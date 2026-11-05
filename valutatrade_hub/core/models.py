"""Модели предметной области: User, Wallet, Portfolio."""

import hashlib
import secrets
from datetime import datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import (
    BASE_CURRENCY,
    STUB_USD_RATES,
    format_amount,
    validate_amount,
)

MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 8

# Фиксированные курсы для get_total_value: сколько USD стоит 1 единица валюты
DEFAULT_EXCHANGE_RATES = {BASE_CURRENCY: 1.0, **STUB_USD_RATES}


class User:
    """Пользователь системы."""

    def __init__(self, user_id, username, hashed_password, salt, registration_date):
        self._user_id = user_id
        self.username = username  # через сеттер с проверкой
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id, username, password):
        """Создаёт нового пользователя: генерирует соль и хеширует пароль."""
        cls._validate_password(password)
        salt = secrets.token_hex(SALT_BYTES)
        return cls(
            user_id=user_id,
            username=username,
            hashed_password=cls._hash_password(password, salt),
            salt=salt,
            registration_date=datetime.now().replace(microsecond=0),
        )

    @staticmethod
    def _hash_password(password, salt):
        """Односторонний хеш: sha256(password + salt)."""
        return hashlib.sha256((password + salt).encode()).hexdigest()

    @staticmethod
    def _validate_password(password):
        """Пароль — строка не короче MIN_PASSWORD_LENGTH символов."""
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
            )

    @property
    def user_id(self):
        """Уникальный идентификатор."""
        return self._user_id

    @property
    def username(self):
        """Имя пользователя."""
        return self._username

    @username.setter
    def username(self, value):
        """Имя не может быть пустым."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self):
        """Хеш пароля."""
        return self._hashed_password

    @property
    def salt(self):
        """Соль пользователя."""
        return self._salt

    @property
    def registration_date(self):
        """Дата регистрации (datetime)."""
        return self._registration_date

    def get_user_info(self):
        """Информация о пользователе без пароля."""
        registered = self._registration_date.strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"ID: {self._user_id}, имя: {self._username}, "
            f"дата регистрации: {registered}"
        )

    def change_password(self, new_password):
        """Меняет пароль: новая соль и новый хеш."""
        self._validate_password(new_password)
        self._salt = secrets.token_hex(SALT_BYTES)
        self._hashed_password = self._hash_password(new_password, self._salt)

    def verify_password(self, password):
        """Проверяет, совпадает ли пароль с сохранённым хешем."""
        return self._hash_password(password, self._salt) == self._hashed_password

    def to_dict(self):
        """Словарь для users.json."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data):
        """Создаёт пользователя из записи users.json."""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )


class Wallet:
    """Кошелёк пользователя для одной валюты."""

    def __init__(self, currency_code, balance=0.0):
        self.currency_code = currency_code
        self.balance = balance  # через сеттер с проверкой

    @property
    def currency(self):
        """Объект Currency для кода кошелька (точка интеграции с currencies.py)."""
        return get_currency(self.currency_code)

    @property
    def balance(self):
        """Текущий баланс."""
        return self._balance

    @balance.setter
    def balance(self, value):
        """Баланс — число (не bool), не отрицательное."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount):
        """Пополнение баланса на положительную сумму."""
        amount = validate_amount(amount)
        self.balance = round(self._balance + amount, 8)

    def withdraw(self, amount):
        """Снятие средств, если баланс позволяет."""
        amount = validate_amount(amount)
        if amount > self._balance:
            code = self.currency_code
            raise InsufficientFundsError(
                format_amount(code, self._balance), format_amount(code, amount), code
            )
        self.balance = round(self._balance - amount, 8)

    def get_balance_info(self):
        """Строка с текущим балансом."""
        code = self.currency_code
        return f"{code}: {format_amount(code, self._balance)}"

    def to_dict(self):
        """Словарь для хранения в составе портфеля."""
        return {"currency_code": self.currency_code, "balance": self._balance}


class Portfolio:
    """Все кошельки одного пользователя."""

    def __init__(self, user_id, wallets=None, user=None):
        self._user_id = user_id
        self._wallets = dict(wallets or {})
        self._user = user

    @property
    def user_id(self):
        """ID владельца портфеля."""
        return self._user_id

    @property
    def user(self):
        """Объект пользователя-владельца (только чтение)."""
        return self._user

    @property
    def wallets(self):
        """Копия словаря кошельков."""
        return dict(self._wallets)

    def add_currency(self, currency_code):
        """Добавляет новый кошелёк; код валюты должен быть уникален."""
        if currency_code in self._wallets:
            raise ValueError(f"Кошелёк '{currency_code}' уже есть в портфеле")
        wallet = Wallet(currency_code)
        self._wallets[currency_code] = wallet
        return wallet

    def get_wallet(self, currency_code):
        """Кошелёк по коду валюты или None."""
        return self._wallets.get(currency_code)

    def get_total_value(self, base_currency=BASE_CURRENCY, exchange_rates=None):
        """Общая стоимость всех кошельков в base_currency.

        exchange_rates: {код: сколько USD стоит 1 единица валюты}.
        """
        rates = exchange_rates or DEFAULT_EXCHANGE_RATES
        if base_currency not in rates:
            raise ValueError(f"Неизвестная базовая валюта '{base_currency}'")
        total_usd = 0.0
        for code, wallet in self._wallets.items():
            if code not in rates:
                raise ValueError(f"Не удалось получить курс для {code}→{base_currency}")
            total_usd += wallet.balance * rates[code]
        return total_usd / rates[base_currency]

    def to_dict(self):
        """Словарь для portfolios.json."""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {"balance": wallet.balance}
                for code, wallet in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, data, user=None):
        """Создаёт портфель из записи portfolios.json."""
        wallets = {
            code: Wallet(code, info["balance"])
            for code, info in data.get("wallets", {}).items()
        }
        return cls(data["user_id"], wallets, user)
