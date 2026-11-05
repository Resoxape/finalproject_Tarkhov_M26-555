"""Иерархия валют: абстрактная Currency, FiatCurrency, CryptoCurrency и реестр."""

from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError

CODE_MIN_LENGTH = 2
CODE_MAX_LENGTH = 5


class Currency(ABC):
    """Базовая валюта: человекочитаемое имя и код (ISO или тикер)."""

    def __init__(self, name, code):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        if (
            not isinstance(code, str)
            or not CODE_MIN_LENGTH <= len(code) <= CODE_MAX_LENGTH
            or not code.isalpha()
            or code != code.upper()
        ):
            raise ValueError(
                f"Код валюты '{code}' должен состоять из {CODE_MIN_LENGTH}–"
                f"{CODE_MAX_LENGTH} заглавных букв без пробелов"
            )
        self.name = name.strip()
        self.code = code

    @abstractmethod
    def get_display_info(self):
        """Строковое представление для UI и логов."""


class FiatCurrency(Currency):
    """Фиатная валюта с указанием страны/зоны эмиссии."""

    def __init__(self, name, code, issuing_country):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self):
        """[FIAT] USD — US Dollar (Issuing: United States)."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта с алгоритмом и рыночной капитализацией."""

    def __init__(self, name, code, algorithm, market_cap):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = float(market_cap)

    def get_display_info(self):
        """[CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e12)."""
        mcap = f"{self.market_cap:.2e}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {mcap})"
        )


# Реестр поддерживаемых валют: код -> объект Currency
CURRENCIES = {
    currency.code: currency
    for currency in (
        FiatCurrency("US Dollar", "USD", "United States"),
        FiatCurrency("Euro", "EUR", "Eurozone"),
        FiatCurrency("British Pound", "GBP", "United Kingdom"),
        FiatCurrency("Russian Ruble", "RUB", "Russia"),
        CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
        CryptoCurrency("Ethereum", "ETH", "Ethash", 4.47e11),
        CryptoCurrency("Solana", "SOL", "Proof of History", 6.8e10),
    )
}


def get_currency(code):
    """Фабрика: валюта по коду. Неизвестный код -> CurrencyNotFoundError."""
    normalized = code.strip().upper() if isinstance(code, str) else code
    if normalized not in CURRENCIES:
        raise CurrencyNotFoundError(code)
    return CURRENCIES[normalized]


def supported_codes():
    """Список кодов поддерживаемых валют."""
    return sorted(CURRENCIES)


def is_crypto(code):
    """True, если код принадлежит криптовалюте из реестра."""
    return isinstance(CURRENCIES.get(code), CryptoCurrency)
