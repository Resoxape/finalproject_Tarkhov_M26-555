"""Клиенты внешних API: единый интерфейс fetch_rates() -> {"BTC_USD": 59337.21}."""

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import requests

from valutatrade_hub.core.exceptions import ApiRequestError

HTTP_OK = 200
HTTP_UNAUTHORIZED = (401, 403)
HTTP_TOO_MANY_REQUESTS = 429
PAIR_SEPARATOR = "_"
ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now_iso():
    """Текущее время UTC: 2025-10-10T12:00:00Z."""
    return datetime.now(timezone.utc).strftime(ISO_UTC_FORMAT)


def is_valid_rate(value):
    """Курс — положительное число (не bool)."""
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value > 0


class BaseApiClient(ABC):
    """Базовый клиент: HTTP-запрос, обработка ошибок, метаданные ответа."""

    SOURCE = "API"

    def __init__(self, config):
        self.config = config
        self.last_meta = {}  # request_ms, status_code, etag последнего запроса
        self.last_timestamp = None  # время курсов (ISO UTC)
        self.raw_ids = {}  # пара -> исходный идентификатор в API

    @abstractmethod
    def fetch_rates(self):
        """Курсы в стандартном формате {"<FROM>_<TO>": rate}."""

    def pair(self, code):
        """'BTC' -> 'BTC_USD'."""
        return f"{code}{PAIR_SEPARATOR}{self.config.BASE_CURRENCY}"

    def _get(self, url, params=None):
        """GET-запрос; любые сетевые и HTTP-ошибки -> ApiRequestError."""
        start = time.monotonic()
        try:
            response = requests.get(
                url, params=params, timeout=self.config.REQUEST_TIMEOUT
            )
        except requests.exceptions.Timeout:
            raise ApiRequestError("превышено время ожидания ответа") from None
        except requests.exceptions.RequestException as error:
            raise ApiRequestError(f"сетевая ошибка ({type(error).__name__})") from None

        self.last_meta = {
            "request_ms": round((time.monotonic() - start) * 1000),
            "status_code": response.status_code,
            "etag": response.headers.get("ETag"),
        }
        if response.status_code == HTTP_TOO_MANY_REQUESTS:
            raise ApiRequestError("превышен лимит запросов (429 Too Many Requests)")
        if response.status_code in HTTP_UNAUTHORIZED:
            raise ApiRequestError(
                f"неверный или неактивный API-ключ (HTTP {response.status_code})"
            )
        if response.status_code != HTTP_OK:
            raise ApiRequestError(f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise ApiRequestError("некорректный JSON в ответе") from None


class CoinGeckoClient(BaseApiClient):
    """Криптовалюты: CoinGecko /simple/price, публичный доступ без ключа."""

    SOURCE = "CoinGecko"

    def fetch_rates(self):
        """{"BTC_USD": 59337.21, ...} для CRYPTO_CURRENCIES."""
        ids = {
            code: self.config.CRYPTO_ID_MAP[code]
            for code in self.config.CRYPTO_CURRENCIES
        }
        vs_currency = self.config.BASE_CURRENCY.lower()
        data = self._get(
            self.config.COINGECKO_URL,
            params={"ids": ",".join(ids.values()), "vs_currencies": vs_currency},
        )
        self.last_timestamp = utc_now_iso()
        rates = {}
        self.raw_ids = {}
        for code, coin_id in ids.items():
            entry = data.get(coin_id) if isinstance(data, dict) else None
            value = entry.get(vs_currency) if isinstance(entry, dict) else None
            if is_valid_rate(value):
                rates[self.pair(code)] = float(value)
                self.raw_ids[self.pair(code)] = coin_id
        if not rates:
            raise ApiRequestError("в ответе нет курсов")
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """Фиатные валюты: ExchangeRate-API /latest/<BASE>, нужен ключ."""

    SOURCE = "ExchangeRate-API"

    def fetch_rates(self):
        """{"EUR_USD": 1.0787, ...}: API отдаёт USD→EUR, сохраняем EUR→USD."""
        key = self.config.EXCHANGERATE_API_KEY
        if not key:
            raise ApiRequestError(
                "не задан API-ключ (переменная EXCHANGERATE_API_KEY или файл .env)"
            )
        base = self.config.BASE_CURRENCY
        data = self._get(f"{self.config.EXCHANGERATE_API_URL}/{key}/latest/{base}")
        if not isinstance(data, dict) or data.get("result") != "success":
            reason = data.get("error-type") if isinstance(data, dict) else None
            raise ApiRequestError(reason or "неуспешный ответ API")

        updated_unix = data.get("time_last_update_unix")
        if isinstance(updated_unix, int):
            self.last_timestamp = datetime.fromtimestamp(
                updated_unix, timezone.utc
            ).strftime(ISO_UTC_FORMAT)
        else:
            self.last_timestamp = utc_now_iso()

        # v6 с ключом отдаёт "conversion_rates", пример в документации — "rates"
        api_rates = data.get("conversion_rates") or data.get("rates") or {}
        rates = {}
        self.raw_ids = {}
        for code in self.config.FIAT_CURRENCIES:
            value = api_rates.get(code)
            if is_valid_rate(value):
                rates[self.pair(code)] = round(1 / value, 8)  # 1 USD = value <code>
                self.raw_ids[self.pair(code)] = code
        if not rates:
            raise ApiRequestError("в ответе нет курсов")
        return rates
