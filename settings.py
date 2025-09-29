"""Configuration helpers shared across modules."""
from __future__ import annotations

import os


def _admin_ids() -> set[int]:
    """Parse administrator IDs from the environment."""
    ids = os.getenv("ADMIN_IDS", "")
    try:
        return {int(value.strip()) for value in ids.split(",") if value.strip()}
    except Exception:
        return set()


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
