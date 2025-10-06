"""Configuration helpers for the handlers package."""
from __future__ import annotations

import logging
import os
from zoneinfo import ZoneInfo

logger = logging.getLogger("handlers.config")

BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Europe/Moscow")
WELCOME_POST_URL = os.getenv("WELCOME_POST_URL", "https://t.me/")
TEST_FORM_URL = os.getenv(
    "TEST_FORM_URL",
    "https://forms.gle/iNcUGfiLGNkLW1dc8",
)
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@Tokyo_tokyo")
AT_PRODUCT_ID_CLUB = os.getenv("AT_PRODUCT_ID_CLUB", "")
CLUB_CHAT_ID = os.getenv("CLUB_CHAT_ID", "")  # ID приватной группы/канала (опц.)
BOT_VERSION = "1.0.0"

try:
    BOT_ZONE = ZoneInfo(BOT_TIMEZONE)
except Exception:  # pragma: no cover - fallback for misconfiguration
    logger.warning("Invalid BOT_TIMEZONE=%s, falling back to Europe/Moscow", BOT_TIMEZONE)
    BOT_ZONE = ZoneInfo("Europe/Moscow")

__all__ = [
    "BOT_TIMEZONE",
    "WELCOME_POST_URL",
    "TEST_FORM_URL",
    "SUPPORT_CONTACT",
    "AT_PRODUCT_ID_CLUB",
    "CLUB_CHAT_ID",
    "BOT_VERSION",
    "BOT_ZONE",
]
