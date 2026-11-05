"""Хранилище Parser Service: история exchange_rates.json и кеш rates.json."""

import json
import os
from datetime import datetime, timezone

FILE_ENCODING = "utf-8"
JSON_INDENT = 2
TMP_SUFFIX = ".tmp"


def parse_utc(value):
    """ISO-строка -> datetime с часовым поясом (без пояса считается UTC)."""
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


class RatesStorage:
    """Чтение и атомарная запись файлов курсов."""

    def __init__(self, rates_path, history_path):
        self.rates_path = rates_path
        self.history_path = history_path

    @staticmethod
    def _read(path, default):
        """JSON из файла; default, если файла нет или он повреждён."""
        try:
            with open(path, encoding=FILE_ENCODING) as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write(path, data):
        """Атомарная запись: временный файл -> rename."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp_path = path + TMP_SUFFIX
        with open(tmp_path, "w", encoding=FILE_ENCODING) as file:
            json.dump(data, file, ensure_ascii=False, indent=JSON_INDENT)
        os.replace(tmp_path, path)

    def load_history(self):
        """Все замеры из exchange_rates.json."""
        history = self._read(self.history_path, [])
        return history if isinstance(history, list) else []

    def append_history(self, records):
        """Добавляет замеры, пропуская уже существующие id. Возвращает число новых."""
        history = self.load_history()
        known_ids = {record["id"] for record in history}
        new_records = [record for record in records if record["id"] not in known_ids]
        if new_records:
            self._write(self.history_path, history + new_records)
        return len(new_records)

    def load_cache(self):
        """Снимок текущих курсов из rates.json."""
        cache = self._read(self.rates_path, {})
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
        self._write(self.rates_path, cache)
        return cache
