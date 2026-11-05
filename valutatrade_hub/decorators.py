"""Декоратор @log_action — логирование доменных операций."""

import logging

from valutatrade_hub.core.utils import format_rate
from valutatrade_hub.logging_config import LOGGER_NAME

logger = logging.getLogger(f"{LOGGER_NAME}.actions")

AMOUNT_LOG_FORMAT = "{:.4f}"


def _format_amount(value):
    """Сумма для лога: 4 знака, если это число."""
    try:
        return AMOUNT_LOG_FORMAT.format(float(value))
    except (TypeError, ValueError):
        return repr(value)


def log_action(action, verbose=False):
    """Фабрика декораторов: пишет в лог INFO-запись об операции.

    Поля: action, user_id/username, currency, amount, rate и base (из результата),
    result=OK|ERROR, error_type и error_message при исключении.
    verbose=True добавляет изменения кошельков «было→стало».
    Исключения не глотаются: после записи в лог они пробрасываются дальше.
    """

    def decorator(func):
        """Оборачивает функцию usecases."""
        code = func.__code__
        arg_names = code.co_varnames[: code.co_argcount]

        def wrapper(*args, **kwargs):
            """Вызывает операцию и логирует её результат."""
            call_args = dict(zip(arg_names, args))
            call_args.update(kwargs)
            fields = [action]
            if "user_id" in call_args:
                fields.append(f"user_id={call_args['user_id']}")
            if "username" in call_args:
                fields.append(f"user={call_args['username']!r}")
            if "currency_code" in call_args:
                fields.append(f"currency={str(call_args['currency_code']).upper()!r}")
            if "amount" in call_args:
                fields.append(f"amount={_format_amount(call_args['amount'])}")

            try:
                result = func(*args, **kwargs)
            except Exception as error:
                fields += [
                    "result=ERROR",
                    f"error_type={type(error).__name__}",
                    f"error_message={str(error)!r}",
                ]
                logger.info(" ".join(fields))
                raise

            if isinstance(result, dict):
                if "rate" in result:
                    fields.append(f"rate={format_rate(result['rate'])}")
                if "base" in result:
                    fields.append(f"base={result['base']!r}")
                if verbose and "changes" in result:
                    changes = ", ".join(
                        f"{code_}: {before}→{after}"
                        for code_, before, after in result["changes"]
                    )
                    fields.append(f"changes=[{changes}]")
            fields.append("result=OK")
            logger.info(" ".join(fields))
            return result

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
