"""DatabaseManager — абстракция над JSON-хранилищем (Singleton)."""

import json
import os

from valutatrade_hub.infra.settings import SettingsLoader

FILE_ENCODING = "utf-8"
JSON_INDENT = 2
TMP_SUFFIX = ".tmp"


def read_json(path, default):
    """JSON из файла; default, если файла нет или он повреждён."""
    try:
        with open(path, encoding=FILE_ENCODING) as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json_atomic(path, data):
    """Атомарная запись JSON: во временный файл, затем rename поверх исходного."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = path + TMP_SUFFIX
    with open(tmp_path, "w", encoding=FILE_ENCODING) as file:
        json.dump(data, file, ensure_ascii=False, indent=JSON_INDENT)
    os.replace(tmp_path, path)


class DatabaseManager:
    """Чтение и запись коллекций users / portfolios / rates.

    Singleton через __new__ (как и SettingsLoader): один объект на приложение.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._settings = SettingsLoader()
            cls._instance = instance
        return cls._instance

    def path(self, collection):
        """Путь к файлу коллекции: data/<collection>.json."""
        filename = self._settings.get(f"{collection}_file")
        return os.path.join(self._settings.get("data_dir"), filename)

    def read(self, collection, default):
        """Данные коллекции; default, если файла нет или он повреждён."""
        return read_json(self.path(collection), default)

    def write(self, collection, data):
        """Атомарная запись коллекции."""
        write_json_atomic(self.path(collection), data)

    def update(self, collection, default, modify):
        """Безопасная операция чтение → модификация → запись.

        modify(data) изменяет данные на месте и возвращает результат операции.
        Если modify бросает исключение, файл не изменяется.
        """
        data = self.read(collection, default)
        result = modify(data)
        self.write(collection, data)
        return result
