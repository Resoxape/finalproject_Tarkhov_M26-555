"""Настройка логирования: формат, уровень, ротация файлов."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import SettingsLoader

LOGGER_NAME = "valutatrade"  # операции пользователя -> logs/actions.log
PARSER_LOGGER_NAME = "valutatrade.parser"  # Parser Service -> logs/parser.log
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"  # ISO-время в каждой записи
CONSOLE_FORMAT = "%(levelname)s: %(message)s"
LOG_ENCODING = "utf-8"


def _file_handler(filename):
    """Файловый обработчик с ротацией по размеру."""
    settings = SettingsLoader()
    log_dir = settings.get("log_dir")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, filename),
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backup_count"),
        encoding=LOG_ENCODING,
    )
    handler.setFormatter(
        logging.Formatter(settings.get("log_format"), datefmt=DATE_FORMAT)
    )
    return handler


def setup_logging():
    """Логгеры приложения: actions.log и parser.log с ротацией.

    Формат строковый (человекочитаемый):
    INFO 2025-10-09T12:05:22 BUY user_id=1 currency='BTC' amount=0.0500 ...
    Уровень по умолчанию INFO, для отладки — log_level = "DEBUG" в настройках.
    """
    settings = SettingsLoader()
    level = getattr(logging, str(settings.get("log_level")).upper(), logging.INFO)

    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.addHandler(_file_handler(settings.get("log_file")))
        logger.setLevel(level)
        logger.propagate = False

    parser_logger = logging.getLogger(PARSER_LOGGER_NAME)
    if not parser_logger.handlers:
        parser_logger.addHandler(_file_handler(settings.get("parser_log_file")))
        parser_logger.setLevel(level)
        parser_logger.propagate = False  # не дублировать в actions.log
    return logger


def console_handler():
    """Вывод логов парсера в консоль: 'INFO: Starting rates update...'."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    return handler
