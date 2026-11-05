"""Константы, работа с JSON-файлами, валидация и форматирование."""

import json
import os

# Хранилище
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PORTFOLIOS_FILE = os.path.join(DATA_DIR, "portfolios.json")
RATES_FILE = os.path.join(DATA_DIR, "rates.json")
FILE_ENCODING = "utf-8"
JSON_INDENT = 2

# Пользователи
MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 8

# Валюты и курсы
BASE_CURRENCY = "USD"
RATES_TTL_SECONDS = 5 * 60  # курс считается свежим 5 минут
RATE_KEY_SEPARATOR = "_"
CRYPTO_CURRENCIES = {"BTC", "ETH", "SOL", "USDT"}
CRYPTO_DECIMALS = 4
FIAT_DECIMALS = 2
# Заглушка Parser Service: сколько USD стоит 1 единица валюты
STUB_USD_RATES = {
    "EUR": 1.0786,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.00,
}
STUB_SOURCE = "ParserServiceStub"


def load_json(path, default):
    """Читает JSON-файл; если файла нет или он повреждён, возвращает default."""
    try:
        with open(path, encoding=FILE_ENCODING) as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    """Сохраняет данные в JSON-файл, создавая директорию при необходимости."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding=FILE_ENCODING) as file:
        json.dump(data, file, ensure_ascii=False, indent=JSON_INDENT)


def validate_currency_code(code):
    """Код валюты: непустая строка из букв. Возвращает код в верхнем регистре."""
    if not isinstance(code, str) or not code.strip().isalpha():
        raise ValueError(f"Некорректный код валюты '{code}'")
    return code.strip().upper()


def validate_amount(raw):
    """Сумма: конечное число > 0. Принимает строку или число, возвращает float."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("'amount' должен быть положительным числом") from None
    if not value > 0 or value == float("inf"):
        raise ValueError("'amount' должен быть положительным числом")
    return value


def format_amount(currency_code, value):
    """Количество валюты: 4 знака для криптовалют, 2 — для фиатных."""
    decimals = CRYPTO_DECIMALS if currency_code in CRYPTO_CURRENCIES else FIAT_DECIMALS
    return f"{value:.{decimals}f}"


def format_rate(rate):
    """Курс: 2 знака от 100, 4 знака от 1, 8 знаков для маленьких курсов."""
    if rate >= 100:
        return f"{rate:.2f}"
    if rate >= 1:
        return f"{rate:.4f}"
    return f"{rate:.8f}"


def format_money(value):
    """Денежная сумма с разделителем тысяч: 3,329.00."""
    return f"{value:,.2f}"
