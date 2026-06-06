from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from typing import Any


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

LOG_DIR = BASE_DIR / "logs"
LOG_PATH = LOG_DIR / "noteshare.log"
LOGGER_NAME = "noteshare"
LOG_LEVEL_VALUES = {"all", "warning", "error"}
LOG_LEVEL_LABELS = {
    "all": "全部",
    "warning": "警告",
    "error": "错误",
}
_LOGGER_READY = False


def clean_log_level(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in LOG_LEVEL_VALUES:
        return normalized
    return "error"


def log_level_to_label(value: Any) -> str:
    return LOG_LEVEL_LABELS[clean_log_level(value)]


def label_to_log_level(label: str) -> str:
    normalized = str(label or "").strip()
    for value, display_label in LOG_LEVEL_LABELS.items():
        if normalized == display_label:
            return value
    return clean_log_level(normalized)


def configure_app_logger(level: Any = "error") -> logging.Logger:
    global _LOGGER_READY

    cleaned_level = clean_log_level(level)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(_to_logging_level(cleaned_level))
    logger.propagate = False

    if not _LOGGER_READY:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                LOG_PATH,
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(handler)
            _LOGGER_READY = True
        except OSError:
            logger.addHandler(logging.NullHandler())
            _LOGGER_READY = True

    for handler in logger.handlers:
        handler.setLevel(_to_logging_level(cleaned_level))

    logger.info("日志等级已设置为：%s", LOG_LEVEL_LABELS[cleaned_level])
    return logger


def get_app_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not _LOGGER_READY:
        configure_app_logger("error")
    return logger


def _to_logging_level(level: str) -> int:
    if level == "all":
        return logging.INFO
    if level == "warning":
        return logging.WARNING
    return logging.ERROR
