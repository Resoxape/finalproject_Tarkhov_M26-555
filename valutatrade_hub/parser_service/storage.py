"""Хранилище Parser Service: история exchange_rates.json и кеш rates.json."""

from valutatrade_hub.core.utils import parse_utc
from valutatrade_hub.infra.database import read_json, write_json_atomic


class RatesStorage:
    """Чтение и атомарная запись файлов курсов."""

    def __init__(self, rates_path, history_path):
        self.rates_path = rates_path
        self.history_path = history_path

    def load_history(self):
        """Все замеры из exchange_rates.json."""
        history = read_json(self.history_path, [])
        return history if isinstance(history, list) else []

    def append_history(self, records):
        """Добавляет замеры, пропуская уже существующие id. Возвращает число новых."""
        history = self.load_history()
        known_ids = {record["id"] for record in history}
        new_records = [record for record in records if record["id"] not in known_ids]
        if new_records:
            write_json_atomic(self.history_path, history + new_records)
        return len(new_records)

    def load_cache(self):
        """Снимок текущих курсов из rates.json."""
        cache = read_json(self.rates_path, {})
        if not isinstance(cache, dict) or not isinstance(cache.get("pairs"), dict):
            return {"pairs": {}}
        return cache

    def update_cache(self, pairs, last_refresh, source):
        """Обновляет пары в rates.json: побеждает запись с более свежим updated_at."""
        cache = self.load_cache()
        for pair, entry in pairs.items():
            current = cache["pairs"].get(pair)
            if current is None or parse_utc(entry["updated_at"]) > parse_utc(
                current["updated_at"]
            ):
                cache["pairs"][pair] = entry
        cache["source"] = source
        cache["last_refresh"] = last_refresh
        write_json_atomic(self.rates_path, cache)
        return cache
