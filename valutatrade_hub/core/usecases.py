"""Бизнес-логика: регистрация, вход, портфель, покупка/продажа, курсы.

Синглтоны: SettingsLoader — TTL курсов и базовая валюта,
DatabaseManager — все чтения и записи JSON-хранилища.
"""

from datetime import datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    BASE_CURRENCY,
    STUB_USD_RATES,
    convert,
    validate_amount,
    validate_currency_code,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader

settings = SettingsLoader()
db = DatabaseManager()

RATE_KEY_SEPARATOR = "_"
STUB_SOURCE = "ParserServiceStub"


# ---------- Пользователи ----------


def load_users():
    """Все пользователи из users.json."""
    return [User.from_dict(item) for item in db.read("users", [])]


@log_action("REGISTER")
def register_user(username, password):
    """Создаёт пользователя и пустой портфель. Возвращает User."""
    username = username.strip()

    def add_user(items):
        """Проверяет уникальность имени и добавляет пользователя."""
        if any(item["username"] == username for item in items):
            raise ValueError(f"Имя пользователя '{username}' уже занято")
        user_id = max((item["user_id"] for item in items), default=0) + 1
        user = User.create(user_id, username, password)
        items.append(user.to_dict())
        return user

    user = db.update("users", [], add_user)
    db.update(
        "portfolios", [], lambda items: items.append(Portfolio(user.user_id).to_dict())
    )
    return user


@log_action("LOGIN")
def login_user(username, password):
    """Проверяет имя и пароль. Возвращает User."""
    for user in load_users():
        if user.username == username:
            if not user.verify_password(password):
                raise ValueError("Неверный пароль")
            return user
    raise ValueError(f"Пользователь '{username}' не найден")


# ---------- Портфели ----------


def _find_portfolio_item(items, user_id):
    """Запись портфеля пользователя в списке (создаётся, если её нет)."""
    for item in items:
        if item["user_id"] == user_id:
            return item
    item = Portfolio(user_id).to_dict()
    items.append(item)
    return item


def load_portfolio(user_id):
    """Портфель пользователя только для чтения."""
    items = db.read("portfolios", [])
    return Portfolio.from_dict(_find_portfolio_item(items, user_id))


def _change_portfolio(user_id, action):
    """Чтение → action(portfolio) → запись портфеля через DatabaseManager."""

    def modify(items):
        """Применяет action к портфелю и сохраняет его в списке."""
        item = _find_portfolio_item(items, user_id)
        portfolio = Portfolio.from_dict(item)
        result = action(portfolio)
        item.update(portfolio.to_dict())
        return result

    return db.update("portfolios", [], modify)


# ---------- Курсы ----------


def rate_key(currency_code):
    """Ключ курса к USD в rates.json: 'BTC' -> 'BTC_USD'."""
    return f"{currency_code}{RATE_KEY_SEPARATOR}{BASE_CURRENCY}"


def is_fresh(rates):
    """Кеш курсов моложе TTL из SettingsLoader."""
    last_refresh = rates.get("last_refresh")
    if not last_refresh:
        return False
    age = datetime.now() - datetime.fromisoformat(last_refresh)
    return age.total_seconds() < settings.get("rates_ttl_seconds")


def fetch_rates_from_parser():
    """Заглушка Parser Service: курсы с текущим временем, сохраняются в кеш."""
    now = datetime.now().replace(microsecond=0).isoformat()
    rates = {
        rate_key(code): {"rate": rate, "updated_at": now}
        for code, rate in STUB_USD_RATES.items()
    }
    rates["source"] = STUB_SOURCE
    rates["last_refresh"] = now
    try:
        db.write("rates", rates)
    except OSError as error:
        raise ApiRequestError(f"не удалось сохранить курсы ({error})") from None
    return rates


