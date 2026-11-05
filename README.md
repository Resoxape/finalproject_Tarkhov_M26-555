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
| Проверить пакет перед публикацией | `uv build` + `uvx twine check dist/*` | `make publish` |
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
| `update-rates [--source coingecko\|exchangerate]` | обновить курсы из API |
| `show-rates [--currency <код>] [--top <N>] [--base <код>]` | курсы из локального кеша |
| `rates-history --currency <код> [--limit <N>]` | история курса (таблица) |
| `schedule-updates [--interval <сек>] [--times <N>]` | периодическое обновление курсов |
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
> sell --currency BTC --amount 0.01
Продажа выполнена: 0.0100 BTC по курсу 59337.21 USD/BTC
Изменения в портфеле:
- BTC: было 0.0500 → стало 0.0400
- USD: было 2033.14 → стало 2626.51
Оценочная выручка: 593.37 USD
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

## Parser Service: курсы валют

Курсы берутся из двух публичных API:

- **CoinGecko** — криптовалюты (BTC, ETH, SOL), без ключа;
- **ExchangeRate-API** — фиатные валюты (EUR, GBP, RUB), нужен бесплатный ключ.

Ключ ExchangeRate-API не хранится в коде. Получите его на
https://www.exchangerate-api.com/ и задайте одним из способов:

```
# переменная окружения (Windows PowerShell)
setx EXCHANGERATE_API_KEY "ваш_ключ"     # затем перезапустить терминал

# или файл .env в корне проекта (не отслеживается git)
EXCHANGERATE_API_KEY=ваш_ключ
```

Файлы:

- `data/rates.json` — снимок последних курсов для Core Service
  (`{"pairs": {"BTC_USD": {"rate", "updated_at", "source"}}, "last_refresh"}`);
- `data/exchange_rates.json` — история всех замеров, `id = <FROM>_<TO>_<timestamp>`;
- `logs/parser.log` — журнал обновлений.

Если кеш старше TTL (`rates_ttl_seconds`, 5 минут), Core Service при запросе
курса сам пытается обновить его; если API недоступны, используются последние
сохранённые курсы с предупреждением.

```
> update-rates
INFO: Starting rates update...
INFO: Fetching from CoinGecko... OK (3 rates)
INFO: Fetching from ExchangeRate-API... OK (3 rates)
INFO: Writing 6 rates to data/rates.json...
Update successful. Total rates updated: 6. Last refresh: 2026-11-06T00:52:03Z
> show-rates --top 2
Rates from cache (updated at 2026-11-06T00:52:03Z):
- BTC_USD: 101234.50
- ETH_USD: 3890.10
```

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
├── parser_service/
│   ├── config.py       # ParserConfig: API, валюты, пути, таймауты
│   ├── api_clients.py  # BaseApiClient, CoinGeckoClient, ExchangeRateApiClient
│   ├── updater.py      # RatesUpdater
│   ├── storage.py      # exchange_rates.json и rates.json
│   └── scheduler.py    # RatesScheduler
└── cli/
    └── interface.py    # команды CLI
main.py               # запуск: uv run main.py
```
