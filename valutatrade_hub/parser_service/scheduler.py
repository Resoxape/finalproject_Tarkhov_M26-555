"""Планировщик периодического обновления курсов."""

import logging
import threading

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import PARSER_LOGGER_NAME

logger = logging.getLogger(PARSER_LOGGER_NAME)


class RatesScheduler:
    """Запускает RatesUpdater.run_update() каждые interval_seconds секунд."""

    def __init__(self, updater, interval_seconds):
        if interval_seconds <= 0:
            raise ValueError("Интервал обновления должен быть больше 0 секунд")
        self.updater = updater
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()

    def run(self, iterations=None):
        """Блокирующий цикл; iterations=None — пока не вызван stop() или Ctrl+C."""
        completed = 0
        while not self._stop_event.is_set():
            try:
                self.updater.run_update()
            except ApiRequestError as error:
                logger.error(f"Scheduled update failed: {error.reason}")
            completed += 1
            if iterations is not None and completed >= iterations:
                break
            self._stop_event.wait(self.interval_seconds)
        return completed

    def start_background(self):
        """Запуск в фоновом потоке (daemon) — для встраивания в другие сервисы."""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """Останавливает цикл после текущего обновления."""
        self._stop_event.set()
