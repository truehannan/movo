"""Logging configuration with mandatory secret masking (PROMPT sections 20, 26).

The application must never log the API key, passwords, or typed secrets. This
module installs a logging filter that redacts anything matching known secret
patterns, as a defence-in-depth backstop even if a caller is careless.
"""

from __future__ import annotations

import logging
import re

_LOGGER_NAME = "jev"

# Patterns that, if they ever reach a log record, must be redacted.
_SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{6,})"),
    re.compile(r"(ts-[A-Za-z0-9_\-]{6,})"),
    re.compile(r"(TYPESAFE_API_KEY\s*=\s*)(\S+)", re.IGNORECASE),
]


class _RedactingFilter(logging.Filter):
    """Redacts secret-looking substrings from every log record's message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = msg
        for pat in _SECRET_PATTERNS:
            if pat.groups >= 2:
                redacted = pat.sub(r"\1****", redacted)
            else:
                redacted = pat.sub("****", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(debug: bool = False) -> logging.Logger:
    """Configure and return the application logger. Idempotent."""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S")
        )
        handler.addFilter(_RedactingFilter())
        logger.addHandler(handler)
        logger.propagate = False
    else:
        logger.setLevel(logging.DEBUG if debug else logging.INFO)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