def get_rates():
    """Курсы из кеша, а если кеш устарел — обновлённые от Parser Service."""
    rates = db.read("rates", {})
    if is_fresh(rates):
        return rates
    return fetch_rates_from_parser()


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
    from_code = get_currency(validate_currency_code(from_code)).code
    to_code = get_currency(validate_currency_code(to_code)).code
    rates = get_rates()
    known = usd_rates(rates)
    for code in (from_code, to_code):
        if code not in known:
            raise ApiRequestError(f"нет данных о курсе {code}→{BASE_CURRENCY}")
    updated_at = rates.get("last_refresh", "")
    for code in (from_code, to_code):
        entry = rates.get(rate_key(code))
        if entry:
            updated_at = entry["updated_at"]
    return convert(1.0, known[from_code], known[to_code]), updated_at


# ---------- Операции с портфелем ----------


def show_portfolio(user_id, base_currency=None):
    """Строки портфеля [(код, баланс, стоимость в base)], итог и база."""
    base = (base_currency or settings.get("default_base_currency")).upper()
    try:
        get_currency(base)
    except CurrencyNotFoundError:
        raise ValueError(f"Неизвестная базовая валюта '{base}'") from None
    known = usd_rates(get_rates())
    portfolio = load_portfolio(user_id)
    rows = []
    for code, wallet in portfolio.wallets.items():
        if code not in known:
            raise ApiRequestError(f"нет данных о курсе {code}→{base}")
        rows.append(
            (code, wallet.balance, convert(wallet.balance, known[code], known[base]))
        )
    total = portfolio.get_total_value(base, known) if rows else 0.0
    return rows, total, base


@log_action("BUY", verbose=True)
def buy_currency(user_id, currency_code, amount):
    """Покупка: валюта зачисляется, её стоимость списывается с USD-кошелька."""
    code = get_currency(validate_currency_code(currency_code)).code
    amount = validate_amount(amount)
    rate, _ = get_rate(code, BASE_CURRENCY)
    cost = amount * rate

    def action(portfolio):
        """Списывает оплату в USD и пополняет кошелёк валюты."""
        changes = []
        if code != BASE_CURRENCY:
            usd_wallet = portfolio.get_wallet(BASE_CURRENCY)
            if usd_wallet is None:
                raise InsufficientFundsError("0.00", f"{cost:.2f}", BASE_CURRENCY)
            usd_before = usd_wallet.balance
            usd_wallet.withdraw(cost)
            changes.append((BASE_CURRENCY, usd_before, usd_wallet.balance))
        wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)
        before = wallet.balance
        wallet.deposit(amount)
        changes.insert(0, (code, before, wallet.balance))
        return changes

    changes = _change_portfolio(user_id, action)
    return {
        "currency": code,
        "amount": amount,
        "rate": rate,
        "base": BASE_CURRENCY,
        "total": cost,
        "changes": changes,
    }


@log_action("SELL", verbose=True)
def sell_currency(user_id, currency_code, amount):
    """Продажа: валюта списывается, выручка зачисляется на USD-кошелёк."""
    code = get_currency(validate_currency_code(currency_code)).code
    amount = validate_amount(amount)
    if load_portfolio(user_id).get_wallet(code) is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
    rate, _ = get_rate(code, BASE_CURRENCY)
    revenue = amount * rate

    def action(portfolio):
        """Списывает валюту (InsufficientFundsError при нехватке) и зачисляет USD."""
        wallet = portfolio.get_wallet(code)
        before = wallet.balance
        wallet.withdraw(amount)
        changes = [(code, before, wallet.balance)]
        if code != BASE_CURRENCY:
            usd_wallet = portfolio.get_wallet(BASE_CURRENCY) or portfolio.add_currency(
                BASE_CURRENCY
            )
            usd_before = usd_wallet.balance
            usd_wallet.deposit(revenue)
            changes.append((BASE_CURRENCY, usd_before, usd_wallet.balance))
        return changes

    changes = _change_portfolio(user_id, action)
    return {
        "currency": code,
        "amount": amount,
        "rate": rate,
        "base": BASE_CURRENCY,
        "total": revenue,
        "changes": changes,
    }
