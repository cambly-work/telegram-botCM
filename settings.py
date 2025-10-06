"""Configuration helpers shared across modules."""
from __future__ import annotations

import logging
import os
import re


LOGGER = logging.getLogger(__name__)


def _parse_ids(value: str, *, source: str = "ID list") -> set[int]:
    """Extract integer identifiers from a free-form string."""

    parsed_ids: set[int] = set()
    tokens = re.findall(r"[^\s,;]+", value)

    for token in tokens:
        matches = re.findall(r"-?\d+", token)
        if not matches:
            LOGGER.warning("Invalid %s token: %r", source, token)
            continue

        for match in matches:
            try:
                parsed_ids.add(int(match))
            except ValueError:
                LOGGER.warning("Invalid %s token: %r", source, token)
                break

    return parsed_ids


def _admin_ids() -> set[int]:
    """Parse administrator IDs from the environment."""
    ids = os.getenv("ADMIN_IDS", "")
    return _parse_ids(ids, source="ADMIN_IDS")


def _env_str(name: str, default: str = "") -> str:
    """Return an environment variable stripped of whitespace."""
    return os.getenv(name, default).strip()


ADMIN_IDS = _admin_ids()
STAFF_ADMIN_IDS = _parse_ids(os.getenv("STAFF_ADMIN_IDS", ""), source="STAFF_ADMIN_IDS")
YOOMONEY_CHECKOUT_URL = _env_str("YOOMONEY_CHECKOUT_URL")
YOOMONEY_WEBHOOK_SECRET = _env_str("YOOMONEY_WEBHOOK_SECRET")

__all__ = [
    "ADMIN_IDS",
    "STAFF_ADMIN_IDS",
    "YOOMONEY_CHECKOUT_URL",
    "YOOMONEY_WEBHOOK_SECRET",
    "_admin_ids",
    "_parse_ids",
    "_env_str",
]
