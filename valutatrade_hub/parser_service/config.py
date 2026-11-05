"""Конфигурация Parser Service: API, списки валют, пути, сетевые параметры."""

import os
from dataclasses import dataclass, field

from valutatrade_hub.infra.settings import SettingsLoader

API_KEY_ENV = "EXCHANGERATE_API_KEY"
ENV_FILE = ".env"  # не отслеживается git (см. .gitignore)
ENV_ENCODING = "utf-8"


def load_api_key():
    """Ключ ExchangeRate-API: переменная окружения, иначе файл .env."""
    key = os.getenv(API_KEY_ENV)
    if key:
        return key.strip()
    try:
        with open(ENV_FILE, encoding=ENV_ENCODING) as file:
            for line in file:
                name, separator, value = line.strip().partition("=")
                if separator and name.strip() == API_KEY_ENV:
                    return value.strip().strip("\"'") or None
    except FileNotFoundError:
        pass
    return None


def data_path(setting_name):
    """Путь к файлу в data/ по имени параметра SettingsLoader."""
    settings = SettingsLoader()
    return os.path.join(settings.get("data_dir"), settings.get(setting_name))


@dataclass
class ParserConfig:
    """Все изменяемые параметры парсера в одном месте."""

    # Ключ не хранится в коде: берётся из окружения или .env
    EXCHANGERATE_API_KEY: str | None = field(default_factory=load_api_key)

    # Эндпоинты
    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    # Списки валют
    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict = field(
        default_factory=lambda: {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
    )

    # Пути
    RATES_FILE_PATH: str = field(default_factory=lambda: data_path("rates_file"))
    HISTORY_FILE_PATH: str = field(default_factory=lambda: data_path("history_file"))

    # Сетевые параметры и расписание
    REQUEST_TIMEOUT: int = 10
    UPDATE_INTERVAL_SECONDS: int = 300
