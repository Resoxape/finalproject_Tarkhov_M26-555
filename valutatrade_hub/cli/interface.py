"""Командный интерфейс: разбор команд, вывод результатов и сообщений об ошибках."""

import shlex

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import CURRENCIES, supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.utils import (
    format_amount,
    format_money,
    format_rate,
)
from valutatrade_hub.logging_config import setup_logging

PROMPT = "> "
SEPARATOR_LINE = "-" * 33
OPTION_PREFIX = "--"

COMMAND_HELP = {
    "register": "register --username <имя> --password <пароль> — регистрация",
    "login": "login --username <имя> --password <пароль> — вход",
    "logout": "logout — выход из аккаунта",
    "show-portfolio": "show-portfolio [--base <валюта>] — портфель и итог",
    "buy": "buy --currency <код> --amount <количество> — купить (оплата из USD)",
    "sell": "sell --currency <код> --amount <количество> — продать (выручка в USD)",
    "get-rate": "get-rate --from <код> --to <код> — курс валюты",
    "currencies": "currencies — список поддерживаемых валют",
    "help": "help [команда] — справка",
    "exit": "exit — выход из программы",
}


def print_help(options_tokens):
    """help или help <команда>."""
    if options_tokens and options_tokens[0] in COMMAND_HELP:
        print(COMMAND_HELP[options_tokens[0]])
        if options_tokens[0] in ("get-rate", "buy", "sell"):
            print(f"Поддерживаемые валюты: {', '.join(supported_codes())}")
        return
    print("Команды:")
    for text in COMMAND_HELP.values():
        print(f"  {text}")


def parse_options(tokens):
    """['--username', 'alice'] -> {'username': 'alice'}."""
    options = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith(OPTION_PREFIX) or len(token) == len(OPTION_PREFIX):
            raise ValueError(f"Некорректный аргумент '{token}'")
        name = token[len(OPTION_PREFIX) :]
        if index + 1 >= len(tokens) or tokens[index + 1].startswith(OPTION_PREFIX):
            raise ValueError(f"Не указано значение для --{name}")
        options[name] = tokens[index + 1]
        index += 2
    return options


def require(options, name):
    """Значение обязательного аргумента."""
    if name not in options:
        raise ValueError(f"Не указан обязательный аргумент --{name}")
    return options[name]


def require_login(session):
    """Текущий пользователь или ошибка, если вход не выполнен."""
    if session["user"] is None:
        raise ValueError("Сначала выполните login")
    return session["user"]


def print_changes(changes):
    """Выводит изменения балансов после сделки."""
    print("Изменения в портфеле:")
    for code, before, after in changes:
        print(
            f"- {code}: было {format_amount(code, before)} "
            f"→ стало {format_amount(code, after)}"
        )


def cmd_register(options, session):
    """register --username --password."""
    user = usecases.register_user(
        require(options, "username"), require(options, "password")
    )
    print(
        f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
        f"Войдите: login --username {user.username} --password ****"
    )


def cmd_login(options, session):
    """login --username --password."""
    user = usecases.login_user(
        require(options, "username"), require(options, "password")
    )
    session["user"] = user
    print(f"Вы вошли как '{user.username}'")


def cmd_logout(options, session):
    """logout."""
    user = require_login(session)
    session["user"] = None
    print(f"Вы вышли из аккаунта '{user.username}'")


def cmd_show_portfolio(options, session):
    """show-portfolio [--base]."""
    user = require_login(session)
    rows, total, base = usecases.show_portfolio(user.user_id, options.get("base"))
    if not rows:
        print(f"Портфель пользователя '{user.username}' пуст. Купите валюту: buy")
        return
    print(f"Портфель пользователя '{user.username}' (база: {base}):")
    for code, balance, value in rows:
        print(f"- {code}: {format_amount(code, balance)}  → {value:.2f} {base}")
    print(SEPARATOR_LINE)
    print(f"ИТОГО: {format_money(total)} {base}")


def cmd_buy(options, session):
    """buy --currency --amount."""
    user = require_login(session)
    result = usecases.buy_currency(
        user.user_id, require(options, "currency"), require(options, "amount")
    )
    code = result["currency"]
    print(
        f"Покупка выполнена: {format_amount(code, result['amount'])} {code} "
        f"по курсу {format_rate(result['rate'])} {result['base']}/{code}"
    )
    print_changes(result["changes"])
    print(
        f"Оценочная стоимость покупки: {format_money(result['total'])} {result['base']}"
    )


def cmd_sell(options, session):
    """sell --currency --amount."""
    user = require_login(session)
    result = usecases.sell_currency(
        user.user_id, require(options, "currency"), require(options, "amount")
    )
    code = result["currency"]
    print(
        f"Продажа выполнена: {format_amount(code, result['amount'])} {code} "
        f"по курсу {format_rate(result['rate'])} {result['base']}/{code}"
    )
    print_changes(result["changes"])
    print(f"Оценочная выручка: {format_money(result['total'])} {result['base']}")


def cmd_get_rate(options, session):
    """get-rate --from --to."""
    from_code = require(options, "from").upper()
    to_code = require(options, "to").upper()
    try:
        rate, updated_at = usecases.get_rate(from_code, to_code)
    except ApiRequestError as error:
        print(error)
        print(f"Курс {from_code}→{to_code} недоступен. Повторите попытку позже.")
        return
    updated = updated_at.replace("T", " ")
    print(f"Курс {from_code}→{to_code}: {format_rate(rate)} (обновлено: {updated})")
    print(f"Обратный курс {to_code}→{from_code}: {format_rate(1 / rate)}")


def cmd_currencies(options, session):
    """currencies — get_display_info() каждой валюты (полиморфизм)."""
    for code in supported_codes():
        print(CURRENCIES[code].get_display_info())


COMMANDS = {
    "register": cmd_register,
    "login": cmd_login,
    "logout": cmd_logout,
    "show-portfolio": cmd_show_portfolio,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "get-rate": cmd_get_rate,
    "currencies": cmd_currencies,
}


def execute(handler, tokens, session):
    """Выполняет команду и превращает исключения в сообщения для пользователя."""
    try:
        handler(parse_options(tokens), session)
    except InsufficientFundsError as error:
        print(error)
    except CurrencyNotFoundError as error:
        print(error)
        print(f"Поддерживаемые валюты: {', '.join(supported_codes())}")
        print("Справка: help get-rate или команда currencies")
    except ApiRequestError as error:
        print(error)
        print("Повторите попытку позже или проверьте подключение к сети.")
    except (ValueError, TypeError) as error:
        print(error)


def run():
    """Основной цикл CLI."""
    print("ValutaTrade Hub — симулятор валютного кошелька. Введите help для справки.")
    session = {"user": None}
    while True:
        try:
            line = input(PROMPT).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not line:
            continue
        try:
            command, *tokens = shlex.split(line)
        except ValueError:
            print(f"Некорректная команда: {line}")
            continue

        if command == "exit":
            break
        if command == "help":
            print_help(tokens)
            continue
        handler = COMMANDS.get(command)
        if handler is None:
            print(f"Неизвестная команда '{command}'. Введите help для справки.")
            continue
        execute(handler, tokens, session)


def main():
    """Точка входа консольной команды project."""
    setup_logging()
    run()
