"""RatesUpdater — опрос всех API-клиентов и сохранение курсов."""

import logging

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import PARSER_LOGGER_NAME
from valutatrade_hub.parser_service.api_clients import (
    PAIR_SEPARATOR,
    CoinGeckoClient,
    ExchangeRateApiClient,
    utc_now_iso,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage

logger = logging.getLogger(PARSER_LOGGER_NAME)

SERVICE_NAME = "ParserService"
CLIENTS_BY_SOURCE = {
    "coingecko": CoinGeckoClient,
    "exchangerate": ExchangeRateApiClient,
}


class RatesUpdater:
    """Точка входа логики парсинга."""

    def __init__(self, clients, storage):
        self.clients = clients
        self.storage = storage

    def run_update(self):
        """Опрашивает клиентов, сохраняет историю и кеш.

        Ошибка одного клиента логируется, остальные продолжают работу.
        Если не ответил ни один — ApiRequestError.
        Возвращает {"updated": N, "errors": [...], "last_refresh": "..."}.
        """
        logger.info("Starting rates update...")
        pairs = {}
        history = []
        errors = []
        for client in self.clients:
            try:
                rates = client.fetch_rates()
            except ApiRequestError as error:
                logger.error(f"Failed to fetch from {client.SOURCE}: {error.reason}")
                errors.append(f"{client.SOURCE}: {error.reason}")
                continue
            logger.info(f"Fetching from {client.SOURCE}... OK ({len(rates)} rates)")
            for pair, rate in rates.items():
                pairs[pair] = {
                    "rate": rate,
                    "updated_at": client.last_timestamp,
                    "source": client.SOURCE,
                }
                history.append(self._history_record(client, pair, rate))

        if not pairs:
            logger.error("Update failed: no rates received.")
            raise ApiRequestError("не удалось получить курсы ни из одного источника")

        last_refresh = utc_now_iso()
        logger.info(f"Writing {len(pairs)} rates to {self.storage.rates_path}...")
        added = self.storage.append_history(history)
        self.storage.update_cache(pairs, last_refresh, SERVICE_NAME)
        logger.debug(f"History: {added} new records in {self.storage.history_path}")
        logger.info(
            f"Update finished: {len(pairs)} rates, {len(errors)} errors, "
            f"last refresh {last_refresh}"
        )
        return {"updated": len(pairs), "errors": errors, "last_refresh": last_refresh}

    @staticmethod
    def _history_record(client, pair, rate):
        """Запись exchange_rates.json с id = <FROM>_<TO>_<timestamp>."""
        from_code, _, to_code = pair.partition(PAIR_SEPARATOR)
        timestamp = client.last_timestamp
        return {
            "id": f"{pair}{PAIR_SEPARATOR}{timestamp}",
            "from_currency": from_code,
            "to_currency": to_code,
            "rate": rate,
            "timestamp": timestamp,
            "source": client.SOURCE,
            "meta": {"raw_id": client.raw_ids.get(pair), **client.last_meta},
        }


def create_updater(source=None):
    """RatesUpdater со всеми клиентами или только с указанным источником."""
    config = ParserConfig()
    if source is None:
        client_classes = list(CLIENTS_BY_SOURCE.values())
    elif source.lower() in CLIENTS_BY_SOURCE:
        client_classes = [CLIENTS_BY_SOURCE[source.lower()]]
    else:
        raise ValueError(
            f"Неизвестный источник '{source}'. Доступны: {', '.join(CLIENTS_BY_SOURCE)}"
        )
    storage = RatesStorage(config.RATES_FILE_PATH, config.HISTORY_FILE_PATH)
    return RatesUpdater([cls(config) for cls in client_classes], storage)
