"""Настройка логирования: формат, уровень, ротация файлов."""

import logging
import os
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import SettingsLoader

LOGGER_NAME = "valutatrade"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"  # ISO-время в каждой записи
LOG_ENCODING = "utf-8"


def setup_logging():
    """Логгер valutatrade: файл logs/actions.log с ротацией по размеру.

    Формат строковый (человекочитаемый):
    INFO 2025-10-09T12:05:22 BUY user_id=1 currency='BTC' amount=0.0500 ...
    Уровень по умолчанию INFO, для отладки — log_level = "DEBUG" в настройках.
    """
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:  # уже настроен
        return logger

    settings = SettingsLoader()
    log_dir = settings.get("log_dir")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, settings.get("log_file")),
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backup_count"),
        encoding=LOG_ENCODING,
    )
    handler.setFormatter(
        logging.Formatter(settings.get("log_format"), datefmt=DATE_FORMAT)
    )
    level = getattr(logging, str(settings.get("log_level")).upper(), logging.INFO)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
