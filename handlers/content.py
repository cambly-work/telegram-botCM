"""Content helpers for loading and storing text snippets."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict

import yaml

from db import execute, fetch, fetchrow

logger = logging.getLogger("handlers.content")


__all__ = [
    "_CONTENT_CACHE",
    "_CONTENT_DB_CACHE",
    "_CONTENT_FILE",
    "_CONTENT_HISTORY_LIMIT",
    "_CONTENT_LAST_RELOAD",
    "_get_yaml_value",
    "_load_yaml_content",
    "get_content",
    "get_content_with_source",
    "get_content_last_update",
    "get_content_versions",
    "sanitize_html",
    "set_content_value",
]


_CONTENT_CACHE: dict = {}
_CONTENT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "content.yaml")
_CONTENT_DB_CACHE: Dict[str, str] = {}
_CONTENT_LAST_RELOAD = None
_CONTENT_HISTORY_LIMIT = 5


def sanitize_html(text: str) -> str:
    """Allow only safe HTML tags and strip other attributes."""
    if not text:
        return ""

    allowed_tags = {"b", "i", "u", "strong", "em", "code", "a"}
    tag_re = re.compile(r'<(/?)(\w+)([^>]*)>')

    def replace_tag(match: re.Match[str]) -> str:
        slash, tag, attrs = match.groups()
        if tag.lower() in allowed_tags:
            if tag.lower() == "a" and attrs:
                href_match = re.search(r'href="([^"]*)"', attrs)
                if href_match:
                    return f'<{slash}{tag} href="{href_match.group(1)}">'
            return f'<{slash}{tag}>'
        return ""

    text = tag_re.sub(replace_tag, text)
    text = re.sub(r'<[^>]*>', "", text)
    return text


def _load_yaml_content() -> dict:
    global _CONTENT_CACHE
    if _CONTENT_CACHE:
        return _CONTENT_CACHE
    try:
        with open(_CONTENT_FILE, "r", encoding="utf-8") as f:
            _CONTENT_CACHE = yaml.safe_load(f) or {}
    except FileNotFoundError:
        _CONTENT_CACHE = {}
    return _CONTENT_CACHE


def _get_yaml_value(key: str, default: str = "") -> tuple[str, bool]:
    data = _load_yaml_content()
    if not data:
        return default, False

    if "." not in key:
        if key in data:
            value = data[key]
            if isinstance(value, (list, dict)):
                return yaml.safe_dump(value, allow_unicode=True), True
            return str(value), True
        return default, False

    cur: Any = data
    try:
        for part in key.split("."):
            if isinstance(cur, list) and part.isdigit():
                cur = cur[int(part)]
            elif isinstance(cur, dict):
                cur = cur[part]
            else:
                raise KeyError(part)
    except Exception:
        return default, False

    if isinstance(cur, (list, dict)):
        return yaml.safe_dump(cur, allow_unicode=True), True
    return str(cur), True


async def get_content_with_source(key: str, default: str = "") -> tuple[str, str]:
    """Return content value along with its source (database or YAML)."""
    if key in _CONTENT_DB_CACHE:
        return _CONTENT_DB_CACHE[key], "db"

    row = await fetchrow("SELECT value FROM content WHERE key=$1", key)
    if row and row.get("value"):
        value = row["value"]
        _CONTENT_DB_CACHE[key] = value
        return value, "db"

    yaml_value, _ = _get_yaml_value(key, default)
    return yaml_value, "yaml"


async def get_content(key: str, default: str = "") -> str:
    value, _ = await get_content_with_source(key, default)
    return value


async def _write_content_version(
    key: str,
    value: str,
    updated_by: int | None,
    *,
    conn=None,
) -> None:
    try:
        if conn is not None:
            await conn.execute(
                "INSERT INTO content_versions(key, value, updated_by, updated_at) VALUES ($1,$2,$3,NOW())",
                key,
                value,
                updated_by,
            )
        else:
            await execute(
                "INSERT INTO content_versions(key, value, updated_by, updated_at) VALUES ($1,$2,$3,NOW())",
                key,
                value,
                updated_by,
            )
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("content_versions: insert failed key=%s err=%s", key, exc)


async def set_content_value(key: str, value: str, *, updated_by: int | None = None) -> None:
    """Upsert content value in the database with sanitisation."""
    value = sanitize_html(value)

    await _write_content_version(key, value, updated_by)

    updated = await fetchrow("SELECT id FROM content WHERE key=$1", key)
    if updated:
        await execute(
            "UPDATE content SET value=$2, updated_at=NOW() WHERE key=$1",
            key,
            value,
        )
    else:
        await execute(
            "INSERT INTO content(key, value, created_at, updated_at) VALUES ($1,$2,NOW(),NOW())",
            key,
            value,
        )

    _CONTENT_DB_CACHE[key] = value
    logger.info("content: set key=%s len=%s", key, len(value or ""))


async def get_content_versions(key: str, limit: int = _CONTENT_HISTORY_LIMIT) -> list[dict]:
    rows = await fetch(
        """
        SELECT id, key, value, updated_by, updated_at
        FROM content_versions
        WHERE key=$1
        ORDER BY updated_at DESC, id DESC
        LIMIT $2
        """,
        key,
        limit,
    )
    return [dict(row) for row in rows] if rows else []


async def get_content_last_update(key: str) -> dict | None:
    row = await fetchrow(
        """
        SELECT updated_at, updated_by
        FROM content_versions
        WHERE key=$1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        key,
    )
    return dict(row) if row else None
