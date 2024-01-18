import sys
from collections.abc import Callable
from datetime import datetime
from typing import Any

from loguru import logger


class Logger:
    FILE_LOG_FORMAT = "<white>[{time:YYYY-MM-DD HH:mm:ss}</white>] | <white>[{extra[server]}</white>/<level>{level: <4}</level><white>]</white> | <white>{message}</white>"
    CONSOLE_LOG_FORMAT = "<white>{time:HH:mm:ss}</white> | <white>[{extra[server]}</white>/<level>{level: <4}</level><white>]</white> | <white>{message}</white>"

    main_logger = None

    def __init__(self, debug_enabled: bool = True):
        logger.remove()
        log_file_name = f'{datetime.now().strftime("%d-%m-%Y")}.log'
        log_file_path = log_file_name
        self.main_logger = logger.bind(server="MAIN")
        self.main_logger.add(log_file_path, format=self.FILE_LOG_FORMAT, level="DEBUG", rotation='1 day',
                             diagnose=False,
                             serialize=False)
        self.main_logger.add(sys.stderr, colorize=True, format=self.CONSOLE_LOG_FORMAT,
                             level='DEBUG' if debug_enabled else 'INFO', diagnose=False, serialize=False)

    def debug(self, message, *args: Any, **kwargs: Any) -> None:
        self.main_logger.debug(message, *args, **kwargs)

    def info(self, message, *args: Any, **kwargs: Any) -> None:
        self.main_logger.info(message, *args, **kwargs)

    def success(self, message, *args: Any, **kwargs: Any) -> None:
        self.main_logger.success(message, *args, **kwargs)

    def warning(self, message, *args: Any, **kwargs: Any) -> None:
        self.main_logger.warning(message, *args, **kwargs)

    def error(self, message, *args: Any, **kwargs: Any) -> None:
        self.main_logger.error(message, *args, **kwargs)

    def critical(self, message, *args: Any, **kwargs: Any) -> None:
        self.main_logger.critical(message, *args, **kwargs)

    def bind(self, **kwargs: Any) -> logger:
        self.main_logger = self.main_logger.bind(**kwargs)
        return self.main_logger

    def patch(self, patcher: Callable) -> logger:
        self.main_logger = self.main_logger.patch(patcher)
        return self.main_logger
