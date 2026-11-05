"""Бизнес-логика: регистрация, вход, портфель, покупка/продажа, курсы.

Синглтоны: SettingsLoader — TTL курсов и базовая валюта,
DatabaseManager — все чтения и записи JSON-хранилища.
"""

from datetime import datetime, timezone

from valutatrade_hub.core.currencies import get_currency, is_crypto
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User
from valutatrade_hub.core.utils import (
    BASE_CURRENCY,
    convert,
    format_amount,
    parse_utc,
    validate_amount,
    validate_currency_code,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import create_updater

settings = SettingsLoader()
db = DatabaseManager()

PAIR_SEPARATOR = "_"
DEFAULT_HISTORY_LIMIT = 10
CACHE_EMPTY_MESSAGE = (
    "Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные."
)


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


def find_user(user_id):
    """Пользователь по id или None."""
    for user in load_users():
        if user.user_id == user_id:
            return user
    return None


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
    return Portfolio.from_dict(_find_portfolio_item(items, user_id), find_user(user_id))


def _change_portfolio(user_id, action):
    """Чтение → action(portfolio) → запись портфеля через DatabaseManager."""

    def modify(items):
        """Применяет action к портфелю и сохраняет его в списке."""
        item = _find_portfolio_item(items, user_id)
        portfolio = Portfolio.from_dict(item, find_user(user_id))
        result = action(portfolio)
        item.update(portfolio.to_dict())
        return result

    return db.update("portfolios", [], modify)


# ---------- Курсы ----------


def read_rates_cache():
    """Снимок курсов rates.json в формате {"pairs": {...}, "last_refresh": ...}."""
    cache = db.read("rates", {})
    if not isinstance(cache, dict) or not isinstance(cache.get("pairs"), dict):
        return {"pairs": {}}
    return cache


def is_fresh(cache):
    """Кеш моложе TTL из SettingsLoader."""
    last_refresh = cache.get("last_refresh")
    if not last_refresh:
        return False
    age = datetime.now(timezone.utc) - parse_utc(last_refresh)
    return age.total_seconds() < settings.get("rates_ttl_seconds")


def rates_are_stale():
    """True, если кеш курсов старше TTL (CLI предупреждает пользователя)."""
    return not is_fresh(read_rates_cache())


def get_rates():
    """Курсы из кеша; устаревший кеш пытаемся обновить через Parser Service.

    Если обновить не удалось, но старые данные есть — работаем с ними
    (CLI покажет предупреждение). Если данных нет совсем — ApiRequestError.
    """
    cache = read_rates_cache()
    if is_fresh(cache):
        return cache
    try:
        create_updater().run_update()
    except ApiRequestError:
        if not cache["pairs"]:
            raise
        return cache
    return read_rates_cache()


def usd_rates(cache):
    """{код: сколько USD стоит 1 единица}, включая сам USD."""
    result = {BASE_CURRENCY: 1.0}
    for pair, entry in cache["pairs"].items():
        from_code, _, to_code = pair.partition(PAIR_SEPARATOR)
        if to_code == BASE_CURRENCY:
            result[from_code] = entry["rate"]
    return result


def get_rate(from_code, to_code):
    """Курс from→to и время обновления. Единый контракт получения курса."""
    from_code = get_currency(validate_currency_code(from_code)).code
    to_code = get_currency(validate_currency_code(to_code)).code
    cache = get_rates()
    known = usd_rates(cache)
    for code in (from_code, to_code):
        if code not in known:
            raise ApiRequestError(f"нет данных о курсе {code}→{BASE_CURRENCY}")
    updated_at = cache.get("last_refresh", "")
    for code in (from_code, to_code):
        entry = cache["pairs"].get(f"{code}{PAIR_SEPARATOR}{BASE_CURRENCY}")
        if entry:
            updated_at = entry["updated_at"]
    return convert(1.0, known[from_code], known[to_code]), updated_at


def list_rates(currency_code=None, top=None, base_currency=None):
    """Курсы из кеша для show-rates: [(пара, курс)] и время обновления.

    currency_code — только эта валюта; top — N самых дорогих криптовалют;
    base_currency — пересчитать все курсы к этой базе.
    """
    cache = read_rates_cache()
    if not cache["pairs"]:
        raise ValueError(CACHE_EMPTY_MESSAGE)
    known = usd_rates(cache)
    base = BASE_CURRENCY
    if base_currency:
        base = validate_currency_code(base_currency)
        if base not in known:
            raise ValueError(f"Курс для '{base}' не найден в кеше.")

    rows = [
        (code, convert(1.0, rate, known[base]))
        for code, rate in known.items()
        if code != base
    ]
    if currency_code:
        code = validate_currency_code(currency_code)
        rows = [row for row in rows if row[0] == code]
        if not rows:
            raise ValueError(f"Курс для '{code}' не найден в кеше.")
    if top is not None:
        try:
            limit = int(top)
        except ValueError:
            raise ValueError("'top' должен быть целым положительным числом") from None
        if limit <= 0:
            raise ValueError("'top' должен быть целым положительным числом")
        rows = sorted((r for r in rows if is_crypto(r[0])), key=lambda r: -r[1])
        rows = rows[:limit]
    else:
        rows.sort()
    pairs = [(f"{code}{PAIR_SEPARATOR}{base}", rate) for code, rate in rows]
    return pairs, cache.get("last_refresh", "")


def rate_history(currency_code, limit=DEFAULT_HISTORY_LIMIT):
    """Последние замеры курса валюты к USD из exchange_rates.json."""
    code = get_currency(validate_currency_code(currency_code)).code
    records = [
        record
        for record in db.read("history", [])
        if record.get("from_currency") == code
    ]
    records.sort(key=lambda record: record["timestamp"])
    return records[-limit:]


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
                raise InsufficientFundsError(
                    format_amount(BASE_CURRENCY, 0.0),
                    format_amount(BASE_CURRENCY, cost),
                    BASE_CURRENCY,
                )
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
