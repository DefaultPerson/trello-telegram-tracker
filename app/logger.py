import logging
import sys
import textwrap
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("app_logger")
sqlalchemy_loggers = [
    logging.getLogger("sqlalchemy.engine.Engine"),
]
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[94m",
        "INFO": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[95m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


class WrappingFormatter(logging.Formatter):
    def format(self, record):
        message = super().format(record)
        if record.exc_info:
            exception_info = self.formatException(record.exc_info)
            message = f"{message}\n{exception_info}"
        wrapped_message = "\n".join(textwrap.wrap(message, width=100))
        return wrapped_message


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("bot_access_manager.log"),
        ],
    )

    # Set warning level for aiogram network errors
    logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)

    logging_errors = logging.getLogger("logging_errors")
    logging_errors.setLevel(logging.WARNING)
    ch_errors = logging.StreamHandler()
    ch_errors.setLevel(logging.WARNING)
    formatter_errors = ColoredFormatter(
        "%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch_errors.setFormatter(formatter_errors)
    logging_errors.handlers = []
    logging_errors.addHandler(ch_errors)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = ColoredFormatter(
        "%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch.setFormatter(formatter)

    fh = RotatingFileHandler(
        "app.log",
        mode="a",
        maxBytes=2 * 1024 * 1024,
        backupCount=4,
        encoding="utf-8",
    )
    fh.setLevel(logging.INFO)
    file_formatter = WrappingFormatter(
        "%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(file_formatter)

    logging.basicConfig(level=logging.INFO, handlers=[ch, fh])

    for sa_logger in sqlalchemy_loggers:
        sa_logger.setLevel(logging.WARN)
        sa_logger.addHandler(ch)
        sa_logger.addHandler(fh)
