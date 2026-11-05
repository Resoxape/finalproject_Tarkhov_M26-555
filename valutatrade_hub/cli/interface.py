"""Командный интерфейс: разбор команд и вывод результатов."""

import shlex

from valutatrade_hub.core import usecases
from valutatrade_hub.core.utils import (
    BASE_CURRENCY,
    format_amount,
    format_money,
    format_rate,
)

PROMPT = "> "
SEPARATOR_LINE = "-" * 33
OPTION_PREFIX = "--"

HELP_TEXT = """Команды:
  register --username <имя> --password <пароль>  регистрация
  login --username <имя> --password <пароль>     вход
  logout                                         выход из аккаунта
  show-portfolio [--base <валюта>]               портфель и итоговая стоимость
  buy --currency <код> --amount <количество>     купить валюту (оплата из USD)
  sell --currency <код> --amount <количество>    продать валюту (выручка в USD)
  get-rate --from <код> --to <код>               курс валюты
  help                                           справка
  exit                                           выход из программы"""


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
    base = options.get("base", BASE_CURRENCY).upper()
    rows, total = usecases.show_portfolio(user, base)
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
        user, require(options, "currency"), require(options, "amount")
    )
    code = result["currency"]
    print(
        f"Покупка выполнена: {format_amount(code, result['amount'])} {code} "
        f"по курсу {format_rate(result['rate'])} {BASE_CURRENCY}/{code}"
    )
    print_changes(result["changes"])
    print(f"Оценочная стоимость покупки: {format_money(result['total'])} USD")


def cmd_sell(options, session):
    """sell --currency --amount."""
    user = require_login(session)
    result = usecases.sell_currency(
        user, require(options, "currency"), require(options, "amount")
    )
    code = result["currency"]
    print(
        f"Продажа выполнена: {format_amount(code, result['amount'])} {code} "
        f"по курсу {format_rate(result['rate'])} {BASE_CURRENCY}/{code}"
    )
    print_changes(result["changes"])
    print(f"Оценочная выручка: {format_money(result['total'])} USD")


def cmd_get_rate(options, session):
    """get-rate --from --to."""
    from_code = require(options, "from").upper()
    to_code = require(options, "to").upper()
    rate, updated_at = usecases.get_rate(from_code, to_code)
    updated = updated_at.replace("T", " ")
    print(f"Курс {from_code}→{to_code}: {format_rate(rate)} (обновлено: {updated})")
    print(f"Обратный курс {to_code}→{from_code}: {format_rate(1 / rate)}")


COMMANDS = {
    "register": cmd_register,
    "login": cmd_login,
    "logout": cmd_logout,
    "show-portfolio": cmd_show_portfolio,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "get-rate": cmd_get_rate,
}


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
            print(HELP_TEXT)
            continue
        handler = COMMANDS.get(command)
        if handler is None:
            print(f"Неизвестная команда '{command}'. Введите help для справки.")
            continue
        try:
            handler(parse_options(tokens), session)
        except (ValueError, TypeError) as error:
            print(error)


def main():
    """Точка входа консольной команды project."""
    run()
