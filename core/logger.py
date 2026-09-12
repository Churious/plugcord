"""Logging configuration and sanitization for Plugcord."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SENSITIVE_PATTERNS = [
    re.compile(r"token\s*[:=]\s*[\w\-\.]{20,}", re.IGNORECASE),
    re.compile(r"mfa\.[\w-]{20,}", re.IGNORECASE),
]


class SensitiveDataFilter(logging.Filter):
    """Filters and redacts sensitive data such as Discord tokens from logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.sanitize(record.msg)
        if record.args:
            sanitized_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    sanitized_args.append(self.sanitize(arg))
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)
        return True

    @staticmethod
    def sanitize(text: str) -> str:
        sanitized = text
        for pattern in _SENSITIVE_PATTERNS:
            sanitized = pattern.sub("[REDACTED_TOKEN]", sanitized)
        return sanitized


def setup_logger(
    name: str = "plugcord",
    log_level: str = "INFO",
    log_file: str | Path = "logs/plugcord.log",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Configures and returns the central logger with console and rotating file handlers."""
    logger = logging.getLogger(name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sensitive_filter = SensitiveDataFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    logger.addHandler(console_handler)

    log_path = Path(log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        logger.addHandler(file_handler)
    except OSError as err:
        logger.warning(f"Could not initialize log file at {log_path}: {err}")

    return logger
