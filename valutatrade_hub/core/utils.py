"""Вспомогательные функции: валидация, форматирование, конвертация валют."""

from valutatrade_hub.core.currencies import (
    CODE_MAX_LENGTH,
    CODE_MIN_LENGTH,
    is_crypto,
)

BASE_CURRENCY = "USD"  # валюта расчётов: покупка оплачивается из USD-кошелька
CRYPTO_DECIMALS = 4
FIAT_DECIMALS = 2

# Запасные фиксированные курсы для Portfolio.get_total_value() без кеша:
# сколько USD стоит 1 единица валюты
FALLBACK_USD_RATES = {
    "EUR": 1.0786,
    "GBP": 1.2710,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.00,
    "SOL": 145.30,
}


def validate_currency_code(code):
    """Формат кода: 2–5 букв без пробелов. Возвращает код в верхнем регистре."""
    if not isinstance(code, str):
        raise ValueError(f"Некорректный код валюты '{code}'")
    normalized = code.strip().upper()
    if (
        not CODE_MIN_LENGTH <= len(normalized) <= CODE_MAX_LENGTH
        or not normalized.isalpha()
    ):
        raise ValueError(f"Некорректный код валюты '{code}'")
    return normalized


def validate_amount(raw):
    """Сумма: конечное число > 0. Принимает строку или число, возвращает float."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("'amount' должен быть положительным числом") from None
    if not value > 0 or value == float("inf"):
        raise ValueError("'amount' должен быть положительным числом")
    return value


def convert(amount, from_usd_rate, to_usd_rate):
    """Конвертация через USD: amount * (from→USD) / (to→USD)."""
    return amount * from_usd_rate / to_usd_rate


def format_amount(currency_code, value):
    """Количество валюты: 4 знака для криптовалют, 2 — для фиатных."""
    decimals = CRYPTO_DECIMALS if is_crypto(currency_code) else FIAT_DECIMALS
    return f"{value:.{decimals}f}"


def format_rate(rate):
    """Курс: 2 знака от 100, 4 знака от 1, 8 знаков для маленьких курсов."""
    if rate >= 100:
        return f"{rate:.2f}"
    if rate >= 1:
        return f"{rate:.4f}"
    return f"{rate:.8f}"


def format_rate_compact(rate):
    """Курс без лишних нулей для маленьких значений: 0.01016."""
    text = format_rate(rate)
    return text.rstrip("0") if rate < 1 else text


def format_money(value):
    """Денежная сумма с разделителем тысяч: 3,329.00."""
    return f"{value:,.2f}"
