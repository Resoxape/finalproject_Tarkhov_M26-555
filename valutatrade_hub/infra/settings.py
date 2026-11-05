"""SettingsLoader — единая точка конфигурации (Singleton)."""

import tomllib

CONFIG_FILE = "pyproject.toml"
CONFIG_SECTION = "valutatrade"  # секция [tool.valutatrade]

# Значения по умолчанию; секция [tool.valutatrade] в pyproject.toml их переопределяет
DEFAULTS = {
    "data_dir": "data",
    "users_file": "users.json",
    "portfolios_file": "portfolios.json",
    "rates_file": "rates.json",
    "history_file": "exchange_rates.json",
    "rates_ttl_seconds": 300,
    "default_base_currency": "USD",
    "log_dir": "logs",
    "log_file": "actions.log",
    "parser_log_file": "parser.log",
    "log_level": "INFO",
    "log_format": "%(levelname)s %(asctime)s %(message)s",
    "log_max_bytes": 1_000_000,
    "log_backup_count": 3,
}


class SettingsLoader:
    """Загружает и кеширует конфигурацию.

    Singleton реализован через __new__: это проще и читабельнее метакласса —
    вся логика в одном классе, а повторный вызов SettingsLoader() в любом модуле
    возвращает тот же объект, поэтому лишние экземпляры при импортах не создаются.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._settings = {}
            instance.reload()
            cls._instance = instance
        return cls._instance

    def reload(self):
        """Перечитывает конфигурацию: значения по умолчанию + pyproject.toml."""
        settings = dict(DEFAULTS)
        try:
            with open(CONFIG_FILE, "rb") as file:
                config = tomllib.load(file)
            settings.update(config.get("tool", {}).get(CONFIG_SECTION, {}))
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            pass  # установленный пакет запускается без pyproject.toml
        self._settings = settings

    def get(self, key, default=None):
        """Значение параметра конфигурации."""
        return self._settings.get(key, default)
