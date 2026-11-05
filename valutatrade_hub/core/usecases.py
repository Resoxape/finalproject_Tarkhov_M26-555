"""Бизнес-логика: регистрация, вход, портфель, покупка/продажа, курсы."""

from datetime import datetime

from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    BASE_CURRENCY,
    PORTFOLIOS_FILE,
    RATE_KEY_SEPARATOR,
    RATES_FILE,
    RATES_TTL_SECONDS,
    STUB_SOURCE,
    STUB_USD_RATES,
    USERS_FILE,
    load_json,
    save_json,
    validate_amount,
    validate_currency_code,
)

# ---------- Пользователи ----------


def load_users():
    """Все пользователи из users.json."""
    return [User.from_dict(item) for item in load_json(USERS_FILE, [])]


def save_users(users):
    """Сохраняет пользователей в users.json."""
    save_json(USERS_FILE, [user.to_dict() for user in users])


def register_user(username, password):
    """Создаёт пользователя и пустой портфель. Возвращает User."""
    users = load_users()
    username = username.strip()
    if any(user.username == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")
    user_id = max((user.user_id for user in users), default=0) + 1
    user = User.create(user_id, username, password)
    users.append(user)
    save_users(users)

    portfolios = load_portfolios()
    portfolios[user_id] = Portfolio(user_id, user=user)
    save_portfolios(portfolios)
    return user


def login_user(username, password):
    """Проверяет имя и пароль. Возвращает User."""
    for user in load_users():
        if user.username == username:
            if not user.verify_password(password):
                raise ValueError("Неверный пароль")
            return user
    raise ValueError(f"Пользователь '{username}' не найден")


# ---------- Портфели ----------


def load_portfolios():
    """Портфели из portfolios.json: {user_id: Portfolio}."""
    return {
        item["user_id"]: Portfolio.from_dict(item)
        for item in load_json(PORTFOLIOS_FILE, [])
    }


def save_portfolios(portfolios):
    """Сохраняет портфели в portfolios.json."""
    save_json(PORTFOLIOS_FILE, [p.to_dict() for p in portfolios.values()])


def get_portfolio(portfolios, user):
    """Портфель пользователя (создаётся пустой, если его ещё нет)."""
    data = portfolios.get(user.user_id)
    wallets = data.wallets if data else {}
    portfolio = Portfolio(user.user_id, wallets, user=user)
    portfolios[user.user_id] = portfolio
    return portfolio


# ---------- Курсы ----------


def rate_key(currency_code):
    """Ключ курса к USD в rates.json: 'BTC' -> 'BTC_USD'."""
    return f"{currency_code}{RATE_KEY_SEPARATOR}{BASE_CURRENCY}"


def is_fresh(rates):
    """Кеш курсов моложе RATES_TTL_SECONDS."""
    last_refresh = rates.get("last_refresh")
    if not last_refresh:
        return False
    age = datetime.now() - datetime.fromisoformat(last_refresh)
    return age.total_seconds() < RATES_TTL_SECONDS


def fetch_rates_from_parser():
    """Заглушка Parser Service: возвращает курсы и обновляет кеш rates.json."""
    now = datetime.now().replace(microsecond=0).isoformat()
    rates = {
        rate_key(code): {"rate": rate, "updated_at": now}
        for code, rate in STUB_USD_RATES.items()
    }
    rates["source"] = STUB_SOURCE
    rates["last_refresh"] = now
    save_json(RATES_FILE, rates)
    return rates


def get_rates():
    """Курсы из кеша, а если кеш устарел — от Parser Service."""
    rates = load_json(RATES_FILE, {})
    if is_fresh(rates):
        return rates
    try:
        return fetch_rates_from_parser()
    except OSError:
        return rates  # сервис недоступен — работаем со старым кешем


def usd_rates(rates):
    """{код: сколько USD стоит 1 единица}, включая сам USD."""
    result = {BASE_CURRENCY: 1.0}
    suffix = f"{RATE_KEY_SEPARATOR}{BASE_CURRENCY}"
    for key, value in rates.items():
        if key.endswith(suffix) and isinstance(value, dict):
            result[key.removesuffix(suffix)] = value["rate"]
    return result


def get_rate(from_code, to_code):
    """Курс from→to и время обновления. Единый контракт получения курса."""
    from_code = validate_currency_code(from_code)
    to_code = validate_currency_code(to_code)
    rates = get_rates()
    known = usd_rates(rates)
    if from_code not in known or to_code not in known:
        raise ValueError(
            f"Курс {from_code}→{to_code} недоступен. Повторите попытку позже."
        )
    updated_at = rates.get("last_refresh", "")
    for code in (from_code, to_code):
        entry = rates.get(rate_key(code))
        if entry:
            updated_at = entry["updated_at"]
    return known[from_code] / known[to_code], updated_at


def rate_to_usd(currency_code):
    """Курс валюты к USD для покупки/продажи."""
    try:
        rate, _ = get_rate(currency_code, BASE_CURRENCY)
    except ValueError:
        raise ValueError(
            f"Не удалось получить курс для {currency_code}→{BASE_CURRENCY}"
        ) from None
    return rate


# ---------- Операции с портфелем ----------


def show_portfolio(user, base_currency=BASE_CURRENCY):
    """Строки портфеля [(код, баланс, стоимость в base)] и итог."""
    base_currency = validate_currency_code(base_currency)
    known = usd_rates(get_rates())
    if base_currency not in known:
        raise ValueError(f"Неизвестная базовая валюта '{base_currency}'")
    portfolio = get_portfolio(load_portfolios(), user)
    rows = []
    for code, wallet in portfolio.wallets.items():
        if code not in known:
            raise ValueError(f"Не удалось получить курс для {code}→{base_currency}")
        rows.append(
            (code, wallet.balance, wallet.balance * known[code] / known[base_currency])
        )
    total = portfolio.get_total_value(base_currency, known) if rows else 0.0
    return rows, total


def buy_currency(user, currency_code, amount):
    """Покупка: валюта зачисляется, её стоимость списывается с USD-кошелька."""
    currency_code = validate_currency_code(currency_code)
    amount = validate_amount(amount)
    rate = rate_to_usd(currency_code)
    cost = amount * rate

    portfolios = load_portfolios()
    portfolio = get_portfolio(portfolios, user)
    changes = []
    if currency_code != BASE_CURRENCY:
        usd_wallet = portfolio.get_wallet(BASE_CURRENCY)
        usd_before = usd_wallet.balance if usd_wallet else 0.0
        if usd_wallet is None or cost > usd_wallet.balance:
            raise ValueError(
                f"Недостаточно средств: доступно {usd_before:.2f} {BASE_CURRENCY}, "
                f"требуется {cost:.2f} {BASE_CURRENCY}"
            )
        usd_wallet.withdraw(cost)
        changes.append((BASE_CURRENCY, usd_before, usd_wallet.balance))

    wallet = portfolio.get_wallet(currency_code) or portfolio.add_currency(
        currency_code
    )
    before = wallet.balance
    wallet.deposit(amount)
    changes.insert(0, (currency_code, before, wallet.balance))
    save_portfolios(portfolios)
    return {
        "currency": currency_code,
        "amount": amount,
        "rate": rate,
        "total": cost,
        "changes": changes,
    }


def sell_currency(user, currency_code, amount):
    """Продажа: валюта списывается, выручка зачисляется на USD-кошелёк."""
    currency_code = validate_currency_code(currency_code)
    amount = validate_amount(amount)

    portfolios = load_portfolios()
    portfolio = get_portfolio(portfolios, user)
    wallet = portfolio.get_wallet(currency_code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{currency_code}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
    rate = rate_to_usd(currency_code)
    revenue = amount * rate

    before = wallet.balance
    wallet.withdraw(amount)
    changes = [(currency_code, before, wallet.balance)]
    if currency_code != BASE_CURRENCY:
        usd_wallet = portfolio.get_wallet(BASE_CURRENCY) or portfolio.add_currency(
            BASE_CURRENCY
        )
        usd_before = usd_wallet.balance
        usd_wallet.deposit(revenue)
        changes.append((BASE_CURRENCY, usd_before, usd_wallet.balance))
    save_portfolios(portfolios)
    return {
        "currency": currency_code,
        "amount": amount,
        "rate": rate,
        "total": revenue,
        "changes": changes,
    }
