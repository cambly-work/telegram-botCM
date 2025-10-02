"""Configuration helpers shared across modules."""
from __future__ import annotations

import logging
import os
import re


LOGGER = logging.getLogger(__name__)


def _admin_ids() -> set[int]:
    """Parse administrator IDs from the environment."""
    ids = os.getenv("ADMIN_IDS", "")
    parsed_ids: set[int] = set()
    for raw_value in re.split(r"[\s,]+", ids):
        value = raw_value.strip()
        if not value:
            continue
        try:
            parsed_ids.add(int(value))
        except ValueError:
            LOGGER.warning("Invalid ADMIN_IDS token: %r", value)
    return parsed_ids


def _env_str(name: str, default: str = "") -> str:
    """Return an environment variable stripped of whitespace."""
    return os.getenv(name, default).strip()


ADMIN_IDS = _admin_ids()
YOOMONEY_CHECKOUT_URL = _env_str("YOOMONEY_CHECKOUT_URL")
YOOMONEY_WEBHOOK_SECRET = _env_str("YOOMONEY_WEBHOOK_SECRET")

__all__ = [
    "ADMIN_IDS",
    "YOOMONEY_CHECKOUT_URL",
    "YOOMONEY_WEBHOOK_SECRET",
    "_admin_ids",
    "_env_str",
]
