"""Constants and helpers for admin forms statistics."""
from __future__ import annotations

from typing import Dict, Iterable

TEST_REQUEST_STATUS_ORDER: list[str] = [
    "waiting",
    "archived",
]

TEST_REQUEST_STATUS_LABELS: Dict[str, str] = {
    "waiting": "В ожидании",
    "archived": "Архив",
}

TEST_REQUEST_CLOSED_STATUSES: set[str] = {"done", "completed", "cancelled", "archived", "rejected"}


def get_status_label(status: str | None) -> str:
    """Return a human-friendly label for a status slug."""
    if not status:
        return "—"
    return TEST_REQUEST_STATUS_LABELS.get(status, status)


def all_status_labels(order: Iterable[str] | None = None) -> list[str]:
    """Return labels for provided statuses preserving order."""
    items = order or TEST_REQUEST_STATUS_ORDER
    return [TEST_REQUEST_STATUS_LABELS.get(status, status) for status in items]
