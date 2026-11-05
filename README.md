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
| `help` / `exit` | справка / выход |

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

## Курсы

Курсы кешируются в `data/rates.json`. Если кеш старше 5 минут, курсы
запрашиваются у Parser Service (пока — заглушка с фиксированными значениями).

## Структура

```
valutatrade_hub/
├── core/
│   ├── models.py     # классы User, Wallet, Portfolio
│   ├── usecases.py   # бизнес-логика
│   └── utils.py      # константы, JSON, валидация, форматирование
└── cli/
    └── interface.py  # команды CLI
main.py               # запуск: uv run main.py
```
