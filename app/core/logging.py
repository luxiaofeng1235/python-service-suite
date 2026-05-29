"""
============================================
日志配置模块
============================================
统一配置控制台日志、文件日志和按天切割。
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

from app.core.config import settings


def setup_logging() -> None:
    """初始化应用日志"""
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    app_file_handler = TimedRotatingFileHandler(
        filename=os.path.join(settings.LOG_DIR, "app.log"),
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(formatter)
    app_file_handler.setLevel(log_level)
    root_logger.addHandler(app_file_handler)

    request_file_handler = TimedRotatingFileHandler(
        filename=os.path.join(settings.LOG_DIR, "request.log"),
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    request_file_handler.setFormatter(formatter)
    request_file_handler.setLevel(log_level)

    request_logger = logging.getLogger("app.request")
    request_logger.handlers.clear()
    request_logger.setLevel(log_level)
    request_logger.propagate = False
    request_logger.addHandler(console_handler)
    request_logger.addHandler(request_file_handler)

    slow_file_handler = TimedRotatingFileHandler(
        filename=os.path.join(settings.LOG_DIR, "slow_request.log"),
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    slow_file_handler.setFormatter(formatter)
    slow_file_handler.setLevel(logging.WARNING)

    slow_logger = logging.getLogger("app.request.slow")
    slow_logger.handlers.clear()
    slow_logger.setLevel(logging.WARNING)
    slow_logger.propagate = False
    slow_logger.addHandler(console_handler)
    slow_logger.addHandler(slow_file_handler)
