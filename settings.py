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


ADMIN_IDS = _admin_ids()

__all__ = ["ADMIN_IDS", "_admin_ids"]
