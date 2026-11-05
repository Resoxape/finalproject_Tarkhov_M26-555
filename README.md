# ValutaTrade Hub

Консольный симулятор валютного кошелька. Пользователь регистрируется, входит
в систему, покупает и продаёт фиатные и криптовалюты, смотрит портфель и курсы.
Данные хранятся в JSON-файлах в директории `data/`.

## Установка и запуск

| Действие | uv | make |
|---|---|---|
| Установить зависимости | `uv sync` | `make install` |
| Запустить приложение | `uv run project` | `make project` |
| Проверить код линтером | `uv run ruff check .` | `make lint` |
| Собрать пакет | `uv build` | `make build` |
| Установить пакет как команду | `uv tool install --force dist/<файл>.whl` | `make package-install` |

## Команды

| Команда | Описание |
|---|---|
| `register --username <имя> --password <пароль>` | регистрация (пароль от 4 символов) |
| `login --username <имя> --password <пароль>` | вход |
| `logout` | выход из аккаунта |
| `show-portfolio [--base <валюта>]` | кошельки и итоговая стоимость (по умолчанию в USD) |
| `buy --currency <код> --amount <количество>` | покупка валюты, оплата списывается с USD-кошелька |
| `sell --currency <код> --amount <количество>` | продажа валюты, выручка зачисляется на USD-кошелёк |
| `get-rate --from <код> --to <код>` | курс валюты |
| `currencies` | список поддерживаемых валют |
| `help [команда]` / `exit` | справка / выход |

USD-кошелёк пополняется командой `buy --currency USD --amount <сумма>`.

## Пример

```
> register --username alice --password 1234
Пользователь 'alice' зарегистрирован (id=1). Войдите: login --username alice --password ****
> login --username alice --password 1234
Вы вошли как 'alice'
> buy --currency USD --amount 5000
> buy --currency BTC --amount 0.05
Покупка выполнена: 0.0500 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0000 → стало 0.0500
- USD: было 5000.00 → стало 2033.14
Оценочная стоимость покупки: 2,966.86 USD
> show-portfolio
Портфель пользователя 'alice' (база: USD):
- USD: 2033.14  → 2033.14 USD
- BTC: 0.0500  → 2966.86 USD
---------------------------------
ИТОГО: 5,000.00 USD
> get-rate --from USD --to BTC
Курс USD→BTC: 0.00001685 (обновлено: 2025-10-09 10:29:42)
Обратный курс BTC→USD: 59337.21
```

## Валюты

Иерархия в `core/currencies.py`: абстрактный `Currency` и наследники
`FiatCurrency` (страна эмиссии) и `CryptoCurrency` (алгоритм, капитализация).
Поддерживаются USD, EUR, GBP, RUB, BTC, ETH, SOL; `get_currency(code)` бросает
`CurrencyNotFoundError` для неизвестного кода.

```
[FIAT] USD — US Dollar (Issuing: United States)
[CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e12)
```

## Ошибки

| Исключение | Когда | Что видит пользователь |
|---|---|---|
| `InsufficientFundsError` | не хватает средств при продаже или для оплаты покупки | `Недостаточно средств: доступно 0.0400 BTC, требуется 0.5000 BTC` |
| `CurrencyNotFoundError` | неизвестный код валюты | `Неизвестная валюта 'XYZ'` + список поддерживаемых валют |
| `ApiRequestError` | не удалось обновить курсы | `Ошибка при обращении к внешнему API: ...` + совет повторить позже |

## Настройки и логи

Конфигурация — секция `[tool.valutatrade]` в `pyproject.toml`, читается
синглтоном `SettingsLoader` (пути к JSON, TTL курсов, базовая валюта, логи).
Доступ к JSON-файлам — через синглтон `DatabaseManager`
(чтение → изменение → атомарная запись).

Операции `register`, `login`, `buy`, `sell` логируются декоратором `@log_action`
в `logs/actions.log` (ротация по размеру, уровень INFO):

```
INFO 2026-11-06T00:43:19 BUY user_id=1 currency='BTC' amount=0.0500 rate=59337.21 base='USD' changes=[BTC: 0.0→0.05, USD: 5000.0→2033.1395] result=OK
```

## Курсы

Курсы кешируются в `data/rates.json`. Если кеш старше 5 минут, курсы
запрашиваются у Parser Service (пока — заглушка с фиксированными значениями).

## Структура

```
valutatrade_hub/
├── logging_config.py   # настройка логов
├── decorators.py       # @log_action
├── core/
│   ├── currencies.py   # Currency, FiatCurrency, CryptoCurrency, get_currency
│   ├── exceptions.py   # пользовательские исключения
│   ├── models.py       # классы User, Wallet, Portfolio
│   ├── usecases.py     # бизнес-логика
│   └── utils.py        # валидация, форматирование, конвертация
├── infra/
│   ├── settings.py     # Singleton SettingsLoader
│   └── database.py     # Singleton DatabaseManager
└── cli/
    └── interface.py    # команды CLI
main.py               # запуск: uv run main.py
```
