"""Командный интерфейс: разбор команд, вывод результатов и сообщений об ошибках."""

import logging
import shlex

from prettytable import PrettyTable

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
    format_rate_compact,
)
from valutatrade_hub.logging_config import (
    PARSER_LOGGER_NAME,
    console_handler,
    setup_logging,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.scheduler import RatesScheduler
from valutatrade_hub.parser_service.updater import create_updater

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
    "update-rates": "update-rates [--source coingecko|exchangerate] — обновить курсы",
    "show-rates": "show-rates [--currency <код>] [--top <N>] [--base <код>] — курсы",
    "rates-history": "rates-history --currency <код> [--limit <N>] — история курса",
    "schedule-updates": "schedule-updates [--interval <сек>] [--times <N>] — авто",
    "currencies": "currencies — список поддерживаемых валют",
    "help": "help [команда] — справка",
    "exit": "exit — выход из программы",
}


def print_help(options_tokens):
    """help или help <команда>."""
    if options_tokens and options_tokens[0] in COMMAND_HELP:
        print(COMMAND_HELP[options_tokens[0]])
        if options_tokens[0] in ("get-rate", "buy", "sell", "show-rates"):
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
    updated = updated_at.replace("T", " ").removesuffix("Z")
    print(f"Курс {from_code}→{to_code}: {format_rate(rate)} (обновлено: {updated})")
    print(f"Обратный курс {to_code}→{from_code}: {format_rate(1 / rate)}")
    print_stale_warning()


def print_stale_warning():
    """Предупреждение, если кеш курсов старше TTL."""
    if usecases.rates_are_stale():
        print("Внимание: курсы в кеше устарели. Выполните 'update-rates'.")


def run_with_console_log(action):
    """Выполняет action, дублируя логи Parser Service в консоль."""
    parser_logger = logging.getLogger(PARSER_LOGGER_NAME)
    handler = console_handler()
    parser_logger.addHandler(handler)
    try:
        return action()
    finally:
        parser_logger.removeHandler(handler)


def cmd_update_rates(options, session):
    """update-rates [--source coingecko|exchangerate]."""
    updater = create_updater(options.get("source"))
    try:
        summary = run_with_console_log(updater.run_update)
    except ApiRequestError as error:
        print(f"Update failed: {error}")
        print("Check logs/parser.log for details.")
        return
    if summary["errors"]:
        print("Update completed with errors. Check logs/parser.log for details.")
    else:
        print(
            f"Update successful. Total rates updated: {summary['updated']}. "
            f"Last refresh: {summary['last_refresh']}"
        )


def cmd_show_rates(options, session):
    """show-rates [--currency] [--top] [--base]."""
    pairs, last_refresh = usecases.list_rates(
        options.get("currency"), options.get("top"), options.get("base")
    )
    print(f"Rates from cache (updated at {last_refresh}):")
    for pair, rate in pairs:
        print(f"- {pair}: {format_rate_compact(rate)}")
    print_stale_warning()


def cmd_rates_history(options, session):
    """rates-history --currency [--limit] — таблица PrettyTable."""
    limit = options.get("limit", "10")
    if not limit.isdigit() or int(limit) == 0:
        raise ValueError("'limit' должен быть целым положительным числом")
    records = usecases.rate_history(require(options, "currency"), int(limit))
    if not records:
        print("История пуста. Выполните 'update-rates'.")
        return
    table = PrettyTable()
    table.field_names = ["Пара", "Курс", "Время (UTC)", "Источник"]
    for record in records:
        table.add_row(
            [
                f"{record['from_currency']}_{record['to_currency']}",
                format_rate_compact(record["rate"]),
                record["timestamp"],
                record["source"],
            ]
        )
    print(table)


def cmd_schedule_updates(options, session):
    """schedule-updates [--interval] [--times] — периодическое обновление."""
    interval = options.get("interval", str(ParserConfig().UPDATE_INTERVAL_SECONDS))
    times = options.get("times")
    if not interval.isdigit() or (times is not None and not times.isdigit()):
        raise ValueError("'interval' и 'times' должны быть целыми положительными")
    scheduler = RatesScheduler(create_updater(), int(interval))
    print(f"Автообновление каждые {interval} с. Остановить: Ctrl+C")
    try:
        done = run_with_console_log(
            lambda: scheduler.run(int(times) if times else None)
        )
    except KeyboardInterrupt:
        scheduler.stop()
        print("\nАвтообновление остановлено.")
        return
    print(f"Автообновление завершено: выполнено обновлений — {done}.")


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
    "update-rates": cmd_update_rates,
    "show-rates": cmd_show_rates,
    "rates-history": cmd_rates_history,
    "schedule-updates": cmd_schedule_updates,
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
