# handlers.py
import asyncio
import io
import json
import math
import os
import re
import yaml
import logging
import time
import html
from collections import OrderedDict
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Iterable, Dict, List, Callable, Awaitable, Any
from aiogram import Router, F, types
from aiogram.enums import ParseMode
from aiogram.types import ReplyKeyboardMarkup, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.utils.chat_action import ChatActionSender
from aiogram.exceptions import TelegramRetryAfter

try:
    from aiogram.exceptions import EventSkip
except ImportError:  # aiogram < 3.13.1 compatibility
    from aiogram.dispatcher.event.bases import SkipHandler as EventSkip
from urllib.parse import parse_qs, urlparse
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from db import fetchrow, fetch, execute, transaction
from settings import ADMIN_IDS, YOOMONEY_CHECKOUT_URL
from keyboards import (
    main_menu_keyboard,
    info_menu_keyboard,
    learning_menu_keyboard,
    materials_menu_keyboard,
    profile_menu_keyboard,
    lessons_overview_keyboard,
    lesson_actions_keyboard,
    after_lesson_keyboard,
    feedback_keyboard,
    cancel_keyboard,
    admin_main_keyboard,
    admin_settings_keyboard,
    admin_content_keyboard,
    admin_content_suggestions_keyboard,
    admin_content_versions_keyboard,
    admin_text_groups_keyboard,
    admin_text_items_keyboard,
    admin_behavior_keyboard,
    admin_onboarding_steps_keyboard,
    admin_onboarding_delete_keyboard,
    admin_broadcast_keyboard,
    admin_broadcast_confirm_keyboard,
    admin_broadcast_templates_keyboard,
    admin_broadcast_delete_keyboard,
    BROADCAST_TEMPLATE_PREFIX,
    BACK_TO_MAIN,
    BACK_TO_LEARNING,
    BACK_TO_ADMIN,
    BACK_TO_TEXT_GROUPS,
    BACK_TO_LESSONS,
    BACK_TO_BEHAVIOR,
    BACK_TO_ONBOARDING,
    LESSON_DONE,
    LESSON_SKIP,
    LESSON_QUESTION,
    NEXT_LESSON,
    WRITE_FEEDBACK,
    SKIP_FEEDBACK,
    FEEDBACK_OPTIONS,
    CANCEL_TEXT,
    ADMIN_TEXTS_ENTRY,
    ADMIN_CONTENT_MENU,
    ADMIN_CONTENT_VIEW,
    ADMIN_CONTENT_CREATE,
    ADMIN_CONTENT_HISTORY,
    ADMIN_CONTENT_SUGGEST_MORE,
    ADMIN_CONTENT_SAVE_TEMPLATE_BUTTON,
    ADMIN_CONTENT_TAGS_HELP,
    ADMIN_CONTENT_ROLLBACK_PREFIX,
    ADMIN_CONTENT_EXPORT,
    ADMIN_CONTENT_IMPORT,
    ADMIN_USERS_BUTTON,
    ADMIN_BROADCAST_BUTTON,
    ADMIN_BEHAVIOR_BUTTON,
    BROADCAST_ALL_BUTTON,
    BROADCAST_LEADS_BUTTON,
    BROADCAST_MEMBERS_BUTTON,
    BROADCAST_EXPIRED_BUTTON,
    BROADCAST_TEMPLATES_BUTTON,
    SEND_BROADCAST_BUTTON,
    EDIT_BROADCAST_BUTTON,
    SAVE_BROADCAST_TEMPLATE_BUTTON,
    CHANGE_BROADCAST_SEGMENT_BUTTON,
    BACK_TO_BROADCAST,
    DELETE_BROADCAST_TEMPLATE_BUTTON,
    ADD_ONBOARDING_STEP,
    DELETE_ONBOARDING_STEP,
    ADMIN_BEHAVIOR_START,
    ADMIN_BEHAVIOR_REGISTRATION,
    ADMIN_BEHAVIOR_ONBOARDING,
    ADMIN_STATS_BUTTON,
    ADMIN_DEBUG_BUTTON,
    ADMIN_SETTINGS_BUTTON,
    ADMIN_PAYMENTS_BUTTON,
    admin_users_segments_keyboard,
    admin_users_pagination_keyboard,
    admin_user_card_keyboard,
    ADMIN_USERS_SEGMENT_LEADS,
    ADMIN_USERS_SEGMENT_ACTIVE,
    ADMIN_USERS_SEGMENT_EXPIRED,
    ADMIN_USERS_PAGE_PREV,
    ADMIN_USERS_PAGE_NEXT,
    ADMIN_USERS_BACK_TO_SEGMENTS,
    ADMIN_USERS_BACK_TO_LIST,
    ADMIN_USERS_GRANT_ACCESS,
    ADMIN_USERS_REVOKE_ACCESS,
    ADMIN_USERS_UPDATE_CONTACTS,
    admin_stats_keyboard,
    admin_payments_keyboard,
    ADMIN_PAYMENTS_OPEN_WINDOW,
    ADMIN_PAYMENTS_CLOSE_WINDOW,
    ADMIN_PAYMENTS_SHOW_LATEST,
    ADMIN_PAYMENTS_CONFIRM_ACCESS,
    ADMIN_PAYMENTS_REVOKE_ACCESS,
    ADMIN_PAYMENTS_MARK_PAID,
    ADMIN_PAYMENTS_MARK_FAILED,
    ADMIN_STATS_REFRESH,
    ADMIN_STATS_USERS_BREAKDOWN,
    ADMIN_STATS_LESSON_PROGRESS,
    ADMIN_STATS_PAYMENTS_BREAKDOWN,
    ADMIN_STATS_RECENT_PAYMENTS,
    ADMIN_STATS_FORMS_BREAKDOWN,
)
# ──────────────────────────────────────────────────────────────────────────────
# Логгер
# ──────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("handlers")


_notify_admins_cached: Optional[Callable[[str], Awaitable[None]]] = None


FORM_SLUG_ANALYSIS = "analysis"
FORM_SLUG_TEST = "test"
FORM_LABELS: dict[str, str] = {
    FORM_SLUG_ANALYSIS: "заявка на разбор",
    FORM_SLUG_TEST: "тест по уровню",
}
FORM_ALIASES: dict[str, str] = {
    FORM_SLUG_ANALYSIS: FORM_SLUG_ANALYSIS,
    FORM_SLUG_TEST: FORM_SLUG_TEST,
    "разбор": FORM_SLUG_ANALYSIS,
    "анкета": FORM_SLUG_ANALYSIS,
    "analysis": FORM_SLUG_ANALYSIS,
    "test": FORM_SLUG_TEST,
    "тест": FORM_SLUG_TEST,
    "magnetism-window": "magnetism-window",
    "magnetism_window": "magnetism-window",
}
# ──────────────────────────────────────────────────────────────────────────────
# Конфиг из окружения
# ──────────────────────────────────────────────────────────────────────────────
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


def is_admin_id(user_id: int | str | None) -> bool:
    if user_id is None:
        return False
    try:
        return int(user_id) in ADMIN_IDS
    except (ValueError, TypeError):
        return False
# ──────────────────────────────────────────────────────────────────────────────
# Мидлвара для throttling
# ──────────────────────────────────────────────────────────────────────────────
class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, limit=3, window=5.0):
        super().__init__()
        self.limit = limit
        self.window = window
        self.bucket = {}  # uid -> [timestamps]
    async def __call__(self, handler, event: types.TelegramObject, data):
        uid = None
        if hasattr(event, "from_user") and event.from_user:
            uid = event.from_user.id
        if uid:
            now = time.monotonic()
            q = self.bucket.get(uid, [])
            q = [t for t in q if now - t <= self.window]
            if len(q) >= self.limit:
                logger.warning(f"Throttled user {uid}, update_id: {event.update_id}")
                return
            q.append(now)
            self.bucket[uid] = q
        return await handler(event, data)
# ──────────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────────
def sanitize_html(text: str) -> str:
    """Разрешаем только безопасные теги и удаляем атрибуты"""
    if not text:
        return ""
    
    # Разрешенные теги
    allowed_tags = {"b", "i", "u", "strong", "em", "code", "a"}
    
    # Регулярка для поиска тегов
    tag_re = re.compile(r'<(/?)(\w+)([^>]*)>')
    
    def replace_tag(match):
        slash, tag, attrs = match.groups()
        if tag.lower() in allowed_tags:
            if tag.lower() == "a" and attrs:
                # Для ссылок оставляем href
                href_match = re.search(r'href="([^"]*)"', attrs)
                if href_match:
                    return f'<{slash}{tag} href="{href_match.group(1)}">'
            return f'<{slash}{tag}>'
        return ""
    
    # Обрабатываем теги
    text = tag_re.sub(replace_tag, text)

    # Удаляем все остальные HTML-теги
    text = re.sub(r'<[^>]*>', '', text)

    return text


_SHORTCUT_LINK_RE = re.compile(r"(?<!\\)\[([^\]]+)\]\(([^)]+)\)")
_SHORTCUT_CODE_RE = re.compile(r"(?<!\\)`([^`]+)`")
_SHORTCUT_BOLD_RE = re.compile(r"(?<!\\)\*\*(.+?)\*\*(?!\*)", re.S)
_SHORTCUT_UNDERLINE_RE = re.compile(r"(?<!\\)__(.+?)__(?!_)", re.S)
_SHORTCUT_ITALIC_RE = re.compile(r"(?<!\\)(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", re.S)
_SHORTCUT_ESCAPE_RE = re.compile(r"\\([*_`\[\]()])")

_URL_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
_FORM_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9_-]+", re.IGNORECASE)


def _lookup_form_alias(value: str) -> Optional[str]:
    cleaned = (value or "").strip()
    if not cleaned:
        return None

    lowered = cleaned.lower()
    candidates = [lowered]

    replaced = lowered.replace("-", "_")
    if replaced not in candidates:
        candidates.append(replaced)

    collapsed = re.sub(r"\s+", "_", replaced)
    if collapsed not in candidates:
        candidates.append(collapsed)

    for candidate in candidates:
        alias = FORM_ALIASES.get(candidate)
        if alias:
            return alias

    return None


def _sanitize_form_slug(candidate: str) -> str:
    cleaned = (candidate or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("=", " ").replace("/", " ").replace("\u202f", " ")
    cleaned = cleaned.lower().replace(" ", "-")
    cleaned = _FORM_SLUG_SANITIZE_RE.sub("-", cleaned)
    return cleaned.strip("-")[:64]


def extract_first_url(text: str) -> Optional[str]:
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    url = match.group(0).rstrip("),.;]")
    return url


def resolve_form_slug(raw_value: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    candidates: list[str] = []
    raw = (raw_value or "").strip()
    if raw:
        if raw.startswith(("http://", "https://")):
            try:
                parsed = urlparse(raw)
                query = parse_qs(parsed.query or "")
                for key in ("form_slug", "slug", "form", "f"):
                    values = query.get(key)
                    if values:
                        candidates.extend(values)
                if parsed.fragment:
                    candidates.append(parsed.fragment)
            except Exception:
                candidates.append(raw)
        else:
            if "=" in raw:
                _, _, value = raw.partition("=")
                if value:
                    candidates.append(value)
            candidates.append(raw)
    if fallback:
        candidates.append(fallback)

    for candidate in candidates:
        alias = _lookup_form_alias(candidate)
        if alias:
            return alias

        slug = _sanitize_form_slug(candidate)
        if slug:
            alias = _lookup_form_alias(slug)
            if alias:
                return alias
            return slug
    return None


def apply_formatting_shortcuts(text: str) -> str:
    """Преобразует простые маркдауно-подобные сокращения в HTML-теги."""
    if not text:
        return ""

    result = text

    # Сохраняем исходные HTML-теги, чтобы не испортить атрибуты с подчёркиваниями и звёздочками
    html_tags: list[str] = []

    def _store_tag(match: re.Match[str]) -> str:
        html_tags.append(match.group(0))
        return f"__HTMLTAG_{len(html_tags) - 1}__"

    result = re.sub(r"<[^>]+>", _store_tag, result)

    def _link_repl(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        url = match.group(2).strip()
        if not url:
            return match.group(0)
        safe_url = html.escape(url, quote=True)
        return f'<a href="{safe_url}">{label}</a>'

    result = _SHORTCUT_LINK_RE.sub(_link_repl, result)
    result = _SHORTCUT_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", result)
    result = _SHORTCUT_BOLD_RE.sub(lambda m: f"<b>{m.group(1)}</b>", result)
    result = _SHORTCUT_UNDERLINE_RE.sub(lambda m: f"<u>{m.group(1)}</u>", result)
    result = _SHORTCUT_ITALIC_RE.sub(lambda m: f"<i>{m.group(1)}</i>", result)
    result = _SHORTCUT_ESCAPE_RE.sub(lambda m: m.group(1), result)

    if html_tags:
        def _restore_tag(match: re.Match[str]) -> str:
            idx = int(match.group(1))
            if 0 <= idx < len(html_tags):
                return html_tags[idx]
            return match.group(0)

        result = re.sub(r"__HTMLTAG_(\d+)__", _restore_tag, result)

    return result


def prepare_admin_text_input(raw_text: str | None) -> str:
    """Очищает ввод администратора и приводит его к безопасному HTML."""
    if raw_text is None:
        return ""
    cleaned = raw_text.strip()
    if not cleaned:
        return ""
    formatted = apply_formatting_shortcuts(cleaned)
    return sanitize_html(formatted)


def render_content(text: str, **placeholders: str) -> str:
    """Заменяет плейсхолдеры вида {name} и {{NAME}} на значения."""
    if not text:
        return ""

    rendered = text
    for key, value in placeholders.items():
        replacement = value or ""
        tokens = {
            f"{{{key}}}",
            f"{{{key.upper()}}}",
            f"{{{{{key}}}}}",
            f"{{{{{key.upper()}}}}}",
        }
        for token in tokens:
            rendered = rendered.replace(token, replacement)
    return rendered


_MONTHS_RU: dict[str, int] = {
    "январь": 1,
    "января": 1,
    "янв": 1,
    "февраль": 2,
    "февраля": 2,
    "фев": 2,
    "март": 3,
    "марта": 3,
    "мар": 3,
    "апрель": 4,
    "апреля": 4,
    "апр": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июн": 6,
    "июль": 7,
    "июля": 7,
    "июл": 7,
    "август": 8,
    "августа": 8,
    "авг": 8,
    "сен": 9,
    "сент": 9,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "окт": 10,
    "ноябрь": 11,
    "ноября": 11,
    "ноя": 11,
    "декабрь": 12,
    "декабря": 12,
    "дек": 12,
}


def _normalize_year(value: str) -> int:
    year = int(value)
    if len(value) >= 4:
        return year
    current_year = datetime.now().year % 100
    if year <= current_year:
        return 2000 + year
    return 1900 + year


def _safe_birthdate(year: int, month: int, day: int) -> Optional[date]:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if parsed > date.today():
        return None
    return parsed


def parse_birthdate(text: str | None) -> Optional[date]:
    """Парсит дату рождения в распространённых форматах."""
    if not text:
        return None
    cleaned = text.strip().lower()
    if not cleaned:
        return None

    cleaned = cleaned.replace("г.", "").replace("г", "")
    cleaned = cleaned.replace(",", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)

    match = re.match(r"^(\d{1,2})\s+([а-яё]+)\s+(\d{2,4})$", cleaned)
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year_value = match.group(3)
        month = _MONTHS_RU.get(month_name)
        if month:
            return _safe_birthdate(_normalize_year(year_value), month, day)

    digits = re.findall(r"\d+", cleaned)
    if len(digits) == 3:
        if len(digits[0]) == 4:
            year_val, month_val, day_val = digits
        else:
            day_val, month_val, year_val = digits
        return _safe_birthdate(
            _normalize_year(year_val),
            int(month_val),
            int(day_val),
        )

    return None


def _preview_text_for_admin(text: str, limit: int = 1500) -> str:
    """Формирует короткий превью-текст для сообщений админки."""
    if not text:
        return "(пусто)"

    trimmed = text.strip()
    if len(trimmed) <= limit:
        return html.escape(trimmed)

    return html.escape(trimmed[:limit]) + "…"


async def log_admin_action(admin_id: int, action: str, payload: dict = None):
    """Логирование админских действий в admin_log"""
    try:
        await execute(
            """INSERT INTO admin_log (admin_id, action, payload, created_at)
               VALUES ($1, $2, $3, NOW())""",
            admin_id, action, payload
        )
        logger.info(f"Admin action logged: {action} by {admin_id}")
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")


async def mark_form_started(user_id: int, slug: Optional[str]) -> None:
    normalized = resolve_form_slug(slug)
    if not user_id or not normalized:
        return
    try:
        await execute(
            """
            INSERT INTO form_sessions (user_id, form_slug, started_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id, form_slug) DO UPDATE
            SET started_at = COALESCE(form_sessions.started_at, EXCLUDED.started_at)
            """,
            user_id,
            normalized,
        )
    except Exception as e:
        logger.warning(
            "mark_form_started failed: user_id=%s slug=%s err=%s",
            user_id,
            normalized,
            e,
        )


async def mark_form_completed(user_id: int, slug: Optional[str]) -> tuple[Optional[dict], bool]:
    normalized = resolve_form_slug(slug)
    if not user_id or not normalized:
        return None, False

    try:
        existing = await fetchrow(
            "SELECT * FROM form_sessions WHERE user_id=$1 AND form_slug=$2",
            user_id,
            normalized,
        )
        row = await fetchrow(
            """
            INSERT INTO form_sessions (user_id, form_slug, started_at, completed_at, last_reminder_at, reminder_count)
            VALUES ($1, $2, COALESCE($3, NOW()), NOW(), NULL, 0)
            ON CONFLICT (user_id, form_slug) DO UPDATE
            SET completed_at = NOW(),
                started_at = COALESCE(form_sessions.started_at, EXCLUDED.started_at),
                last_reminder_at = NULL,
                reminder_count = 0
            RETURNING *
            """,
            user_id,
            normalized,
            existing.get("started_at") if existing else None,
        )
        return row, existing is None
    except Exception as e:
        logger.warning(
            "mark_form_completed failed: user_id=%s slug=%s err=%s",
            user_id,
            normalized,
            e,
        )
        return None, False


async def upsert_test_request(
    *,
    tg_user_id: int,
    user_id: Optional[int],
    birthdate: date,
    preferred_name: Optional[str],
) -> Optional[dict]:
    try:
        return await fetchrow(
            """
            INSERT INTO test_requests (tg_user_id, user_id, birthdate, preferred_name, status)
            VALUES ($1, $2, $3, $4, 'waiting')
            ON CONFLICT (tg_user_id) DO UPDATE
            SET user_id = COALESCE(EXCLUDED.user_id, test_requests.user_id),
                birthdate = EXCLUDED.birthdate,
                preferred_name = EXCLUDED.preferred_name,
                status = 'waiting',
                updated_at = NOW()
            RETURNING *
            """,
            tg_user_id,
            user_id,
            birthdate,
            preferred_name,
        )
    except Exception as e:
        logger.warning(
            "test_request upsert failed: tg_user_id=%s err=%s",
            tg_user_id,
            e,
        )
        return None


def _get_notify_admins() -> Optional[Callable[[str], Awaitable[None]]]:
    global _notify_admins_cached
    if _notify_admins_cached is not None:
        return _notify_admins_cached
    try:
        from app import notify_admins as _notify_admins  # type: ignore
    except Exception:
        _notify_admins_cached = None
        return None
    _notify_admins_cached = _notify_admins
    return _notify_admins_cached


def _format_birthdate(birthdate: date) -> str:
    return birthdate.strftime("%d.%m.%Y")
# ──────────────────────────────────────────────────────────────────────────────
# Контент: content.yaml + БД content (fallback-логика)
# ──────────────────────────────────────────────────────────────────────────────
_CONTENT_CACHE: dict = {}
_CONTENT_FILE = os.path.join(os.path.dirname(__file__), "content.yaml")
_CONTENT_DB_CACHE: Dict[str, str] = {}
_CONTENT_LAST_RELOAD = None
_CONTENT_HISTORY_LIMIT = 5


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
async def get_content_with_source(key: str, default: str = "") -> tuple[str, str]:
    """Возвращает значение контента и источник (БД или YAML-шаблон)."""
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
    """
    1) Пытаемся достать из БД content.value по key.
    2) Если нет — из content.yaml (поддержка вложенных ключей "onboarding.0").
    """
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
    except Exception as exc:
        logger.warning("content_versions: insert failed key=%s err=%s", key, exc)


async def set_content_value(key: str, value: str, *, updated_by: int | None = None) -> None:
    """
    Upsert контента в таблицу content.
    Если нет уникального индекса по key — используем UPDATE → INSERT.
    """
    # Очищаем HTML перед сохранением
    value = sanitize_html(value)

    await _write_content_version(key, value, updated_by)

    updated = await fetchrow("SELECT id FROM content WHERE key=$1", key)
    if updated:
        await execute(
            "UPDATE content SET value=$2, updated_at=NOW() WHERE key=$1",
            key, value
        )
    else:
        await execute(
            "INSERT INTO content(key, value, created_at, updated_at) VALUES ($1,$2,NOW(),NOW())",
            key, value
        )
    # Обновляем кэш
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


async def _format_content_version_author(updated_by: Any) -> str:
    if not updated_by:
        return "—"

    try:
        tg_id = int(updated_by)
    except (TypeError, ValueError):
        return html.escape(str(updated_by))

    user_row = await fetchrow(
        "SELECT username, full_name, name FROM users WHERE tg_user_id=$1",
        tg_id,
    )
    if user_row:
        user_data = dict(user_row)
        display_name = _admin_user_display_name(user_data)
        parts: list[str] = []
        if display_name and display_name != "—":
            parts.append(html.escape(display_name))
        username = (user_data.get("username") or "").strip()
        if username:
            parts.append(f"@{html.escape(username)}")
        parts.append(f"tg_id={tg_id}")
        return " ".join(parts)

    return f"tg_id={tg_id}"


async def _send_content_history(
    message: types.Message,
    state: FSMContext,
    key: str,
    *,
    source: str,
) -> bool:
    versions = await get_content_versions(key, limit=_CONTENT_HISTORY_LIMIT)
    if not versions:
        return False

    version_choices = {str(idx): int(item["id"]) for idx, item in enumerate(versions, start=1)}
    await state.update_data(content_history={"key": key, "choices": version_choices})
    await state.set_state(AdminContentStates.waiting_history_choice)

    lines = ["<b>История изменений</b>", f"<b>Ключ:</b> <code>{html.escape(key)}</code>", ""]

    for idx, version in enumerate(versions, start=1):
        timestamp_text = _format_datetime_safe(version.get("updated_at"))
        author_text = await _format_content_version_author(version.get("updated_by"))
        preview = _preview_text_for_admin(str(version.get("value") or ""), limit=400)
        lines.extend([
            f"{idx}. {timestamp_text} — {author_text}",
            preview,
            "",
        ])

    lines.extend([
        "Выбери версию кнопкой «↩️ Откатить N», чтобы вернуть текст.",
        "Отмена — вернуться назад.",
    ])

    await message.answer(
        "\n".join(lines).strip(),
        reply_markup=admin_content_versions_keyboard(len(versions)),
        disable_web_page_preview=True,
    )

    await log_admin_action(
        message.from_user.id,
        "content_history_view",
        {"key": key, "count": len(versions), "source": source},
    )
    return True
async def list_content_keys_db() -> list[str]:
    rows = await fetch("SELECT key FROM content ORDER BY key ASC")
    return [r["key"] for r in rows] if rows else []


async def _collect_content_export_data() -> OrderedDict[str, str]:
    db_keys = await list_content_keys_db()
    db_values: dict[str, str] = {}

    if db_keys:
        rows = await fetch(
            "SELECT key, value FROM content WHERE key = ANY($1::text[])",
            db_keys,
        )
        value_map = {str(row["key"]): str(row.get("value") or "") for row in (rows or [])}
        for key in db_keys:
            if key in value_map:
                db_values[key] = value_map[key]

    yaml_content = _load_yaml_content()
    yaml_keys = list(_flatten_yaml_keys(yaml_content))
    combined_keys = _merge_unique_content_keys(db_keys, yaml_keys)

    export_data: OrderedDict[str, str] = OrderedDict()
    for key in combined_keys:
        if key in db_values:
            export_data[key] = db_values[key]
            continue

        yaml_value, found = _get_yaml_value(key, default="")
        if found:
            export_data[key] = yaml_value

    return export_data


async def get_onboarding_steps() -> list[str]:
    """Возвращает список шагов онбординга из БД либо YAML по умолчанию."""
    rows = await fetch(
        """
        SELECT key, value
        FROM content
        WHERE key LIKE $1
        ORDER BY (regexp_replace(key, '^onboarding\\.', ''))::int
        """,
        "onboarding.%",
    )
    if rows:
        steps: list[str] = []
        for row in rows:
            value = row.get("value") or ""
            steps.append(str(value))
        return steps

    yaml_content = _load_yaml_content()
    yaml_steps = yaml_content.get("onboarding", []) if isinstance(yaml_content, dict) else []
    return [str(step) for step in (yaml_steps or [])]


async def save_onboarding_steps(steps: list[str], *, updated_by: int | None = None) -> None:
    """Перезаписывает шаги онбординга в таблице content."""
    cleaned_steps = [sanitize_html(step or "") for step in steps]
    await execute("DELETE FROM content WHERE key LIKE $1", "onboarding.%")
    for idx, step in enumerate(cleaned_steps):
        await set_content_value(f"onboarding.{idx}", step, updated_by=updated_by)


def format_onboarding_summary(steps: list[str]) -> str:
    if not steps:
        return "Пока нет активных шагов. Добавь первый."

    lines: list[str] = []
    for idx, step in enumerate(steps, start=1):
        lines.append(f"{idx}. {step.strip() or '(пусто)'}")
    return "\n".join(lines)


_BROADCAST_SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


async def _generate_broadcast_slug(title: str) -> str:
    base = _BROADCAST_SLUG_RE.sub("-", (title or "").strip().lower()).strip("-")
    if not base:
        base = "template"
    base = base[:50]
    candidate = base
    suffix = 1
    while await fetchrow("SELECT 1 FROM broadcast_templates WHERE slug=$1", candidate):
        candidate = f"{base}-{suffix}"[:60]
        suffix += 1
    return candidate


async def upsert_broadcast_template(title: str, segment: str, body: str) -> dict:
    sanitized_body = sanitize_html(body or "")
    existing = await fetchrow("SELECT slug FROM broadcast_templates WHERE title=$1", title)
    if existing:
        slug = existing["slug"]
    else:
        slug = await _generate_broadcast_slug(title)

    await execute(
        """
        INSERT INTO broadcast_templates (slug, title, segment, body, created_at, updated_at)
        VALUES ($1, $2, $3, $4, NOW(), NOW())
        ON CONFLICT(slug)
        DO UPDATE SET
            title = EXCLUDED.title,
            segment = EXCLUDED.segment,
            body = EXCLUDED.body,
            updated_at = NOW()
        """,
        slug,
        title,
        segment,
        sanitized_body,
    )

    return {
        "slug": slug,
        "title": title,
        "segment": segment,
        "body": sanitized_body,
    }


async def list_broadcast_templates() -> list[dict]:
    rows = await fetch(
        """
        SELECT slug, title, segment, body
        FROM broadcast_templates
        ORDER BY created_at ASC, title ASC
        """
    )
    return [dict(row) for row in rows] if rows else []


async def get_broadcast_template_by_title(title: str) -> Optional[dict]:
    row = await fetchrow(
        "SELECT slug, title, segment, body FROM broadcast_templates WHERE title=$1",
        title,
    )
    return dict(row) if row else None


async def delete_broadcast_template(title: str) -> bool:
    row = await fetchrow(
        "DELETE FROM broadcast_templates WHERE title=$1 RETURNING slug",
        title,
    )
    return bool(row)
def _flatten_yaml_keys(src: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(src, dict):
        for k, v in (src or {}).items():
            full = f"{prefix}.{k}" if prefix else str(k)
            yield from _flatten_yaml_keys(v, full)
    elif isinstance(src, list):
        for idx, item in enumerate(src):
            full = f"{prefix}.{idx}" if prefix else str(idx)
            yield from _flatten_yaml_keys(item, full)
    else:
        if prefix:
            yield prefix
def now_utc() -> datetime:
    return datetime.now(timezone.utc)
# ──────────────────────────────────────────────────────────────────────────────
# FSM
# ──────────────────────────────────────────────────────────────────────────────
class RegistrationStates(StatesGroup):
    waiting_name = State()      # ждём имя пользователя
    waiting_email = State()     # ждём email
    waiting_phone = State()     # ждём телефон
class HWStates(StatesGroup):
    waiting_answer = State()  # ждём текстовый ответ на ДЗ ({"lesson_num": int})
    waiting_feedback = State() # ждём обратную связь после урока
class BroadcastStates(StatesGroup):
    waiting_segment = State()   # ждём выбор сегмента в мастере
    waiting_body = State()      # ждём текст рассылки ({"segment": str})
    waiting_confirm = State()   # подтверждение рассылки
    waiting_template_title = State()  # название шаблона
    waiting_template_delete = State() # выбор шаблона для удаления
class ProfileStates(StatesGroup):
    waiting_email = State()
    waiting_phone = State()


class AdminContentStates(StatesGroup):
    waiting_value = State()
    waiting_custom_key = State()
    waiting_custom_value = State()
    waiting_view_key = State()
    waiting_history_key = State()
    waiting_history_choice = State()
    waiting_import_file = State()


class AdminBehaviorStates(StatesGroup):
    waiting_start_text = State()
    waiting_registration_text = State()
    waiting_onboarding_text = State()
    waiting_onboarding_delete = State()


class AdminUserStates(StatesGroup):
    choosing_segment = State()
    browsing_users = State()
    viewing_user = State()
    waiting_contacts = State()


class AdminPaymentsStates(StatesGroup):
    waiting_access_user = State()
    waiting_revoke_user = State()
    waiting_payment_review = State()


class TestStates(StatesGroup):
    waiting_birthdate = State()
    waiting_name = State()
# ──────────────────────────────────────────────────────────────────────────────
# Улучшенные клавиатуры
# ──────────────────────────────────────────────────────────────────────────────
_MENU_SECTION_PROMPTS: dict[str, tuple[str, str]] = {
    "root": ("menu.prompts.root", "Главное меню\n\nВыбери раздел, чтобы продолжить."),
    "info": ("menu.prompts.info", "Раздел «О клубе».\n\nВыбери интересующий пункт."),
    "learning": ("menu.prompts.learning", "Раздел «Обучение».\n\nВыбери, с чего продолжить."),
    "materials": ("menu.prompts.materials", "Раздел «Материалы».\n\nДоступ к материалам зависит от статуса участия."),
    "profile": ("menu.prompts.profile", "Раздел «Профиль».\n\nУправляй своими данными и доступами."),
}

_ADMIN_SETTINGS_DEFAULTS: dict[str, bool] = {
    "payments_open": True,
    "payments_manual_review": False,
    "show_weekly_materials": True,
    "show_schedule": True,
}

_ADMIN_SETTINGS_LABELS: dict[str, str] = {
    "payments_open": "Окно оплаты",
    "payments_manual_review": "Ручная проверка оплат",
    "show_weekly_materials": "Материалы недели",
    "show_schedule": "Расписание",
}

_PROFILE_STATUS_TITLES: dict[str, str] = {
    "lead_funnel": "Без подписки",
    "member_active": "Активный доступ",
    "member_expired": "Доступ истёк",
}

_ADMIN_TEXT_GROUPS: dict[str, list[tuple[str, str]]] = {
    "🏠 Вход и меню": [
        ("Приветствие /start", "menu.start"),
        ("Сообщение после регистрации", "menu.registration_complete"),
        ("Подсказка главного меню", "menu.prompts.root"),
        ("Подсказка «Профиль»", "menu.prompts.profile"),
    ],
    "ℹ️ Раздел «О клубе»": [
        ("Подсказка «О клубе»", "menu.prompts.info"),
        ("Окно «О клубе»", "menu.about"),
        ("Окно FAQ", "menu.faq"),
        ("Окно «Правила»", "menu.rules"),
    ],
    "🎓 Раздел «Обучение»": [
        ("Подсказка «Обучение»", "menu.prompts.learning"),
        ("Окно «Записаться на разбор»", "menu.analysis"),
        ("Окно «Пройти тест»", "menu.test"),
        ("Сообщение «Все уроки пройдены»", "menu.funnel.completed"),
    ],
    "📦 Раздел «Материалы»": [
        ("Подсказка «Материалы»", "menu.prompts.materials"),
        ("Материалы недели (контент)", "weekly_materials"),
        ("Материалы недели закрыты", "menu.weekly.disabled"),
        ("Материалы недели без доступа", "menu.weekly.locked"),
        ("Расписание (контент)", "schedule"),
        ("Расписание скрыто", "menu.schedule.disabled"),
        ("Расписание без доступа", "menu.schedule.locked"),
    ],
    "💳 Оплата и поддержка": [
        ("Окно «Оплата»", "menu.pay"),
        ("Оплата закрыта", "menu.pay.closed"),
        ("Комментарий о проверке оплаты", "menu.pay.manual_review"),
        ("Окно «Поддержка»", "menu.support"),
    ],
}

ADMIN_TEXTS_PREVIEW_BUTTON = "👁 Предпросмотр"

_ADMIN_TEXT_PLACEHOLDERS: dict[str, dict[str, list[str]]] = {
    "menu.start": {
        "required": ["{name}"],
        "optional": ["{{NAME}}"],
    },
    "menu.registration_complete": {
        "required": ["{name}"],
        "optional": ["{{NAME}}"],
    },
    "menu.pay": {
        "required": ["{checkout_url}"],
        "optional": ["{{CHECKOUT_URL}}"],
    },
    "menu.support": {
        "required": ["{support}"],
        "optional": ["{{SUPPORT_CONTACT}}"],
    },
}

_ADMIN_TEXT_PREVIEW_SAMPLE_DATA: dict[str, str] = {
    "name": "Алиса",
    "checkout_url": YOOMONEY_CHECKOUT_URL or "https://pay.example.com/checkout",
    "support": SUPPORT_CONTACT,
    "support_contact": SUPPORT_CONTACT,
}


def _admin_placeholder_variants(token: str) -> set[str]:
    normalized = token.strip("{}").strip()
    if not normalized:
        return {token}
    key = normalized.lower()
    variants = {
        f"{{{key}}}",
        f"{{{key.upper()}}}",
        f"{{{{{key}}}}}",
        f"{{{{{key.upper()}}}}}",
    }
    variants.add(token)
    return variants


def _admin_placeholder_config(key: str) -> tuple[list[str], list[str]]:
    config = _ADMIN_TEXT_PLACEHOLDERS.get(key) or {}
    required = list(config.get("required", []))
    optional = [token for token in config.get("optional", []) if token not in required]
    return required, optional


def _admin_missing_required_placeholders(text: str, key: str) -> list[str]:
    required_tokens, _ = _admin_placeholder_config(key)
    if not required_tokens:
        return []
    missing: list[str] = []
    for token in required_tokens:
        variants = _admin_placeholder_variants(token)
        if not any(variant in text for variant in variants):
            missing.append(token)
    return missing


def _admin_placeholder_hint_line(key: str) -> str:
    required, optional = _admin_placeholder_config(key)
    if not required and not optional:
        return ""

    def _format(tokens: list[str]) -> str:
        return ", ".join(f"<code>{html.escape(token)}</code>" for token in tokens)

    parts: list[str] = []
    if required:
        parts.append(f"обязательные — {_format(required)}")
    if optional:
        parts.append(f"дополнительные — {_format(optional)}")

    return "Можно использовать плейсхолдеры: " + "; ".join(parts)

_CONTENT_KEY_HINTS: dict[str, str] = {
    "about": "Описание клуба по умолчанию",
    "rules": "Правила сообщества",
    "faq": "Ответы на частые вопросы",
    "weekly_materials": "Шаблон блока «Материалы недели»",
    "schedule": "Основной текст расписания",
    "offer_after_lesson_4": "Оффер после четвёртого урока",
}

for entries in _ADMIN_TEXT_GROUPS.values():
    for label, key in entries:
        if key:
            _CONTENT_KEY_HINTS.setdefault(key, label)

for setting_key, label in _ADMIN_SETTINGS_LABELS.items():
    _CONTENT_KEY_HINTS.setdefault(f"settings.{setting_key}", f"Настройка: {label}")

_CONTENT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,}$")
_CONTENT_SUGGESTION_STEP = 6
_CONTENT_SUGGESTION_LIMIT: int | None = None
_CONTENT_PREVIEW_KEY_RE = re.compile(r"<b>Ключ:</b>\s*<code>([^<]+)</code>")
_CONTENT_PREVIEW_KEY_PLAIN_RE = re.compile(r"Ключ[:：]\s*([A-Za-z0-9_.-]{3,})")


_BROADCAST_SEGMENT_LABELS: dict[str, str] = {
    "all": "Все пользователи",
    "lead_funnel": "Лиды без доступа",
    "member_active": "Активные участницы",
    "member_expired": "Доступ истёк",
}

_BROADCAST_BUTTON_SEGMENTS: dict[str, str] = {
    BROADCAST_ALL_BUTTON: "all",
    BROADCAST_LEADS_BUTTON: "lead_funnel",
    BROADCAST_MEMBERS_BUTTON: "member_active",
    BROADCAST_EXPIRED_BUTTON: "member_expired",
}

_ADMIN_USER_SEGMENT_CONDITIONS: dict[str, str] = {
    "lead_funnel": "status='lead_funnel'",
    "member_active": "status='member_active' AND (access_until IS NULL OR access_until > NOW())",
    "member_expired": "status='member_expired' OR (access_until IS NOT NULL AND access_until <= NOW())",
}

_ADMIN_USER_BUTTON_SEGMENTS: dict[str, str] = {
    ADMIN_USERS_SEGMENT_LEADS: "lead_funnel",
    ADMIN_USERS_SEGMENT_ACTIVE: "member_active",
    ADMIN_USERS_SEGMENT_EXPIRED: "member_expired",
}

_ADMIN_USER_SEGMENT_LABELS: dict[str, str] = {
    "lead_funnel": "Лиды",
    "member_active": "Активные",
    "member_expired": "Завершившие",
}

_ADMIN_USERS_PAGE_SIZE = 5

_ADMIN_USER_PROGRESS_ICONS: dict[str, str] = {
    "submitted": "✅",
    "skipped": "⏭️",
    "pending": "⏳",
}

_ADMIN_STATS_USER_LABELS: dict[str, str] = {
    "total": "Всего",
    "lead_funnel": "Лиды",
    "member_active": "Активные",
    "member_expired": "Завершившие",
}

_ADMIN_LESSON_STATUS_ORDER = ["submitted", "pending", "skipped"]

_ADMIN_LESSON_STATUS_LABELS: dict[str, str] = {
    "submitted": "Сдано",
    "pending": "В работе",
    "skipped": "Пропущено",
}

_ADMIN_PAYMENT_STATUS_LABELS: dict[str, str] = {
    "paid": "Оплачено",
    "renew": "Продление",
    "refund": "Возврат",
    "failed": "Ошибка",
}

_TEST_REQUEST_STATUS_ORDER = [
    "waiting",
    "booked",
    "in_progress",
    "done",
    "cancelled",
    "archived",
]

_TEST_REQUEST_STATUS_LABELS: dict[str, str] = {
    "waiting": "В ожидании",
    "booked": "Запланировано",
    "in_progress": "В работе",
    "done": "Завершено",
    "cancelled": "Отменено",
    "archived": "Архив",
}

_TEST_REQUEST_CLOSED_STATUSES = {"done", "completed", "cancelled", "archived", "rejected"}


def _admin_user_segment_from_text(text: str | None) -> str | None:
    if not text:
        return None
    return _ADMIN_USER_BUTTON_SEGMENTS.get(text.strip())


def _admin_user_segment_label(segment: str | None) -> str:
    if not segment:
        return "—"
    return _ADMIN_USER_SEGMENT_LABELS.get(segment, segment)


def _admin_user_display_name(user: dict) -> str:
    for key in ("name", "full_name"):
        value = (user.get(key) or "").strip()
        if value:
            return value
    return "—"


def _admin_user_username(user: dict) -> str:
    username = (user.get("username") or "").strip()
    return f"@{username}" if username else "—"


def _format_datetime_safe(value: Any) -> str:
    if not value:
        return "—"
    dt = value
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return html.escape(dt)
    if isinstance(dt, datetime):
        try:
            return tz_aware_msk(dt)
        except Exception:
            return dt.isoformat()
    return html.escape(str(value))


def _admin_user_access_line(user: dict) -> str:
    access_until = user.get("access_until")
    if not access_until:
        return "—"
    dt = access_until
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return html.escape(dt)
    if isinstance(dt, datetime) and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if isinstance(dt, datetime):
        try:
            return tz_aware_msk(dt)
        except Exception:
            return dt.isoformat()
    return html.escape(str(access_until))


def _admin_user_progress_summary(progress: list[tuple[int, str]] | None) -> str:
    if not progress:
        return "—"
    parts: list[str] = []
    for lesson_num, status in sorted(progress, key=lambda item: item[0]):
        icon = _ADMIN_USER_PROGRESS_ICONS.get(status, "•")
        parts.append(f"{lesson_num}{icon}")
    return " ".join(parts)


async def _collect_progress_map(user_ids: list[int]) -> dict[int, list[tuple[int, str]]]:
    if not user_ids:
        return {}
    rows = await fetch(
        """
        SELECT user_id, lesson_num, hw_status
        FROM funnel_progress
        WHERE user_id = ANY($1::int[])
        ORDER BY user_id, lesson_num
        """,
        user_ids,
    )
    progress: dict[int, list[tuple[int, str]]] = {}
    for row in rows or []:
        progress.setdefault(row["user_id"], []).append((row["lesson_num"], row["hw_status"]))
    return progress


async def _collect_last_payments(users: list[dict]) -> dict[int, dict]:
    results: dict[int, dict] = {}
    for user in users:
        email = (user.get("email") or "").strip()
        phone = (user.get("phone") or "").strip()
        at_user = (user.get("at_user_id") or "").strip()

        conditions: list[str] = []
        params: list[Any] = []
        idx = 1
        if email:
            conditions.append(f"LOWER(email) = LOWER(${idx})")
            params.append(email)
            idx += 1
        if phone:
            conditions.append(f"phone = ${idx}")
            params.append(phone)
            idx += 1
        if at_user:
            conditions.append(f"at_user_id = ${idx}")
            params.append(at_user)
            idx += 1

        if not conditions:
            continue

        sql = (
            "SELECT status, paid_at, access_until FROM payments WHERE "
            + " OR ".join(conditions)
            + " ORDER BY paid_at DESC NULLS LAST, created_at DESC, id DESC LIMIT 1"
        )
        row = await fetchrow(sql, *params)
        if row:
            results[user["id"]] = dict(row)
    return results


def _format_payment_line(payment: dict | None) -> str:
    if not payment:
        return "—"
    status = html.escape(payment.get("status") or "—")
    paid_at_text = _format_datetime_safe(payment.get("paid_at"))
    access_text = _format_datetime_safe(payment.get("access_until"))
    details = []
    if paid_at_text != "—":
        details.append(paid_at_text)
    if access_text != "—" and access_text != paid_at_text:
        details.append(f"доступ до {access_text}")
    if details:
        return f"{status} ({', '.join(details)})"
    return status


async def _fetch_recent_payments(limit: int = 5) -> list[dict]:
    rows = await fetch(
        """
        SELECT id, order_id, status, email, phone, paid_at, created_at, access_until
          FROM payments
         ORDER BY paid_at DESC NULLS LAST, created_at DESC, id DESC
         LIMIT $1
        """,
        limit,
    )
    return [dict(row) for row in rows or []]


def _format_admin_payment_entry(payment: dict) -> str:
    order_id = html.escape(payment.get("order_id") or f"#{payment.get('id')}")
    status = html.escape(payment.get("status") or "—")
    paid_at = _format_datetime_safe(payment.get("paid_at") or payment.get("created_at"))
    contact_bits = []
    email = payment.get("email")
    phone = payment.get("phone")
    if email:
        contact_bits.append(html.escape(email))
    if phone:
        contact_bits.append(html.escape(phone))
    contacts = ", ".join(contact_bits) if contact_bits else "контакты не указаны"
    return f"• <code>{order_id}</code> — {status} ({paid_at})\n  {contacts}"


def _render_stats_table(
    headers: list[str],
    rows: list[list[str]],
    align: list[str] | None = None,
) -> str:
    if align is None:
        align = ["left"] * len(headers)

    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _format_cell(text: str, width: int, alignment: str) -> str:
        if alignment == "right":
            return text.rjust(width)
        if alignment == "center":
            pad_total = max(width - len(text), 0)
            left = pad_total // 2
            right = pad_total - left
            return " " * left + text + " " * right
        return text.ljust(width)

    space = "  "
    header_line = space.join(
        _format_cell(headers[idx], widths[idx], align[idx]) for idx in range(len(headers))
    )
    separator = space.join("─" * width for width in widths)
    body_lines = [
        space.join(_format_cell(row[idx], widths[idx], align[idx]) for idx in range(len(headers)))
        for row in rows
    ]
    table_lines = [header_line, separator, *body_lines] if rows else [header_line, separator]
    return "<pre>" + "\n".join(table_lines) + "</pre>"


async def _collect_admin_stats_data() -> dict[str, Any]:
    total = await fetchrow("SELECT COUNT(*) AS c FROM users")
    lead = await fetchrow("SELECT COUNT(*) AS c FROM users WHERE status='lead_funnel'")
    active = await fetchrow("SELECT COUNT(*) AS c FROM users WHERE status='member_active'")
    expired = await fetchrow("SELECT COUNT(*) AS c FROM users WHERE status='member_expired'")

    lesson_stats_rows = await fetch(
        """
        SELECT lesson_num, hw_status, COUNT(*) AS count
          FROM funnel_progress
         GROUP BY lesson_num, hw_status
         ORDER BY lesson_num, hw_status
        """
    )

    completed_4 = await fetchrow(
        """
        SELECT COUNT(*) AS c
          FROM (
                SELECT user_id
                  FROM funnel_progress
                 WHERE hw_status = 'submitted'
                 GROUP BY user_id
                HAVING COUNT(DISTINCT CASE
                           WHEN lesson_num BETWEEN 1 AND 4 THEN lesson_num
                       END) = 4
               ) AS completed
        """
    )

    payment_stats_rows = await fetch(
        """
        SELECT status, COUNT(*) AS count, MAX(created_at) AS last_payment
          FROM payments
         GROUP BY status
        """
    )

    form_sessions_rows = await fetch(
        """
        SELECT form_slug,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE completed_at IS NOT NULL) AS completed,
               COUNT(*) FILTER (WHERE completed_at IS NULL) AS in_progress,
               MAX(started_at) AS last_started,
               MAX(completed_at) AS last_completed
          FROM form_sessions
         GROUP BY form_slug
        """
    )

    test_requests_status_rows = await fetch(
        """
        SELECT status, COUNT(*) AS count, MAX(updated_at) AS last_updated
          FROM test_requests
         GROUP BY status
        """
    )

    test_requests_overview = await fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (
                   WHERE status NOT IN ('done', 'completed', 'cancelled', 'archived', 'rejected')
               ) AS active
          FROM test_requests
        """
    )

    return {
        "users": {
            "total": int((total or {}).get("c", 0)),
            "lead_funnel": int((lead or {}).get("c", 0)),
            "member_active": int((active or {}).get("c", 0)),
            "member_expired": int((expired or {}).get("c", 0)),
        },
        "funnel": {
            "completed_4of4": int((completed_4 or {}).get("c", 0)),
            "lesson_stats": [dict(row) for row in lesson_stats_rows or []],
        },
        "payments": [dict(row) for row in payment_stats_rows or []],
        "forms": {
            "sessions": [dict(row) for row in form_sessions_rows or []],
            "test_requests": {
                "statuses": [dict(row) for row in test_requests_status_rows or []],
                "summary": {
                    "total": int((test_requests_overview or {}).get("total", 0)),
                    "active": int((test_requests_overview or {}).get("active", 0)),
                },
            },
        },
        "timestamp": now_utc(),
    }


def _generate_users_table_data(stats: dict[str, Any]) -> tuple[list[str], list[list[str]], list[str]]:
    users = stats.get("users", {})
    total = int(users.get("total") or 0)
    headers = ["Статус", "Кол-во", "%"]
    rows: list[list[str]] = []
    for key in ("total", "lead_funnel", "member_active", "member_expired"):
        label = _ADMIN_STATS_USER_LABELS.get(key, key)
        value = int(users.get(key) or 0)
        if total:
            share = "100%" if key == "total" else f"{value / total * 100:.1f}%"
        else:
            share = "—"
        rows.append([label, str(value), share])
    return headers, rows, ["left", "right", "right"]


def _generate_lesson_table_data(stats: dict[str, Any]) -> tuple[list[str], list[list[str]], list[str]]:
    funnel = stats.get("funnel") or {}
    lesson_rows = funnel.get("lesson_stats") or []

    statuses_present = {
        row.get("hw_status") for row in lesson_rows if row.get("hw_status")
    }
    base_statuses = list(_ADMIN_LESSON_STATUS_ORDER)
    extra_statuses = sorted(statuses_present - set(base_statuses))
    status_order = list(dict.fromkeys(base_statuses + extra_statuses))

    lesson_numbers = sorted({row.get("lesson_num") for row in lesson_rows if row.get("lesson_num")})
    if not lesson_numbers:
        lesson_numbers = list(range(1, 5))

    totals: dict[str, int] = {status: 0 for status in status_order}
    rows: list[list[str]] = []

    for lesson_num in lesson_numbers:
        row_counts = {status: 0 for status in status_order}
        for item in lesson_rows:
            if item.get("lesson_num") == lesson_num:
                status = item.get("hw_status")
                if not status:
                    continue
                count = int(item.get("count") or 0)
                row_counts[status] = count
                totals[status] = totals.get(status, 0) + count
        rows.append(
            [f"Урок {lesson_num}"]
            + [str(row_counts.get(status, 0)) for status in status_order]
        )

    totals_row = ["Итого"] + [str(totals.get(status, 0)) for status in status_order]
    rows.append(totals_row)

    headers = ["Урок"] + [
        _ADMIN_LESSON_STATUS_LABELS.get(status, str(status).title()) for status in status_order
    ]
    align = ["left"] + ["right"] * len(status_order)
    return headers, rows, align


def _generate_payments_table_data(stats: dict[str, Any]) -> tuple[list[str], list[list[str]], list[str]]:
    payment_rows = stats.get("payments") or []
    statuses_present = {row.get("status") for row in payment_rows if row.get("status")}
    base_order = ["paid", "renew", "refund", "failed"]
    extra_statuses = sorted(statuses_present - set(base_order))
    status_order = list(dict.fromkeys(base_order + extra_statuses))

    rows: list[list[str]] = []
    total = 0
    for status in status_order:
        matching = next((row for row in payment_rows if row.get("status") == status), None)
        count = int((matching or {}).get("count") or 0)
        total += count
        last_payment = _format_datetime_safe((matching or {}).get("last_payment"))
        label = _ADMIN_PAYMENT_STATUS_LABELS.get(status, status)
        rows.append([label, str(count), last_payment])

    if not status_order:
        rows.append(["Нет записей", "0", "—"])

    rows.append(["Итого", str(total), "—"])

    headers = ["Статус", "Кол-во", "Последняя запись"]
    align = ["left", "right", "left"]
    return headers, rows, align


def _form_display_label(slug: str) -> str:
    if not slug:
        return "—"
    normalized = slug.strip()
    base = FORM_LABELS.get(normalized)
    if base and base != normalized:
        return f"{base} ({normalized})"
    return normalized


def _generate_form_sessions_table_data(stats: dict[str, Any]) -> tuple[list[str], list[list[str]], list[str]]:
    forms_data = stats.get("forms") or {}
    session_rows = forms_data.get("sessions") or []

    headers = [
        "Форма",
        "Начато",
        "Завершено",
        "Активно",
        "Посл. старт",
        "Посл. заверш.",
    ]
    align = ["left", "right", "right", "right", "left", "left"]

    if not session_rows:
        empty_row = ["Нет данных", "0", "0", "0", "—", "—"]
        return headers, [empty_row], align

    def _row_key(item: dict[str, Any]) -> tuple[int, str]:
        slug = str(item.get("form_slug") or "")
        priority = 0 if slug in (FORM_SLUG_ANALYSIS, FORM_SLUG_TEST) else 1
        return priority, slug

    rows: list[list[str]] = []
    total_started = 0
    total_completed = 0
    total_active = 0

    for item in sorted(session_rows, key=_row_key):
        slug = str(item.get("form_slug") or "")
        started = int(item.get("total") or 0)
        completed = int(item.get("completed") or 0)
        in_progress = int(item.get("in_progress") or started - completed)
        in_progress = max(in_progress, 0)
        last_started = _format_datetime_safe(item.get("last_started"))
        last_completed = _format_datetime_safe(item.get("last_completed"))

        total_started += started
        total_completed += completed
        total_active += in_progress

        rows.append(
            [
                _form_display_label(slug),
                str(started),
                str(completed),
                str(in_progress),
                last_started,
                last_completed,
            ]
        )

    rows.append([
        "Итого",
        str(total_started),
        str(total_completed),
        str(total_active),
        "—",
        "—",
    ])

    return headers, rows, align


def _format_admin_stats_overview(stats: dict[str, Any]) -> str:
    headers_users, rows_users, align_users = _generate_users_table_data(stats)
    headers_lessons, rows_lessons, align_lessons = _generate_lesson_table_data(stats)
    headers_payments, rows_payments, align_payments = _generate_payments_table_data(stats)

    users_table = _render_stats_table(headers_users, rows_users, align_users)
    lessons_table = _render_stats_table(headers_lessons, rows_lessons, align_lessons)
    payments_table = _render_stats_table(headers_payments, rows_payments, align_payments)

    timestamp = _format_datetime_safe(stats.get("timestamp"))
    completed = stats.get("funnel", {}).get("completed_4of4", 0)

    lines = [
        "<b>📊 Сводка по базе</b>",
        "",
        "<b>👥 Пользователи</b>",
        users_table,
        "",
        "<b>🎯 Уроки</b>",
        f"Завершили 4/4 урока: <b>{completed}</b>",
        lessons_table,
        "",
        "<b>💰 Оплаты</b>",
        payments_table,
        "",
        f"Обновлено: {timestamp}",
        "",
        "Используй кнопки ниже, чтобы открыть подробные отчёты.",
        "«🗂 Формы и консультации» — отдельная сводка по тестам и разборам.",
    ]
    return "\n".join(lines)


def _format_admin_stats_users(stats: dict[str, Any]) -> str:
    headers, rows, align = _generate_users_table_data(stats)
    table = _render_stats_table(headers, rows, align)
    timestamp = _format_datetime_safe(stats.get("timestamp"))
    return "\n".join([
        "<b>📋 Статусы пользователей</b>",
        table,
        "",
        f"Обновлено: {timestamp}",
    ])


def _format_admin_stats_lessons(stats: dict[str, Any]) -> str:
    headers, rows, align = _generate_lesson_table_data(stats)
    table = _render_stats_table(headers, rows, align)
    completed = stats.get("funnel", {}).get("completed_4of4", 0)
    timestamp = _format_datetime_safe(stats.get("timestamp"))
    return "\n".join([
        "<b>🎯 Прогресс уроков</b>",
        f"4/4 урока завершили: <b>{completed}</b>",
        table,
        "",
        "Статусы: <i>Сдано</i> — домашнее задание принято, <i>В работе</i> — урок открыт,",
        "<i>Пропущено</i> — урок отмечен как пропущенный.",
        "",
        f"Обновлено: {timestamp}",
    ])


def _format_admin_stats_payments(stats: dict[str, Any]) -> str:
    headers, rows, align = _generate_payments_table_data(stats)
    table = _render_stats_table(headers, rows, align)
    timestamp = _format_datetime_safe(stats.get("timestamp"))
    return "\n".join([
        "<b>💰 Статистика оплат</b>",
        table,
        "",
        "Последняя запись показывает дату по полю created_at/paid_at.",
        "",
        f"Обновлено: {timestamp}",
    ])


def _format_admin_stats_forms(stats: dict[str, Any]) -> str:
    headers, rows, align = _generate_form_sessions_table_data(stats)
    forms_table = _render_stats_table(headers, rows, align)

    forms_data = stats.get("forms") or {}
    test_requests = forms_data.get("test_requests") or {}
    status_rows = test_requests.get("statuses") or []
    summary = test_requests.get("summary") or {}
    total_requests = int(summary.get("total") or 0)
    active_requests = int(summary.get("active") or 0)

    if not total_requests and status_rows:
        total_requests = sum(int(item.get("count") or 0) for item in status_rows)
    if not active_requests and status_rows:
        active_requests = sum(
            int(item.get("count") or 0)
            for item in status_rows
            if str(item.get("status") or "").lower() not in _TEST_REQUEST_CLOSED_STATUSES
        )

    if status_rows:
        def _status_key(item: dict[str, Any]) -> tuple[int, str]:
            status = str(item.get("status") or "")
            try:
                return _TEST_REQUEST_STATUS_ORDER.index(status), status
            except ValueError:
                return len(_TEST_REQUEST_STATUS_ORDER), status

        ordered_statuses = sorted(status_rows, key=_status_key)
    else:
        ordered_statuses = []

    status_lines: list[str] = []
    for item in ordered_statuses:
        status = str(item.get("status") or "")
        label = _TEST_REQUEST_STATUS_LABELS.get(status, status or "—")
        count = int(item.get("count") or 0)
        last_updated = _format_datetime_safe(item.get("last_updated"))
        suffix = f" (обновлено: {last_updated})" if last_updated != "—" else ""
        is_active = str(status).lower() not in _TEST_REQUEST_CLOSED_STATUSES
        marker = "🔥" if is_active else "✅"
        status_lines.append(f"{marker} {label}: <b>{count}</b>{suffix}")

    updates = [item.get("last_updated") for item in ordered_statuses if item.get("last_updated")]
    last_status_update = max(updates) if updates else None

    lines = [
        "<b>🗂 Формы и консультации</b>",
        "",
        "<b>Формы</b>",
        forms_table,
        "",
        "<b>Заявки на консультацию</b>",
        f"Всего заявок: <b>{total_requests}</b>",
        f"Активных (ожидают действий): <b>{active_requests}</b>",
    ]

    if status_lines:
        lines.extend(["", "По статусам:", *status_lines])
    else:
        lines.extend(["", "Пока нет заявок в базе."])

    timestamp = _format_datetime_safe(stats.get("timestamp"))
    last_status_text = _format_datetime_safe(last_status_update)

    lines.extend([
        "",
        f"Последнее изменение статусов: {last_status_text}",
        f"Обновлено: {timestamp}",
    ])

    return "\n".join(lines)


async def _admin_set_member_active(user_id: int, access_until: Optional[datetime]) -> None:
    await execute(
        """
        UPDATE users
           SET status='member_active',
               access_until=$2,
               joined_club_at=COALESCE(joined_club_at, NOW()),
               updated_at=NOW()
         WHERE id=$1
        """,
        user_id,
        access_until,
    )


async def _admin_set_member_expired(user_id: int) -> None:
    await execute(
        "UPDATE users SET status='member_expired', access_until=NULL, updated_at=NOW() WHERE id=$1",
        user_id,
    )


async def _admin_find_user(identifier: str) -> Optional[dict]:
    normalized = (identifier or "").strip()
    if not normalized:
        return None

    if normalized.startswith("@"):
        normalized = normalized[1:]

    if normalized.isdigit():
        tg_id = int(normalized)
        row = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_id)
        if row:
            return dict(row)
        row = await fetchrow("SELECT * FROM users WHERE id=$1", tg_id)
        if row:
            return dict(row)

    if normalized:
        row = await fetchrow("SELECT * FROM users WHERE LOWER(username)=LOWER($1)", normalized)
        if row:
            return dict(row)

    return None


def _parse_admin_access_token(token: str | None) -> tuple[Optional[datetime], bool]:
    if not token:
        return None, False

    normalized = token.strip()
    if not normalized:
        return None, False

    lowered = normalized.lower()
    if lowered in {"permanent", "forever", "навсегда", "navsegda", "∞"}:
        return None, True

    if lowered.startswith("+") and lowered[1:].isdigit():
        days = int(lowered[1:])
        return now_utc() + timedelta(days=days), True

    if lowered.isdigit():
        days = int(lowered)
        return now_utc() + timedelta(days=days), True

    normalized_iso = normalized.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%d.%m.%Y"):
        try:
            if fmt is None:
                dt = datetime.fromisoformat(normalized_iso)
            else:
                dt = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        else:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, True

    return None, False


def _admin_user_button_label(user: dict) -> str:
    base = _admin_user_display_name(user)
    username = (user.get("username") or "").strip()
    fallback = str(user.get("tg_user_id") or user.get("id"))
    pieces = [piece for piece in [base if base != "—" else "", f"@{username}" if username else "", fallback] if piece]
    label = " ".join(dict.fromkeys(pieces)) or fallback
    text = f"#{user['id']} · {label}"
    if len(text) > 60:
        return text[:57] + "…"
    return text


def _admin_user_id_from_button(text: str, mapping: dict[str, int]) -> int | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned in mapping:
        return mapping[cleaned]
    for key, value in mapping.items():
        if key.strip() == cleaned:
            return value
    if cleaned.startswith("#"):
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


async def _fetch_users_page(segment: str, page: int) -> tuple[list[dict], int]:
    condition = _ADMIN_USER_SEGMENT_CONDITIONS.get(segment)
    if not condition:
        return [], 0

    limit = _ADMIN_USERS_PAGE_SIZE
    offset = max(0, (page - 1) * limit)

    rows = await fetch(
        f"""
        SELECT id, tg_user_id, username, full_name, name, email, phone, at_user_id,
               status, access_until, last_activity_at, joined_club_at, created_at
        FROM users
        WHERE {condition}
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )

    count_row = await fetchrow(f"SELECT COUNT(*) AS count FROM users WHERE {condition}")
    total = count_row["count"] if count_row else 0
    return [dict(row) for row in rows] if rows else [], total


async def _fetch_user_by_id(user_id: int) -> dict | None:
    row = await fetchrow("SELECT * FROM users WHERE id=$1", user_id)
    return dict(row) if row else None


async def _show_admin_users_list(
    message: types.Message,
    state: FSMContext,
    *,
    segment: str,
    page: int,
    notice: str | None = None,
) -> None:
    page = max(1, page)
    users, total = await _fetch_users_page(segment, page)
    total_pages = max(1, math.ceil(total / _ADMIN_USERS_PAGE_SIZE)) if total else 1

    if page > total_pages:
        page = total_pages
        users, total = await _fetch_users_page(segment, page)

    progress_map = await _collect_progress_map([user["id"] for user in users])
    payments_map = await _collect_last_payments(users)
    offset = (page - 1) * _ADMIN_USERS_PAGE_SIZE

    lines: list[str] = []
    if notice:
        lines.append(f"<b>{html.escape(notice)}</b>")
    lines.append(
        f"<b>Сегмент: {_admin_user_segment_label(segment)}</b> — страница {page} из {total_pages}"
        f"\nВсего пользователей: {total}"
    )

    if not users:
        lines.append("Пока нет пользователей в этом сегменте.")
    else:
        for idx, user in enumerate(users, start=1 + offset):
            display_name = html.escape(_admin_user_display_name(user))
            username_text = html.escape(_admin_user_username(user))
            tg_id = html.escape(str(user.get("tg_user_id") or "—"))
            status_value = user.get("status") or "—"
            status_title = _PROFILE_STATUS_TITLES.get(status_value, status_value)
            access_line = _admin_user_access_line(user)
            progress_summary = _admin_user_progress_summary(progress_map.get(user["id"]))
            payment_line = _format_payment_line(payments_map.get(user["id"]))

            lines.append(
                "\n".join(
                    [
                        f"{idx}. {display_name} — {username_text}",
                        f"ID: <code>{tg_id}</code>",
                        f"Статус: {html.escape(status_title)} ({html.escape(status_value)})",
                        f"Доступ до: {access_line}",
                        f"Прогресс: {progress_summary}",
                        f"Платёж: {payment_line}",
                    ]
                )
            )

    text = "\n\n".join(lines)
    button_labels = [_admin_user_button_label(user) for user in users]
    keyboard = admin_users_pagination_keyboard(
        button_labels,
        has_prev=page > 1,
        has_next=page < total_pages,
    )

    await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
    await state.set_state(AdminUserStates.browsing_users)
    await state.update_data(
        segment=segment,
        page=page,
        total_pages=total_pages,
        page_users={label: user["id"] for label, user in zip(button_labels, users)},
        selected_user_id=None,
    )


async def _show_admin_user_card(
    message: types.Message,
    state: FSMContext,
    *,
    user_id: int,
    notice: str | None = None,
) -> None:
    user = await _fetch_user_by_id(user_id)
    if not user:
        await message.answer("Пользователь не найден или уже удалён.")
        data = await state.get_data()
        segment = data.get("segment")
        page = data.get("page", 1)
        if segment:
            await _show_admin_users_list(message, state, segment=segment, page=page)
        else:
            await state.clear()
        return

    progress_map = await _collect_progress_map([user_id])
    payments_map = await _collect_last_payments([user])
    progress_summary = _admin_user_progress_summary(progress_map.get(user_id))
    payment_line = _format_payment_line(payments_map.get(user_id))
    access_line = _admin_user_access_line(user)

    status_value = user.get("status") or "—"
    status_title = _PROFILE_STATUS_TITLES.get(status_value, status_value)
    username_text = _admin_user_username(user)
    name_line = _admin_user_display_name(user)
    full_name = (user.get("full_name") or "").strip()
    last_activity = _format_datetime_safe(user.get("last_activity_at"))
    joined_at = _format_datetime_safe(user.get("joined_club_at"))
    utm_parts = [user.get("utm_source"), user.get("utm_medium"), user.get("utm_campaign")]
    utm_line = "/".join(filter(None, [part or "" for part in utm_parts])) or "—"

    lines: list[str] = []
    if notice:
        lines.append(f"<b>{html.escape(notice)}</b>")
    lines.append(f"<b>Пользователь #{user['id']}</b>")
    lines.append(f"Имя: {html.escape(name_line)}")
    if full_name and full_name != name_line:
        lines.append(f"ФИО: {html.escape(full_name)}")
    lines.append(
        f"Telegram: <code>{html.escape(str(user.get('tg_user_id') or '—'))}</code> {html.escape(username_text)}"
    )
    lines.append(f"Статус: {html.escape(status_title)} ({html.escape(status_value)})")
    lines.append(f"Доступ до: {access_line}")
    lines.append(f"Прогресс: {progress_summary}")
    lines.append(f"Последний платёж: {payment_line}")
    lines.append(f"Email: {html.escape(user.get('email') or '—')}")
    lines.append(f"Телефон: {html.escape(user.get('phone') or '—')}")
    lines.append(f"AT ID: {html.escape(user.get('at_user_id') or '—')}")
    lines.append(f"UTM: {html.escape(utm_line)}")
    lines.append(f"Присоединился: {joined_at}")
    lines.append(f"Активность: {last_activity}")

    text = "\n".join(lines)
    await message.answer(text, reply_markup=admin_user_card_keyboard(), disable_web_page_preview=True)
    await state.set_state(AdminUserStates.viewing_user)
    await state.update_data(selected_user_id=user_id)

_TEMPLATE_DELETE_PREFIX = "🗑️ "
_ONBOARDING_EDIT_PREFIX = "✏️ Шаг "
_ONBOARDING_DELETE_PREFIX = "🗑️ Шаг "


def _admin_text_labels(group_title: str) -> list[str]:
    entries = _ADMIN_TEXT_GROUPS.get(group_title, [])
    return [label for label, _ in entries]


def _admin_find_text_entry(label: str) -> tuple[Optional[str], Optional[str]]:
    for group_title, entries in _ADMIN_TEXT_GROUPS.items():
        for entry_label, key in entries:
            if entry_label == label:
                return group_title, key
    return None, None


def _merge_unique_content_keys(*sources: Iterable[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for source in sources:
        for key in source or []:
            if not key:
                continue
            key_str = str(key)
            if key_str in seen:
                continue
            seen.add(key_str)
            result.append(key_str)
            if limit is not None and len(result) >= limit:
                return result
    return result


async def _collect_content_suggestions(limit: int | None = _CONTENT_SUGGESTION_LIMIT) -> list[str]:
    db_keys = await list_content_keys_db()
    yaml_content = _load_yaml_content()
    yaml_keys = sorted(_flatten_yaml_keys(yaml_content))
    return _merge_unique_content_keys(db_keys, yaml_keys, limit=limit)


def _suggestion_chunk(
    keys: list[str],
    offset: int,
    step: int = _CONTENT_SUGGESTION_STEP,
) -> tuple[list[str], int, int, bool, bool]:
    total = len(keys)
    if total == 0:
        return [], 0, 0, False, False

    normalized = False
    if offset < 0 or offset >= total:
        offset = 0
        normalized = True

    end = min(offset + step, total)
    chunk = keys[offset:end]
    next_offset = 0 if end >= total else end
    reached_end = end >= total
    return chunk, next_offset, total, reached_end, normalized


def _describe_content_key(key: str) -> str:
    if not key:
        return ""

    if key in _CONTENT_KEY_HINTS:
        return _CONTENT_KEY_HINTS[key]

    if key.startswith("onboarding."):
        suffix = key.split(".", 1)[1]
        if suffix.isdigit():
            return f"Шаг онбординга #{int(suffix) + 1}"
        return "Шаг онбординга"

    if key.startswith("funnel.lesson_urls."):
        lesson = key.rsplit(".", 1)[-1]
        if lesson.isdigit():
            return f"Ссылка на урок {lesson}"
        return "Ссылка на урок"

    if key.startswith("funnel.hw_questions."):
        lesson = key.rsplit(".", 1)[-1]
        if lesson.isdigit():
            return f"Вопрос ДЗ для урока {lesson}"
        return "Вопрос для домашнего задания"

    offer_match = re.match(r"offer_after_lesson_(\d+)", key)
    if offer_match:
        return f"Оффер после урока {offer_match.group(1)}"

    if key.startswith("settings."):
        setting = key.split(".", 1)[1]
        label = _ADMIN_SETTINGS_LABELS.get(setting)
        if label:
            return f"Настройка: {label}"
        return "Настройка бота"

    if key.startswith("funnel."):
        return "Настройки воронки обучения"

    if "." not in key:
        return "Пользовательский текст из шаблона"

    return "Пользовательский текст"


def _format_suggestion_lines(keys: list[str]) -> list[str]:
    lines: list[str] = []
    for key in keys:
        description = _describe_content_key(key)
        if description:
            lines.append(f"• <code>{html.escape(key)}</code> — {html.escape(description)}")
        else:
            lines.append(f"• <code>{html.escape(key)}</code>")
    return lines


def _filter_suggestions(keys: list[str], query: str, limit: int = 5) -> list[str]:
    if not query:
        return []
    normalized = query.strip().lower()
    if not normalized:
        return []
    matches = [key for key in keys if normalized in key.lower()]
    return matches[:limit]


async def _send_content_key_suggestions(
    message: types.Message,
    query: str,
    matches: list[str],
) -> None:
    if not query:
        return

    escaped_query = html.escape(query)
    if matches:
        lines = [
            f"<b>Похожие ключи на запрос</b> <code>{escaped_query}</code>:",
            "",
        ]
        lines.extend(_format_suggestion_lines(matches))
        lines.extend(
            [
                "",
                "Можно выбрать ключ кнопкой из списка ниже или ввести его полностью вручную.",
            ]
        )
    else:
        lines = [
            f"Не нашёл ключи, похожие на <code>{escaped_query}</code>.",
            "Попробуй уточнить запрос или пролистай список через «🔁 Ещё варианты».",
        ]

    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def get_bool_setting(key: str, default: bool = True) -> bool:
    raw_value = await get_content(f"settings.{key}", "true" if default else "false")
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "y", "да"}:
        return True
    if normalized in {"0", "false", "no", "off", "n", "нет"}:
        return False
    return default


async def set_bool_setting(key: str, value: bool, *, updated_by: int | None = None) -> None:
    await set_content_value(
        f"settings.{key}",
        "true" if value else "false",
        updated_by=updated_by,
    )


async def get_menu_flags() -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for setting_key, default in _ADMIN_SETTINGS_DEFAULTS.items():
        flags[setting_key] = await get_bool_setting(setting_key, default)
    return flags


async def build_menu_keyboard(
    *,
    user: Optional[dict],
    is_admin: bool,
    section: str = "root",
) -> ReplyKeyboardMarkup:
    flags = await get_menu_flags()
    payments_open = flags.get("payments_open", True)
    weekly_enabled = flags.get("show_weekly_materials", True)
    schedule_enabled = flags.get("show_schedule", True)
    has_pay = bool(AT_PRODUCT_ID_CLUB)

    if section == "info":
        return info_menu_keyboard()
    if section == "learning":
        return learning_menu_keyboard()
    if section == "materials":
        return materials_menu_keyboard(
            weekly_enabled=weekly_enabled,
            schedule_enabled=schedule_enabled,
        )
    if section == "profile":
        return profile_menu_keyboard(
            has_pay=has_pay,
            payments_open=payments_open,
        )

    return main_menu_keyboard(
        is_admin=is_admin,
        has_pay=has_pay,
        payments_open=payments_open,
    )


async def answer_with_main_menu(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    text: str,
    *,
    section: str = "root",
    from_callback: bool = False,
) -> None:
    """Отправляет или обновляет сообщение с главным меню."""
    user_row = user or await get_user_with_id(message.from_user.id)
    kb = await build_menu_keyboard(user=user_row, is_admin=is_admin, section=section)
    await message.answer(text, reply_markup=kb)


async def send_menu_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    section: str,
    *,
    from_callback: bool = False,
) -> None:
    """Показывает выбранный раздел меню с соответствующей клавиатурой."""

    prompt_key, default_text = _MENU_SECTION_PROMPTS.get(
        section, _MENU_SECTION_PROMPTS["root"]
    )

    user_row = user
    if not user_row:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        if chat_id:
            user_row = await get_user_with_id(chat_id)

    prompt_text = await get_content(prompt_key, default_text)
    keyboard = await build_menu_keyboard(user=user_row, is_admin=is_admin, section=section)
    await message.answer(prompt_text, reply_markup=keyboard)


async def send_about_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    about_text = await get_content(
        "menu.about",
        (
            "CODE: Магнетизм — закрытое пространство для тех, кто хочет:\n\n"
            "- Управлять вниманием, мыслями и эмоциями\n"
            "- Укрепить уверенность и личный магнетизм\n"
            "- Изменить сценарии в отношениях и деньгах\n\n"
            "Внутри тебя ждут:\n"
            "- Подкасты и практики\n"
            "- Челленджи и разборы\n"
            "- Структурная система развития\n\n"
            "Готова присоединиться? Оформи доступ в меню."
        ),
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        about_text,
        section="info",
        from_callback=from_callback,
    )


async def send_faq_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    faq_text = await get_content(
        "menu.faq",
        (
            "FAQ.\n\n"
            "Как получить доступ? — Оформи участие в разделе «Оплата».\n\n"
            "Как проходят уроки? — Видеоуроки + практики, доступ через меню.\n\n"
            f"Как задать вопрос? — Кнопка «Вопрос» в уроке или {SUPPORT_CONTACT}.\n\n"
            "Как продлить доступ? — Раздел «Оплата»."
        ),
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        faq_text,
        section="info",
        from_callback=from_callback,
    )


async def send_rules_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    rules_text = await get_content(
        "menu.rules",
        (
            "Правила CODE: Магнетизм.\n\n"
            "1. Уважение к участникам.\n"
            "2. Только полезный контент.\n"
            "3. Без спама и рекламы.\n"
            "4. Конфиденциальность.\n"
            "5. Без оскорблений и дискриминации.\n\n"
            "Нарушение = блокировка доступа."
        ),
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        rules_text,
        section="info",
        from_callback=from_callback,
    )


async def send_analysis_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)
    if not user_row:
        user_row = await ensure_user(message.from_user)

    default_url = "https://forms.example.com/analysis"
    template = await get_content(
        "menu.analysis",
        (
            "Персональный разбор.\n\n"
            "Заполни форму → мы назначим время.\n\n"
            "{analysis_url}"
        ),
    )
    analysis_text = render_content(
        template,
        analysis_url=default_url,
        ANALYSIS_URL=default_url,
    )

    if user_row:
        form_url = extract_first_url(analysis_text) or default_url
        slug = resolve_form_slug(form_url, FORM_SLUG_ANALYSIS)
        if slug:
            try:
                await mark_form_started(user_row["id"], slug)
            except Exception as e:
                logger.warning(
                    "form_session: mark start failed user_id=%s slug=%s: %s",
                    user_row.get("id"),
                    slug,
                    e,
                )

    await answer_with_main_menu(
        message,
        user_row,
        is_admin,
        analysis_text,
        section="learning",
        from_callback=from_callback,
    )


async def send_test_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
    only_text: bool = False,
) -> tuple[str, Optional[str]] | None:
    user_row = user or await get_user_with_id(message.from_user.id)
    if not user_row:
        user_row = await ensure_user(message.from_user)

    template = await get_content(
        "menu.test",
        (
            "Тест: определение уровня.\n\n"
            "Пройди тест и получи анализ.\n\n"
            "После теста ты получишь анализ, рекомендации и сможешь записаться на разбор."
        ),
    )
    default_slug = resolve_form_slug(TEST_FORM_URL, "test")
    test_text = render_content(
        template,
        test_url=TEST_FORM_URL,
        TEST_FORM_URL=TEST_FORM_URL,
        test_slug=default_slug or "",
        TEST_SLUG=default_slug or "",
    )

    slug = resolve_form_slug(TEST_FORM_URL, default_slug or FORM_SLUG_TEST) or FORM_SLUG_TEST
    if user_row:
        form_url = extract_first_url(test_text) or TEST_FORM_URL
        resolved = resolve_form_slug(form_url, slug)
        if resolved:
            slug = resolved
        try:
            await mark_form_started(user_row["id"], slug)
        except Exception as e:
            logger.warning(
                "form_session: mark start failed user_id=%s slug=%s: %s",
                user_row.get("id"),
                slug,
                e,
            )

    if only_text:
        return test_text, slug

    await answer_with_main_menu(
        message,
        user_row,
        is_admin,
        test_text,
        section="learning",
        from_callback=from_callback,
    )
    return test_text, slug


async def send_support_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    support_template = await get_content(
        "menu.support",
        (
            "Поддержка.\n\n"
            "Если есть вопросы или сложности — пиши сюда: {support}. Мы отвечаем лично и максимально быстро."
        ),
    )
    support_text = render_content(
        support_template,
        support=SUPPORT_CONTACT,
        SUPPORT_CONTACT=SUPPORT_CONTACT,
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        support_text,
        section="root",
        from_callback=from_callback,
    )


async def send_profile_overview(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)
    if not user_row:
        await answer_with_main_menu(
            message,
            user_row,
            is_admin,
            "Профиль не найден. Перезапусти /start, чтобы обновить данные.",
            section="profile",
            from_callback=from_callback,
        )
        return

    status_key = user_row.get("status") or "lead_funnel"
    status_label = _PROFILE_STATUS_TITLES.get(status_key, "—")

    access_until = user_row.get("access_until")
    access_line = "Доступ пока не активирован."
    if status_key == "member_active":
        if access_until:
            dt = access_until
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                except ValueError:
                    dt = None
            if isinstance(dt, datetime):
                access_line = f"Доступ активен до {tz_aware_msk(dt)}"
            else:
                access_line = "Доступ активен."
        else:
            access_line = "Доступ активен."
    elif status_key == "member_expired":
        if access_until:
            dt = access_until
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                except ValueError:
                    dt = None
            if isinstance(dt, datetime):
                access_line = f"Доступ истёк {tz_aware_msk(dt)}"
            else:
                access_line = "Доступ истёк."
        else:
            access_line = "Доступ истёк."

    email_value = user_row.get("email") or "—"
    phone_value = user_row.get("phone") or "—"
    name_value = user_row.get("name") or (user_row.get("full_name") or "—")

    profile_text = (
        "<b>Твой профиль</b>\n\n"
        f"Имя: {html.escape(name_value)}\n"
        f"Email: {html.escape(email_value)}\n"
        f"Телефон: {html.escape(phone_value)}\n\n"
        f"Статус: {status_label}\n"
        f"{access_line}\n\n"
        "Используй кнопки ниже, чтобы обновить контакты."
    )

    keyboard = await build_menu_keyboard(
        user=user_row,
        is_admin=is_admin,
        section="profile",
    )

    await message.answer(profile_text, reply_markup=keyboard)


async def send_weekly_materials_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)

    weekly_enabled = await get_bool_setting(
        "show_weekly_materials", _ADMIN_SETTINGS_DEFAULTS["show_weekly_materials"]
    )
    if not weekly_enabled:
        disabled_text = await get_content(
            "menu.weekly.disabled",
            "Раздел «Материалы недели» временно закрыт. Загляни позже — мы сообщим о новых материалах дополнительно.",
        )
        await answer_with_main_menu(
            message,
            user_row,
            is_admin,
            disabled_text,
            section="materials",
            from_callback=from_callback,
        )
        return

    if not user_row or not await is_member(user_row):
        locked_text = await get_content(
            "menu.weekly.locked",
            (
                "Материалы недели доступны участницам клуба.\n\n"
                f"Оформи доступ в разделе «{ADMIN_PAYMENTS_BUTTON}», и бот пришлёт ссылки автоматически."
            ),
        )
        await answer_with_main_menu(
            message,
            user_row,
            is_admin,
            locked_text,
            section="materials",
            from_callback=from_callback,
        )
        return

    weekly_text = await get_content(
        "weekly_materials",
        (
            "📚 Материалы недели:\n"
            "• Подкаст: [ссылка]\n"
            "• Практика: [ссылка]\n"
            "• Челлендж: [описание]\n"
            "• Дневник: [шаблон]"
        ),
    )

    await answer_with_main_menu(
        message,
        user_row,
        is_admin,
        weekly_text,
        section="materials",
        from_callback=from_callback,
    )


async def send_schedule_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)

    schedule_enabled = await get_bool_setting(
        "show_schedule", _ADMIN_SETTINGS_DEFAULTS["show_schedule"]
    )
    if not schedule_enabled:
        disabled_text = await get_content(
            "menu.schedule.disabled",
            "Расписание временно недоступно. Мы обновляем расписание и пришлём уведомление, как только оно появится.",
        )
        await answer_with_main_menu(
            message,
            user_row,
            is_admin,
            disabled_text,
            section="materials",
            from_callback=from_callback,
        )
        return

    if not user_row or not await is_member(user_row):
        locked_text = await get_content(
            "menu.schedule.locked",
            (
                "Расписание доступно участницам клуба.\n\n"
                "Активируй доступ — и бот пришлёт ближайшие эфиры."
            ),
        )
        await answer_with_main_menu(
            message,
            user_row,
            is_admin,
            locked_text,
            section="materials",
            from_callback=from_callback,
        )
        return

    schedule_text = await get_content(
        "schedule",
        (
            "🗓️ Расписание эфиров:\n"
            "• Понедельник 20:00 — Вводный эфир\n"
            "• Четверг 19:00 — Практика в группе\n"
            "• Воскресенье 18:00 — Подведение итогов"
        ),
    )

    await answer_with_main_menu(
        message,
        user_row,
        is_admin,
        schedule_text,
        section="materials",
        from_callback=from_callback,
    )


async def send_magnetism_window_section(
    message: types.Message,
    user: dict,
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    default_form_url = "https://forms.gle/iNcUGfiLGNkLW1dc8"
    template = await get_content(
        "menu.learning.magnetism_window",
        (
            "Окно в Магнетизм.\n\n"
            "Заполни форму и получи доступ к следующему шагу.\n\n"
            "{form_url}"
        ),
    )
    default_slug = resolve_form_slug(default_form_url, "magnetism-window")
    message_text = render_content(
        template,
        form_url=default_form_url,
        FORM_URL=default_form_url,
        form_slug=default_slug or "",
        FORM_SLUG=default_slug or "",
    )

    displayed_form_url = extract_first_url(message_text) or default_form_url
    slug = resolve_form_slug(displayed_form_url, default_slug or "magnetism-window")

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        message_text,
        section="learning",
        from_callback=from_callback,
    )

    if slug:
        await mark_form_started(user.get("id"), slug)


async def send_pay_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    checkout_url = (YOOMONEY_CHECKOUT_URL or "").strip()
    if not checkout_url and AT_PRODUCT_ID_CLUB:
        checkout_url = f"https://antitraining.example/checkout/{AT_PRODUCT_ID_CLUB}"

    if not checkout_url:
        await answer_with_main_menu(
            message,
            user,
            is_admin,
            "Сейчас доступ в клуб бесплатный.",
            section="root",
            from_callback=from_callback,
        )
        return

    flags = await get_menu_flags()
    payments_open = flags.get("payments_open", True)
    if not payments_open:
        closed_text = await get_content(
            "menu.pay.closed",
            "Оплата временно закрыта. Мы сообщим о новом окне, как только оно откроется.",
        )
        await answer_with_main_menu(
            message,
            user,
            is_admin,
            closed_text,
            section="root",
            from_callback=from_callback,
        )
        return

    pay_template = await get_content(
        "menu.pay",
        (
            "Доступ в клуб CODE: Магнетизм.\n\n"
            "Тариф: Полный доступ — 2690₽ (единовременно).\n\n"
            "Ссылка на оплату: {checkout_url}\n\n"
            "После оплаты бот автоматически активирует доступ."
        ),
    )
    pay_text = render_content(
        pay_template,
        checkout_url=checkout_url,
        CHECKOUT_URL=checkout_url,
    )

    if flags.get("payments_manual_review", False):
        manual_hint = await get_content(
            "menu.pay.manual_review",
            (
                "Платежи проходят ручную проверку. "
                "Если вы уже оплатили, команда подтвердит доступ и пришлёт уведомление."
            ),
        )
        if manual_hint:
            pay_text = f"{pay_text}\n\n{manual_hint.strip()}"

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        pay_text,
        section="root",
        from_callback=from_callback,
    )


async def send_funnel_section(
    message: types.Message,
    user: dict,
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    n = await next_lesson_to_deliver(user["id"])

    if n == 5:
        completed_text = await get_content(
            "menu.funnel.completed",
            (
                "Все уроки пройдены.\n\n"
                "Дальше — клуб CODE: Магнетизм: углублённые практики, сообщество, живые эфиры."
            ),
        )
        await answer_with_main_menu(
            message,
            user,
            is_admin,
            completed_text,
            section="learning",
        )
        return

    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции",
    }

    lines = [
        "Бесплатные уроки\n",
        "Доступные уроки отмечены галочкой. Урок откроется после завершения предыдущего.\n",
    ]

    for i in range(1, 5):
        status = "✅" if i < n else ("⏳" if i == n else "🔒")
        lines.append(f"{status} Урок {i}: {lesson_titles.get(i, f'Урок {i}')}\n")

    keyboard = lessons_overview_keyboard(n)
    await message.answer("".join(lines), reply_markup=keyboard)


async def send_admin_menu(
    message: types.Message,
    *,
    from_callback: bool = False,
) -> None:
    admin_text = (
        "<b>Админ-панель</b>\n\n"
        "Здесь собраны основные инструменты:\n"
        "• 👥 Пользователи — сегменты, карточки профилей и управление доступом.\n"
        "• 📢 Рассылка — как отправлять сообщения сегментам.\n"
        "• 🧾 Контент и тексты — редактирование сообщений бота без команд.\n"
        "• 🎛 Логика бота — сценарии приветствия, онбординг и доступ к оплатам.\n"
        "• 📊 Статистика — сводка по статусам, прогресс уроков и последние оплаты.\n"
        "• 🛠️ Диагностика — проверка важных настроек.\n"
        "• ⚙️ Настройки — управление разделами меню и вспомогательными опциями.\n\n"
        "Выберите раздел, чтобы открыть расширенную статистику, карточки пользователей или настроить сценарии бота."
    )
    await message.answer(
        admin_text,
        reply_markup=admin_main_keyboard(),
        disable_web_page_preview=True,
    )


async def send_admin_settings(
    message: types.Message,
    *,
    from_callback: bool = False,
) -> None:
    flags = await get_menu_flags()
    text = (
        "Тонкие настройки бота\n\n"
        f"Окно оплаты: {'открыто' if flags.get('payments_open', True) else 'закрыто'}\n"
        f"Ручная проверка оплат: {'включена' if flags.get('payments_manual_review', False) else 'выключена'}\n"
        f"Материалы недели: {'доступны' if flags.get('show_weekly_materials', True) else 'скрыты'}\n"
        f"Расписание: {'показывается' if flags.get('show_schedule', True) else 'скрыто'}\n\n"
        "Используй кнопки ниже, чтобы включать и выключать опции.\n\n"
        "Готово? Вернись через «⬅️ В админку» или открой главное меню."
    )
    keyboard = admin_settings_keyboard(flags, _ADMIN_SETTINGS_LABELS)

    await message.answer(text, reply_markup=keyboard)


async def send_admin_behavior_menu(message: types.Message) -> None:
    text = (
        "<b>Логика бота</b>\n\n"
        "Здесь можно быстро настроить ключевые сценарии и управление доступами:\n"
        "• Изменить приветствие при /start.\n"
        "• Обновить сообщение после регистрации.\n"
        "• Управлять шагами онбординга для новых участниц.\n"
        "• Открыть раздел «💳 Оплаты» для ручных операций с платежами.\n\n"
        "Выбирай нужный раздел — бот попросит только текст, остальное он сделает сам."
    )
    await message.answer(
        text,
        reply_markup=admin_behavior_keyboard(),
        disable_web_page_preview=True,
    )


async def send_admin_payments_overview(message: types.Message) -> None:
    flags = await get_menu_flags()
    payments_open = flags.get("payments_open", True)
    manual_review = flags.get("payments_manual_review", False)
    payments = await _fetch_recent_payments(limit=5)

    status_line = "открыто" if payments_open else "закрыто"
    review_line = "включена" if manual_review else "выключена"

    lines = [
        "<b>💳 Управление оплатами</b>",
        "",
        f"Окно оплаты: <b>{status_line}</b>",
        f"Ручная проверка: <b>{review_line}</b>",
    ]

    if payments:
        lines.append("\n<b>Последние платежи:</b>")
        for payment in payments:
            lines.append(_format_admin_payment_entry(payment))
    else:
        lines.append("\nПока нет записей о платежах.")

    lines.extend(
        [
            "",
            "<i>Подсказки:</i>",
            "• Кнопки 🔓/🔒 открывают или закрывают окно оплаты.",
            "• «🧾 Последние платежи» обновляет список ниже.",
            "• «✅ Подтвердить доступ» и «🚫 Приостановить доступ» требуют @username или ID участницы.",
            "• Кнопки отметки платежа добавят отметку о ручной проверке в карточку платежа.",
            "• «⬅️ К логике бота» вернёт к настройкам сценариев и оплат.",
        ]
    )

    keyboard = admin_payments_keyboard(payments_open=payments_open)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def send_admin_onboarding_menu(message: types.Message) -> None:
    steps = await get_onboarding_steps()
    summary = format_onboarding_summary(steps)
    text = (
        "<b>Шаги онбординга</b>\n\n"
        "Эти сообщения бот отправляет новым участницам после оплаты.\n"
        "Можно редактировать существующие шаги, добавлять новые и удалять лишние.\n\n"
        f"<b>Текущий сценарий:</b>\n{html.escape(summary)}"
    )
    await message.answer(
        text,
        reply_markup=admin_onboarding_steps_keyboard(steps),
        disable_web_page_preview=True,
    )


async def send_admin_broadcast_menu(message: types.Message) -> None:
    text = (
        "<b>Рассылка</b>\n\n"
        "Выберите сегмент, напишите текст — бот покажет предпросмотр и спросит подтверждение.\n"
        "Можно сохранять тексты как шаблоны и переиспользовать их позже."
    )
    await message.answer(
        text,
        reply_markup=admin_broadcast_keyboard(),
        disable_web_page_preview=True,
    )


async def send_admin_broadcast_templates(message: types.Message) -> None:
    templates = await list_broadcast_templates()
    titles = [tpl["title"] for tpl in templates]
    if not templates:
        text = (
            "<b>Шаблоны рассылок</b>\n\n"
            "Пока шаблонов нет. Сохрани любой текст после предпросмотра — и он появится здесь."
        )
    else:
        lines = [
            "<b>Шаблоны рассылок</b>",
            "",
        ]
        for tpl in templates:
            segment = tpl.get("segment") or "all"
            segment_label = _BROADCAST_SEGMENT_LABELS.get(segment, segment)
            preview = _preview_text_for_admin(tpl.get("body", ""), limit=200)
            lines.append(f"• <b>{html.escape(tpl['title'])}</b> — {segment_label}\n{preview}")
        text = "\n".join(lines)

    await message.answer(
        text,
        reply_markup=admin_broadcast_templates_keyboard(titles),
        disable_web_page_preview=True,
    )


async def send_admin_content_menu(message: types.Message) -> None:
    text = (
        "<b>Контент и тексты</b>\n\n"
        "Здесь можно:\n"
        "• 📄 <b>Тексты экранов</b> — выбрать готовый экран и обновить его текст.\n"
        "• 🔍 <b>Посмотреть текст</b> — узнать текущее содержимое любого ключа и при необходимости сразу обновить его ответом.\n"
        "• ➕ <b>Добавить или обновить текст</b> — создать свой ключ или выбрать существующий из подсказок.\n\n"
        "• ⬇️ <b>Экспорт</b> — выгрузить все ключи в YAML и JSON для резервной копии.\n"
        "• ⬆️ <b>Импорт</b> — загрузить подготовленный файл и массово обновить тексты.\n\n"
        "Можно писать обычным текстом — бот автоматически преобразует популярные сокращения в теги и очищает форматирование.\n"
        "Подробности о тегах и примерах — в кнопке «ℹ️ Форматирование текста».\n"
        "Допустимы теги: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;u&gt;</code>, <code>&lt;strong&gt;</code>, <code>&lt;em&gt;</code>, <code>&lt;code&gt;</code>, <code>&lt;a href=&quot;...&quot;&gt;</code>.\n"
        "Бот подсказывает популярные ключи и запоминает последние изменения, чтобы можно было быстро вносить правки.\n"
        "Достаточно набрать несколько символов — бот пришлёт подходящие ключи с описанием, чтобы быстрее найти нужный текст.\n"
        "Если нужно отменить действие — нажми кнопку «Отмена»."
    )
    keyboard = admin_content_keyboard()
    await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


async def send_admin_text_groups(message: types.Message) -> None:
    text = (
        "<b>Редактор текстов бота</b>\n\n"
        "1️⃣ Выбери раздел, где лежит нужное сообщение.\n"
        "2️⃣ Затем выбери сам текст — бот покажет текущее содержимое и попросит новый вариант.\n\n"
        "Можно вернуться в меню контента кнопкой «🧾 Контент и тексты»."
    )
    keyboard = admin_text_groups_keyboard(list(_ADMIN_TEXT_GROUPS.keys()))
    await message.answer(text, reply_markup=keyboard)


async def send_admin_text_items(message: types.Message, group_title: str) -> None:
    labels = _admin_text_labels(group_title)
    if not labels:
        await message.answer(
            "В этой группе пока нет текстов. Выбери другой раздел.",
            reply_markup=admin_text_groups_keyboard(list(_ADMIN_TEXT_GROUPS.keys())),
        )
        return

    text = (
        f"<b>Группа «{group_title}»</b>\n\n"
        "Выбери текст, который нужно обновить — бот покажет текущую версию и попросит прислать новый вариант."
    )
    keyboard = admin_text_items_keyboard(labels)
    await message.answer(text, reply_markup=keyboard)

async def ensure_user(tg_user: types.User, utm: dict | None = None) -> dict:
    """
    Создаёт пользователя при первом входе, либо возвращает его запись.
    Обновляет username/full_name/utm при необходимости.
    """
    row = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user.id)
    if row:
        # Обновляем UTM, если они предоставлены
        utm_updates = {}
        if utm:
            if 'utm_source' in utm and utm['utm_source']:
                utm_updates['utm_source'] = utm['utm_source']
            if 'utm_medium' in utm and utm['utm_medium']:
                utm_updates['utm_medium'] = utm['utm_medium']
            if 'utm_campaign' in utm and utm['utm_campaign']:
                utm_updates['utm_campaign'] = utm['utm_campaign']
        
        update_fields = ["username=$2", "full_name=$3", "last_activity_at=NOW()", "updated_at=NOW()"]
        params = [tg_user.id, tg_user.username, tg_user.full_name]
        param_count = 3
        
        for field, value in utm_updates.items():
            param_count += 1
            update_fields.append(f"{field}=${param_count}")
            params.append(value)
        
        await execute(
            f"UPDATE users SET {', '.join(update_fields)} WHERE tg_user_id=$1",
            *params
        )
        return await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user.id)
    
    utm_source = (utm or {}).get("utm_source")
    utm_medium = (utm or {}).get("utm_medium")
    utm_campaign = (utm or {}).get("utm_campaign")
    
    await execute(
        """INSERT INTO users (tg_user_id, username, full_name, utm_source, utm_medium, utm_campaign, created_at, updated_at, last_activity_at)
           VALUES ($1,$2,$3,$4,$5,$6, NOW(), NOW(), NOW())""",
        tg_user.id, tg_user.username, tg_user.full_name, utm_source, utm_medium, utm_campaign
    )
    
    created = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user.id)
    logger.info("ensure_user: created user tg_id=%s id=%s", tg_user.id, created["id"])
    return created
async def is_member(user_row: dict) -> bool:
    if not user_row:
        return False
    
    status = user_row.get("status")
    access_until = user_row.get("access_until")
    
    if status == "member_active":
        if access_until is None:
            return True

        if access_until > now_utc():
            return True

        # Если срок доступа истек, обновляем статус только при наличии даты
        await execute(
            "UPDATE users SET status='member_expired', updated_at=NOW() WHERE id=$1",
            user_row["id"]
        )

    return False
def parse_start_utm(text: Optional[str]) -> dict:
    if not text or " " not in text:
        return {}
    try:
        _, payload = text.split(" ", 1)
        # Убираем начальный "/start " если есть
        if payload.startswith("/start "):
            payload = payload[7:]
        qs = parse_qs(payload, keep_blank_values=True)
        return {k: (v[0] if isinstance(v, list) else v) for k, v in qs.items()}
    except Exception:
        return {}
async def upsert_funnel_delivery(user_id: int, lesson_num: int) -> None:
    row = await fetchrow(
        "SELECT id FROM funnel_progress WHERE user_id=$1 AND lesson_num=$2", user_id, lesson_num
    )
    if row:
        return
    await execute(
        """INSERT INTO funnel_progress (user_id, lesson_num, delivered_at, hw_status)
           VALUES ($1,$2, NOW(), 'pending')""",
        user_id, lesson_num
    )
    logger.info("funnel: delivered user_id=%s lesson=%s", user_id, lesson_num)
async def mark_lesson_done(user_id: int, lesson_num: int, hw_answer: Optional[str] = None) -> None:
    await execute(
        """UPDATE funnel_progress
           SET opened_at=COALESCE(opened_at, NOW()),
               hw_status='submitted',
               hw_answer=COALESCE($3, hw_answer)
           WHERE user_id=$1 AND lesson_num=$2""",
        user_id, lesson_num, hw_answer
    )
    logger.info("funnel: done user_id=%s lesson=%s", user_id, lesson_num)
async def mark_lesson_skipped(user_id: int, lesson_num: int) -> None:
    await execute(
        """UPDATE funnel_progress
           SET opened_at=COALESCE(opened_at, NOW()),
               hw_status='skipped'
           WHERE user_id=$1 AND lesson_num=$2""",
        user_id, lesson_num
    )
    logger.info("funnel: skipped user_id=%s lesson=%s", user_id, lesson_num)
async def save_lesson_feedback(user_id: int, lesson_num: int, feedback_type: str, feedback_text: str = None) -> None:
    """Сохраняет обратную связь по уроку"""
    await execute(
        """INSERT INTO lesson_feedback (user_id, lesson_num, feedback_type, feedback_text, created_at)
           VALUES ($1, $2, $3, $4, NOW())""",
        user_id, lesson_num, feedback_type, feedback_text
    )
    logger.info("feedback saved: user_id=%s lesson=%s type=%s", user_id, lesson_num, feedback_type)


async def mark_form_started(user_id: int, form_slug: str) -> None:
    slug = resolve_form_slug(form_slug)
    if not slug:
        return

    await execute(
        """
        INSERT INTO form_sessions (user_id, form_slug, started_at, completed_at, last_reminder_at, reminder_count)
        VALUES ($1, $2, NOW(), NULL, NULL, 0)
        ON CONFLICT (user_id, form_slug) DO UPDATE
        SET started_at = CASE
                WHEN form_sessions.completed_at IS NOT NULL THEN EXCLUDED.started_at
                ELSE form_sessions.started_at
            END,
            completed_at = NULL,
            last_reminder_at = CASE
                WHEN form_sessions.completed_at IS NOT NULL THEN NULL
                ELSE form_sessions.last_reminder_at
            END,
            reminder_count = CASE
                WHEN form_sessions.completed_at IS NOT NULL THEN 0
                ELSE form_sessions.reminder_count
            END
        """,
        user_id,
        slug,
    )
    logger.info("form_session: started user_id=%s slug=%s", user_id, slug)


async def mark_form_completed(user_id: int, form_slug: str) -> tuple[Optional[dict], bool]:
    slug = resolve_form_slug(form_slug)
    if not slug:
        return None, False

    existing = await fetchrow(
        "SELECT * FROM form_sessions WHERE user_id=$1 AND form_slug=$2",
        user_id,
        slug,
    )
    if existing and existing.get("completed_at"):
        return existing, False

    if existing:
        row = await fetchrow(
            """
            UPDATE form_sessions
            SET completed_at = NOW(),
                last_reminder_at = NULL
            WHERE id = $1
            RETURNING *
            """,
            existing["id"],
        )
        logger.info("form_session: completed user_id=%s slug=%s (existing)", user_id, slug)
        return row, True

    row = await fetchrow(
        """
        INSERT INTO form_sessions (user_id, form_slug, started_at, completed_at, last_reminder_at, reminder_count)
        VALUES ($1, $2, NOW(), NOW(), NULL, 0)
        RETURNING *
        """,
        user_id,
        slug,
    )
    logger.info("form_session: completed user_id=%s slug=%s (new)", user_id, slug)
    return row, True
async def get_user_with_id(tg_user_id: int) -> Optional[dict]:
    return await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user_id)
async def next_lesson_to_deliver(user_id: int) -> int:
    rows = await fetch(
        "SELECT lesson_num FROM funnel_progress WHERE user_id=$1 ORDER BY lesson_num", user_id
    )
    delivered = {r["lesson_num"] for r in rows} if rows else set()
    for i in range(1, 5):
        if i not in delivered:
            return i
    return 5


async def deliver_lesson(
    message: types.Message,
    user: dict,
    lesson_num: int,
    state: FSMContext,
) -> None:
    """Отправляет карточку урока и фиксирует выдачу в воронке."""

    if lesson_num not in (1, 2, 3, 4):
        await message.answer("Урок пока недоступен. Попробуй выбрать другой.")
        return

    if user is None:
        await message.answer("Не удалось загрузить профиль. Перезапусти /start.")
        return

    # Сбрасываем активный FSM-стейт, если пользователь был в другом сценарии
    await _reset_state_if_needed(state)
    await state.set_state(None)
    await state.update_data(active_lesson=lesson_num)

    try:
        await upsert_funnel_delivery(user["id"], lesson_num)
    except Exception as e:
        logger.warning("deliver_lesson: upsert failed for user=%s lesson=%s: %s", user.get("id"), lesson_num, e)

    funnel_cfg = (_load_yaml_content() or {}).get("funnel") or {}
    lesson_urls = funnel_cfg.get("lesson_urls") or {}
    hw_questions = funnel_cfg.get("hw_questions") or {}

    url = ""
    if isinstance(lesson_urls, dict):
        url = str(lesson_urls.get(lesson_num) or "").strip()

    hw_prompt = "Короткое ДЗ: ответь одной фразой."
    if isinstance(hw_questions, dict):
        hw_prompt = str(hw_questions.get(lesson_num) or hw_prompt).strip() or hw_prompt

    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции",
    }
    title = lesson_titles.get(lesson_num, f"Урок {lesson_num}")

    parts: list[str] = [f"<b>Урок {lesson_num}/4.</b> {title}"]
    if url:
        parts.append(f"Смотри урок: {url}")
    parts.append(hw_prompt)
    parts.append("Когда будешь готова, отметь урок через кнопки ниже.")

    text = "\n\n".join(parts)

    keyboard = lesson_actions_keyboard()

    async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
        await asyncio.sleep(0.2)
        await message.answer(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=not bool(url),
        )
def tz_aware_msk(dt: datetime) -> str:
    return dt.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M MSK")
async def generate_invite_link_or_placeholder(bot, chat_id: str) -> str:
    """
    Генерирует одноразовую ссылку-приглашение, если указан CLUB_CHAT_ID и бот админ.
    Иначе возвращает плейсхолдер.
    """
    if not chat_id:
        return "Инвайт будет выслан вручную администратором."
    try:
        numeric_chat_id = int(chat_id) if isinstance(chat_id, str) and chat_id.strip().lstrip("-").isdigit() else chat_id
        expire = int((datetime.now(timezone.utc) + timedelta(hours=24)).timestamp())
        link = await bot.create_chat_invite_link(
            chat_id=numeric_chat_id,
            expire_date=expire,
            member_limit=1,
            creates_join_request=False
        )
        return link.invite_link
    except Exception as e:
        logger.warning("create_chat_invite_link failed: %s", e)
        return "Инвайт будет выслан вручную администратором."
# ──────────────────────────────────────────────────────────────────────────────
# Валидации
# ──────────────────────────────────────────────────────────────────────────────
_email_re = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_phone_digits_re = re.compile(r"[^\d+]")
def normalize_phone(s: str) -> str:
    s = (s or "").strip()
    s = _phone_digits_re.sub("", s)
    
    # Нормализация российских номеров
    if s.startswith("8") and len(s) == 11:
        s = "+7" + s[1:]
    elif s.startswith("7") and len(s) == 11:
        s = "+" + s
    elif len(s) == 10 and s.isdigit():
        s = "+7" + s
    
    # Добавляем + если его нет
    if not s.startswith("+") and s:
        s = "+" + s
    
    return s
def validate_phone(phone: str) -> bool:
    """Проверяет, соответствует ли номер международному формату"""
    phone = normalize_phone(phone)
    # Проверяем, что номер начинается с + и содержит только цифры после +
    if not phone.startswith('+'):
        return False
    
    # Убираем + и проверяем, что остались только цифры
    digits = phone[1:]
    if not digits.isdigit():
        return False
    
    # Проверяем минимальную длину номера (включая код страны)
    return len(digits) >= 7
def validate_email(email: str) -> bool:
    """Проверяет валидность email адреса"""
    return bool(_email_re.match(email))
# ──────────────────────────────────────────────────────────────────────────────
# Router и хэндлеры
# ──────────────────────────────────────────────────────────────────────────────
router = Router(name="main-router")
@router.my_chat_member()
async def on_my_chat_member(event: types.ChatMemberUpdated):
    try:
        await event.bot.send_message(
            event.from_user.id,
            "Привет! Напиши /start, чтобы открыть меню"
        )
    except Exception as e:
        logger.error(f"Error in my_chat_member: {e}", exc_info=True)
# /start — создаём пользователя, захватываем UTM, показываем меню
@router.message(CommandStart())
async def on_start(message: types.Message, state: FSMContext):
    # Проверяем, зарегистрирован ли уже пользователь
    user = await get_user_with_id(message.from_user.id)
    
    # Если пользователь не зарегистрирован, создаем его
    if not user:
        utm_params = parse_start_utm(message.text)
        user_row = await ensure_user(message.from_user, utm=utm_params)
        user = await get_user_with_id(message.from_user.id)  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
    
    # Проверяем, завершена ли регистрация
    if not user.get("name") or not user.get("email") or not user.get("phone"):
        # Начинаем процесс регистрации
        await state.set_state(RegistrationStates.waiting_name)
        await message.answer(
            "Добро пожаловать! Для начала нам нужно познакомиться. Как тебя зовут?",
            reply_markup=cancel_keyboard()
        )
        return
    
    # Показываем главное меню
    is_admin = is_admin_id(message.from_user.id)
    kb = await build_menu_keyboard(user=user, is_admin=is_admin, section="root")
    
    welcome_template = await get_content(
        "menu.start",
        "Добро пожаловать в CODE: Магнетизм. Это пространство для развития и перемен. Выбери раздел в меню, чтобы начать, {name}!",
    )
    display_name = (
        user.get("name")
        or user.get("full_name")
        or message.from_user.full_name
        or message.from_user.first_name
        or "друг"
    )
    welcome_text = render_content(
        welcome_template,
        name=display_name,
        NAME=display_name,
    )

    async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
        await asyncio.sleep(0.15)
        await message.answer(welcome_text, reply_markup=kb)

# Обработка ввода имени при регистрации
@router.message(RegistrationStates.waiting_name, F.text.len() > 0)
async def registration_receive_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    
    # Сохраняем имя
    await execute("UPDATE users SET name=$2, updated_at=NOW() WHERE tg_user_id=$1", message.from_user.id, name)
    
    # Переходим к вводу email
    await state.set_state(RegistrationStates.waiting_email)
    await message.answer(
        "Укажи email для связи:",
        reply_markup=cancel_keyboard()
    )

# Обработка ввода email при регистрации
@router.message(RegistrationStates.waiting_email, F.text.len() > 0)
async def registration_receive_email(message: types.Message, state: FSMContext):
    email = (message.text or "").strip()
    
    if not validate_email(email):
        await message.answer(
            "Формат неверный. Пример: name@mail.com",
            reply_markup=cancel_keyboard()
        )
        return
    
    # Сохраняем email
    await execute("UPDATE users SET email=$2, updated_at=NOW() WHERE tg_user_id=$1", message.from_user.id, email)
    
    # Переходим к вводу телефона
    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer(
        "Укажи номер телефона:",
        reply_markup=cancel_keyboard()
    )

# Обработка ввода телефона при регистрации
@router.message(RegistrationStates.waiting_phone, F.text.len() > 0)
async def registration_receive_phone(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text or "")
    
    if not validate_phone(phone):
        await message.answer(
            "Формат неверный. Пример: +79991234567",
            reply_markup=cancel_keyboard()
        )
        return
    
    # Сохраняем телефон
    await execute("UPDATE users SET phone=$2, updated_at=NOW() WHERE tg_user_id=$1", message.from_user.id, phone)
    
    # Завершаем регистрацию
    await state.clear()
    
    # Получаем обновленные данные пользователя
    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)

    # Показываем главное меню
    kb = await build_menu_keyboard(user=user, is_admin=is_admin, section="root")
    
    completion_template = await get_content(
        "menu.registration_complete",
        "Регистрация завершена, {name}!\n\nТеперь тебе доступно:\n- Бесплатные уроки\n- Доступ в клуб\n- Отслеживание прогресса\n\nВыбирай в меню и начинай.",
    )
    display_name = (
        user.get("name")
        or user.get("full_name")
        or message.from_user.full_name
        or message.from_user.first_name
        or "друг"
    )
    completion_text = render_content(
        completion_template,
        name=display_name,
        NAME=display_name,
    )

    await message.answer(completion_text, reply_markup=kb)

async def _reset_state_if_needed(state: FSMContext) -> bool:
    """Сбрасывает активный FSM-стейт, если он есть."""
    if state is None:
        return False

    current_state = await state.get_state()
    if current_state:
        await state.clear()
        return True
    return False











@router.message(HWStates.waiting_answer, F.text.len() > 0)
async def hw_receive_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lesson_num = int(data.get("lesson_num", 0) or 0)
    if lesson_num not in (1, 2, 3, 4):
        await state.clear()
        await message.answer("Что-то пошло не так. Попробуй снова через меню «Бесплатные уроки».")
        return
    user = await get_user_with_id(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer("Перезапусти /start.")
        return
    await mark_lesson_done(user["id"], lesson_num, hw_answer=message.text.strip())
    await state.clear()
    
    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции"
    }
    
    await state.set_state(HWStates.waiting_feedback)
    await state.update_data(lesson_num=lesson_num, last_lesson=lesson_num)
    
    await message.answer(
        f"Отлично!\n\n"
        f"Твой ответ на урок «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» принят.\n\n"
        f"Теперь расскажи, как тебе урок? Насколько полезной была информация?",
        reply_markup=feedback_keyboard()
    )




@router.message(HWStates.waiting_feedback, F.text.len() > 0)
async def feedback_receive_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lesson_num = int(data.get("lesson_num", 0) or 0)
    if lesson_num not in (1, 2, 3, 4):
        await state.clear()
        await message.answer("Что-то пошло не так. Попробуй снова через меню «Бесплатные уроки».")
        return
    
    user = await get_user_with_id(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer("Перезапусти /start.")
        return
    
    await save_lesson_feedback(user["id"], lesson_num, "custom", message.text.strip())
    await state.update_data(last_lesson=lesson_num)
    await state.set_state(None)
    
    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции"
    }
    
    await message.answer(
        f"Спасибо за отзыв!\n\n"
        f"Твой отзыв по уроку «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» сохранен.",
        reply_markup=after_lesson_keyboard()
    )


@router.message(
    ProfileStates.waiting_email, F.text.casefold() == CANCEL_TEXT.lower()
)
async def profile_cancel_email(message: types.Message, state: FSMContext):
    await state.clear()

    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)

    await message.answer("Изменение email отменено.")
    await send_profile_overview(message, user, is_admin)


@router.message(ProfileStates.waiting_email, F.text.len() > 0)
async def profile_receive_email(message: types.Message, state: FSMContext):
    email = (message.text or "").strip()

    if not validate_email(email):
        await message.answer(
            "Формат email неверный. Пример: name@mail.com",
            reply_markup=cancel_keyboard(),
        )
        return

    await execute(
        "UPDATE users SET email=$2, updated_at=NOW() WHERE tg_user_id=$1",
        message.from_user.id,
        email,
    )
    await state.clear()

    await message.answer("Email обновлён ✅")
    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    await send_profile_overview(message, user, is_admin)


@router.message(ProfileStates.waiting_phone, F.text.casefold() == CANCEL_TEXT.lower())
async def profile_cancel_phone(message: types.Message, state: FSMContext):
    await state.clear()

    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)

    await message.answer("Изменение телефона отменено.")
    await send_profile_overview(message, user, is_admin)


@router.message(ProfileStates.waiting_phone, F.text.len() > 0)
async def profile_receive_phone(message: types.Message, state: FSMContext):
    raw_phone = (message.text or "").strip()

    if not validate_phone(raw_phone):
        await message.answer(
            "Номер не распознан. Укажи телефон в формате +79991234567.",
            reply_markup=cancel_keyboard(),
        )
        return

    normalized = normalize_phone(raw_phone)
    await execute(
        "UPDATE users SET phone=$2, updated_at=NOW() WHERE tg_user_id=$1",
        message.from_user.id,
        normalized,
    )
    await state.clear()

    await message.answer("Телефон обновлён ✅")
    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    await send_profile_overview(message, user, is_admin)


# ──────────────────────────────────────────────────────────────────────────────
# Новые кнопки меню: правила, запись на разбор, тест
# ──────────────────────────────────────────────────────────────────────────────








# ──────────────────────────────────────────────────────────────────────────────
# Поддержка и помощь
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("support"))
async def cmd_support(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    is_admin = is_admin_id(message.from_user.id)
    user = await get_user_with_id(message.from_user.id)
    await message.answer(
        f"Поддержка.\n\n"
        f"Если есть вопросы или сложности — пиши сюда: {SUPPORT_CONTACT}. Мы отвечаем лично и максимально быстро.",
        reply_markup=await build_menu_keyboard(user=user, is_admin=is_admin, section="root"),
    )

@router.message(Command("form_done"))
async def cmd_form_done(message: types.Message, command: CommandObject, state: FSMContext):
    await _reset_state_if_needed(state)

    is_admin = is_admin_id(message.from_user.id)
    raw_arg = (command.args or "").strip() if command else ""
    slug = resolve_form_slug(raw_arg) if raw_arg else FORM_SLUG_ANALYSIS

    user_row = await get_user_with_id(message.from_user.id)
    if not user_row:
        user_row = await ensure_user(message.from_user)

    keyboard = await build_menu_keyboard(user=user_row, is_admin=is_admin, section="root")

    if raw_arg and not slug:
        await message.answer(
            "Не удалось определить, какую анкету завершить. Используй варианты: разбор или тест.",
            reply_markup=keyboard,
        )
        return

    if not slug:
        await message.answer("Не удалось определить тип анкеты. Попробуй ещё раз позже.", reply_markup=keyboard)
        return

    try:
        _, newly_completed = await mark_form_completed(user_row["id"], slug)
    except Exception:
        logger.exception("form_session: mark completion failed user_id=%s slug=%s", user_row["id"], slug)
        await message.answer("Не получилось обновить статус анкеты. Попробуй позже или напиши в поддержку.", reply_markup=keyboard)
        return

    label = FORM_LABELS.get(slug, slug)
    response_lines: list[str] = []

    if newly_completed:
        response_lines.append(f"Спасибо! Анкета «{label}» отмечена как завершённая.")

        invite_text = ""
        gen_invite_link = None
        notify_admins = None
        invite_attempted = False
        invite_generated = False
        try:
            from app import gen_invite_link as _gen_invite_link

            gen_invite_link = _gen_invite_link
        except Exception:
            gen_invite_link = None

        try:
            from app import notify_admins as _notify_admins

            notify_admins = _notify_admins
        except Exception:
            notify_admins = None

        if gen_invite_link:
            try:
                invite_attempted = True
                invite_payload = await gen_invite_link()
                if invite_payload:
                    if invite_payload.startswith("http"):
                        invite_text = f"Твоя персональная ссылка: {invite_payload}"
                    else:
                        invite_text = invite_payload
                    invite_generated = True
            except Exception as exc:
                logger.warning("form_session: gen_invite_link failed user_id=%s slug=%s: %s", user_row["id"], slug, exc)

        if invite_text:
            response_lines.append(invite_text)
        else:
            response_lines.append("Мы передали заявку администраторам и свяжемся с тобой в ближайшее время.")
        if notify_admins:
            username = message.from_user.username
            display = f"@{username}" if username else message.from_user.full_name or message.from_user.id
            if invite_generated:
                invite_status = "Ссылка выдана автоматически"
            elif invite_attempted:
                invite_status = "Не удалось выдать ссылку автоматически"
            else:
                invite_status = "Автовыдача ссылок недоступна"
            try:
                await notify_admins(
                    "\n".join(
                        [
                            f"✅ Завершена анкета «{label}»",
                            f"Пользователь: {display} (tg_id={message.from_user.id})",
                            f"Инвайт: {invite_status}",
                        ]
                    )
                )
            except Exception as exc:
                logger.warning("form_session: notify_admins failed user_id=%s slug=%s: %s", user_row["id"], slug, exc)
    else:
        response_lines.append(f"Анкета «{label}» уже отмечена как завершённая.")

    await message.answer("\n\n".join(response_lines), reply_markup=keyboard)


@router.message(Command("id"))
async def cmd_id(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else "—"
    is_admin = is_admin_id(message.from_user.id)
    user = await get_user_with_id(message.from_user.id)
    await message.answer(
        f"Твои данные:\n\n"
        f"Telegram ID: <code>{uid}</code>\n"
        f"Username: {uname}\n\n"
        f"Эти данные могут понадобиться при обращении в поддержку.",
        reply_markup=await build_menu_keyboard(user=user, is_admin=is_admin, section="root"),
    )


@router.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    await send_profile_overview(message, user, is_admin)


@router.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    is_admin = is_admin_id(message.from_user.id)
    user = await get_user_with_id(message.from_user.id)
    await message.answer(
        "Справка по боту.\n\n"
        "Команды:\n"
        "/start — главное меню\n"
        "/support — поддержка\n"
        "/id — твои данные\n\n"
        "В меню доступны:\n"
        "О клубе\n"
        "Бесплатные уроки\n"
        "Мой прогресс\n"
        "FAQ\n"
        "Оплата доступа\n"
        "Правила клуба\n"
        "Тест и разбор",
        reply_markup=await build_menu_keyboard(user=user, is_admin=is_admin, section="root"),
    )


@router.message(Command("form_done"))
async def cmd_form_done(
    message: types.Message, command: CommandObject, state: FSMContext
):
    await _reset_state_if_needed(state)

    user = await get_user_with_id(message.from_user.id)
    if not user:
        await message.answer(
            "Перезапусти /start, чтобы зарегистрироваться и продолжить работу с формами."
        )
        return

    raw_slug = command.args if command else None
    slug = resolve_form_slug(raw_slug)
    if not slug and message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            slug = resolve_form_slug(parts[1])

    if not slug:
        await message.answer(
            "Укажи идентификатор формы, например: /form_done magnetism-window."
        )
        return

    await mark_form_completed(user.get("id"), slug)

    confirmation_template = await get_content(f"forms.completed.{slug}", "")
    if not confirmation_template:
        confirmation_template = await get_content(
            "forms.completed",
            "Спасибо! Мы отметили форму «{form_slug}» заполненной.",
        )

    confirmation_text = render_content(
        confirmation_template,
        slug=slug,
        form_slug=slug,
        FORM_SLUG=slug,
    )

    is_admin = is_admin_id(message.from_user.id)
    await answer_with_main_menu(
        message,
        user,
        is_admin,
        confirmation_text,
        section="learning",
    )
# ──────────────────────────────────────────────────────────────────────────────
# Поддержка и помощь
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("id"))
async def cmd_id(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else "—"
    is_admin = is_admin_id(message.from_user.id)
    user = await get_user_with_id(message.from_user.id)
    await message.answer(
        f"Твои данные:\n\n"
        f"Telegram ID: <code>{uid}</code>\n"
        f"Username: {uname}\n\n"
        f"Эти данные могут понадобиться при обращении в поддержку.",
        reply_markup=await build_menu_keyboard(user=user, is_admin=is_admin, section="root"),
    )


@router.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    await send_profile_overview(message, user, is_admin)


@router.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    is_admin = is_admin_id(message.from_user.id)
    user = await get_user_with_id(message.from_user.id)
    await message.answer(
        "Справка по боту.\n\n"
        "Команды:\n"
        "/start — главное меню\n"
        "/support — поддержка\n"
        "/id — твои данные\n\n"
        "В меню доступны:\n"
        "О клубе\n"
        "Бесплатные уроки\n"
        "Мой прогресс\n"
        "FAQ\n"
        "Оплата доступа\n"
        "Правила клуба\n"
        "Тест и разбор",
        reply_markup=await build_menu_keyboard(user=user, is_admin=is_admin, section="root"),
    )
# ──────────────────────────────────────────────────────────────────────────────
# Навигация по меню
# ──────────────────────────────────────────────────────────────────────────────
async def _get_user_and_admin(message: types.Message) -> tuple[Optional[dict], bool]:
    user = await get_user_with_id(message.from_user.id)
    return user, is_admin_id(message.from_user.id)


@router.message(F.text == BACK_TO_MAIN)
async def menu_back_to_main(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_menu_section(message, user, is_admin, "root")


@router.message(F.text == "ℹ️ О клубе")
async def menu_open_info(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_menu_section(message, user, is_admin, "info")


@router.message(F.text == "🎓 Обучение")
async def menu_open_learning(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_menu_section(message, user, is_admin, "learning")


@router.message(F.text == "📦 Материалы")
async def menu_open_materials(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_menu_section(message, user, is_admin, "materials")


@router.message(F.text == "👤 Профиль")
async def menu_open_profile(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_menu_section(message, user, is_admin, "profile")


@router.message(F.text == "О клубе")
async def info_about(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_about_section(message, user, is_admin)


@router.message(F.text == "FAQ")
async def info_faq(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_faq_section(message, user, is_admin)


@router.message(F.text == "Правила")
async def info_rules(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_rules_section(message, user, is_admin)


@router.message(F.text.in_({"💳 Оплата", "🔒 Оплата"}))
async def menu_pay(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    if not user:
        user = await ensure_user(message.from_user)
    await send_pay_section(message, user, is_admin)


@router.message(F.text == "🆘 Поддержка")
async def menu_support(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_support_section(message, user, is_admin)


@router.message(F.text == "Бесплатные уроки")
async def menu_lessons(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user = await get_user_with_id(message.from_user.id)
    if not user:
        user = await ensure_user(message.from_user)
    is_admin = is_admin_id(message.from_user.id)
    await send_funnel_section(message, user, is_admin)


@router.message(F.text == "Окно в Магнетизм")
async def menu_magnetism_window(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    if not user:
        await message.answer("Перезапусти /start, чтобы загрузить профиль.")
        return
    await send_magnetism_window_section(message, user, is_admin)


@router.message(F.text == "Записаться на разбор")
async def menu_analysis(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_analysis_section(message, user, is_admin)


@router.message(F.text == "Пройти тест")
async def menu_test(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    if not user:
        user = await ensure_user(message.from_user)

    result = await send_test_section(message, user, is_admin, only_text=True)
    if result:
        intro_text, slug = result
    else:
        intro_text, slug = "", FORM_SLUG_TEST

    await state.set_state(TestStates.waiting_birthdate)
    await state.update_data(
        test_form_slug=slug,
        test_user_id=(user or {}).get("id"),
    )

    intro_template = await get_content("menu.test_intro", intro_text)
    intro_message = render_content(
        intro_template,
        test_url=TEST_FORM_URL,
        TEST_FORM_URL=TEST_FORM_URL,
    )

    birth_prompt_template = await get_content(
        "menu.test_birthdate_prompt",
        (
            "Чтобы записать тебя на тест, напиши дату рождения.\n"
            "Подойдут варианты: 24.08.1992 или 24 августа 1992.\n\n"
            "Для отмены нажми «Отмена»."
        ),
    )
    birth_prompt = render_content(
        birth_prompt_template,
        test_url=TEST_FORM_URL,
        TEST_FORM_URL=TEST_FORM_URL,
    )

    parts = [intro_message.strip(), birth_prompt.strip()]
    message_text = "\n\n".join([part for part in parts if part])
    await message.answer(message_text, reply_markup=cancel_keyboard())


@router.message(TestStates.waiting_birthdate, F.text.casefold() == CANCEL_TEXT.lower())
async def test_cancel_birthdate(message: types.Message, state: FSMContext):
    await cancel_handler(message, state)


@router.message(TestStates.waiting_birthdate)
async def test_collect_birthdate(message: types.Message, state: FSMContext):
    if (message.text or "").casefold() == CANCEL_TEXT.lower():
        await cancel_handler(message, state)
        return

    birthdate = parse_birthdate(message.text)
    if not birthdate:
        invalid_template = await get_content(
            "menu.test_birthdate_invalid",
            (
                "Не получилось распознать дату. Попробуй формат 24.08.1992 или 24 августа 1992.\n\n"
                "Если передумала — нажми «Отмена»."
            ),
        )
        response = render_content(
            invalid_template,
            raw=message.text or "",
            RAW=message.text or "",
        )
        await message.answer(response, reply_markup=cancel_keyboard())
        return

    await state.update_data(test_birthdate=birthdate.isoformat())
    await state.set_state(TestStates.waiting_name)

    name_prompt_template = await get_content(
        "menu.test_name_prompt",
        (
            "Отлично! Как тебя записать в заявке?\n\n"
            "Можно указать короткое имя или ник."
        ),
    )
    formatted_birthdate = _format_birthdate(birthdate)
    name_prompt = render_content(
        name_prompt_template,
        birthdate=formatted_birthdate,
        BIRTHDATE=formatted_birthdate,
    )
    await message.answer(name_prompt, reply_markup=cancel_keyboard())

    notify_admins = _get_notify_admins()
    if notify_admins:
        stage_label = "ожидание имени"
        card_lines = [
            "🧪 Заявка на тест: обновление",
            f"tg-id: <code>{message.from_user.id}</code>",
            f"Дата рождения: {_format_birthdate(birthdate)}",
            f"Этап: {stage_label}",
        ]
        try:
            await notify_admins("\n".join(card_lines))
        except Exception as exc:
            logger.warning(
                "test_request: notify_admins birthdate failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )


@router.message(TestStates.waiting_name, F.text.len() > 0)
async def test_collect_name(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() == CANCEL_TEXT.lower():
        await cancel_handler(message, state)
        return

    name = text
    if len(name) < 2:
        invalid_name_template = await get_content(
            "menu.test_name_invalid",
            "Имя должно содержать хотя бы два символа. Попробуй снова.",
        )
        await message.answer(invalid_name_template, reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    birthdate_raw = data.get("test_birthdate")
    form_slug = data.get("test_form_slug") or FORM_SLUG_TEST
    stored_user_id = data.get("test_user_id")
    if not birthdate_raw:
        await state.set_state(TestStates.waiting_birthdate)
        await message.answer("Начнём с даты рождения. Напиши её ещё раз, пожалуйста.", reply_markup=cancel_keyboard())
        return

    birthdate = date.fromisoformat(birthdate_raw)

    user, is_admin = await _get_user_and_admin(message)
    if not user:
        user = await ensure_user(message.from_user)
    user_id = stored_user_id or (user or {}).get("id")

    if user_id and form_slug:
        try:
            await mark_form_started(user_id, form_slug)
        except Exception as exc:
            logger.warning(
                "test_request: mark start retry failed user_id=%s slug=%s err=%s",
                user_id,
                form_slug,
                exc,
            )

    preferred_name = name
    await upsert_test_request(
        tg_user_id=message.from_user.id,
        user_id=user_id,
        birthdate=birthdate,
        preferred_name=preferred_name,
    )

    await state.clear()

    thanks_template = await get_content(
        "menu.test_thanks",
        (
            "Спасибо, {name}! Мы записали тебя на тестирование.\n"
            "Когда будет готов анализ, администратор напишет в Telegram."
        ),
    )
    safe_name = html.escape(preferred_name)
    if not safe_name:
        safe_name = html.escape(
            (user or {}).get("name")
            or (user or {}).get("full_name")
            or message.from_user.first_name
            or "друг"
        )
    formatted_birthdate = _format_birthdate(birthdate)
    thanks_text = render_content(
        thanks_template,
        name=safe_name,
        NAME=safe_name,
        birthdate=formatted_birthdate,
        BIRTHDATE=formatted_birthdate,
    )

    keyboard = await build_menu_keyboard(user=user, is_admin=is_admin, section="learning")
    await message.answer(thanks_text, reply_markup=keyboard)

    notify_admins = _get_notify_admins()
    if notify_admins:
        card_lines = [
            "🧪 Новая запись на тестирование",
            f"tg-id: <code>{message.from_user.id}</code>",
            f"Дата рождения: {_format_birthdate(birthdate)}",
            f"Имя: {safe_name if safe_name else '—'}",
        ]
        try:
            await notify_admins("\n".join(card_lines))
        except Exception as exc:
            logger.warning(
                "test_request: notify_admins failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )


@router.message(F.text == "⚙️ Админка")
async def menu_admin_entry(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_menu(message)


@router.message(F.text.in_({"Материалы недели", "Материалы недели 🔒"}))
async def menu_weekly_materials(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_weekly_materials_section(message, user, is_admin)


@router.message(F.text.in_({"Расписание", "Расписание 🔒"}))
async def menu_schedule(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_schedule_section(message, user, is_admin)


@router.message(F.text == "Мой профиль")
async def menu_profile_overview(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    if not user:
        await message.answer("Перезапусти /start, чтобы загрузить профиль.")
        return
    await send_profile_overview(message, user, is_admin)


@router.message(F.text == "Изменить email")
async def menu_profile_email(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    await state.set_state(ProfileStates.waiting_email)
    await message.answer(
        "Введи новый email. Если передумала — нажми «Отмена».",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == "Изменить телефон")
async def menu_profile_phone(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    await state.set_state(ProfileStates.waiting_phone)
    await message.answer(
        "Введи номер в формате +79991234567. Для отмены — кнопка ниже.",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == BACK_TO_LEARNING)
async def menu_back_to_learning(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_menu_section(message, user, is_admin, "learning")


@router.message(F.text == BACK_TO_LESSONS)
async def menu_back_to_lessons(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user = await get_user_with_id(message.from_user.id)
    if not user:
        user = await ensure_user(message.from_user)
    is_admin = is_admin_id(message.from_user.id)
    await send_funnel_section(message, user, is_admin)


@router.message(F.text.regexp(r"^[✅⏳🔒] Урок (\d)"))
async def lessons_select(message: types.Message, state: FSMContext):
    match = re.match(r"^[✅⏳🔒] Урок (\d)", message.text or "")
    if not match:
        return
    lesson_num = int(match.group(1))
    user = await get_user_with_id(message.from_user.id)
    if not user:
        user = await ensure_user(message.from_user)
    n = await next_lesson_to_deliver(user["id"])
    if lesson_num > n:
        await message.answer("Этот урок пока закрыт. Заверши предыдущий, чтобы открыть его.")
        return
    await deliver_lesson(message, user, lesson_num, state)


@router.message(F.text == LESSON_DONE)
async def lesson_mark_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lesson_num = int(data.get("active_lesson", 0) or 0)
    if lesson_num not in (1, 2, 3, 4):
        await message.answer("Сначала выбери урок в разделе «Бесплатные уроки»." )
        return
    await state.set_state(HWStates.waiting_answer)
    await state.update_data(lesson_num=lesson_num)
    await message.answer(
        "Напиши короткий ответ на задание. Например: «Сегодня я заметила, что…»",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == LESSON_SKIP)
async def lesson_skip(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lesson_num = int(data.get("active_lesson", 0) or 0)
    if lesson_num not in (1, 2, 3, 4):
        await message.answer("Сначала открой урок из меню «Бесплатные уроки»." )
        return
    user = await get_user_with_id(message.from_user.id)
    if not user:
        await message.answer("Перезапусти /start, чтобы загрузить профиль.")
        return
    await mark_lesson_skipped(user["id"], lesson_num)
    await state.update_data(active_lesson=None, last_lesson=lesson_num)
    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции",
    }
    reply = await build_menu_keyboard(
        user=user,
        is_admin=is_admin_id(message.from_user.id),
        section="learning",
    )
    await message.answer(
        f"Урок «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» пропущен. К нему можно вернуться в «Мой прогресс».",
        reply_markup=reply,
    )


@router.message(F.text == LESSON_QUESTION)
async def lesson_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lesson_num = int(data.get("active_lesson", 0) or 0)
    if lesson_num not in (1, 2, 3, 4):
        await message.answer("Сначала открой урок из раздела «Бесплатные уроки»." )
        return
    await message.answer(
        f"Задай вопрос по уроку {lesson_num}\n\n"
        f"Напиши одним сообщением или обратись в поддержку: {SUPPORT_CONTACT}",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == NEXT_LESSON)
async def lesson_next(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_lesson = int(data.get("last_lesson", 0) or 0)
    if last_lesson not in (1, 2, 3, 4):
        await message.answer("Сначала пройди урок, чтобы открыть следующий.")
        return
    next_lesson_num = last_lesson + 1
    if next_lesson_num > 4:
        await message.answer("Это был последний урок. Посмотри прогресс или материалы клуба.")
        return
    user = await get_user_with_id(message.from_user.id)
    if not user:
        user = await ensure_user(message.from_user)
    await deliver_lesson(message, user, next_lesson_num, state)


@router.message(HWStates.waiting_feedback, F.text == WRITE_FEEDBACK)
async def feedback_request_text(message: types.Message, state: FSMContext):
    await message.answer(
        "Поделись впечатлением от урока одним сообщением.",
        reply_markup=cancel_keyboard(),
    )


@router.message(HWStates.waiting_feedback, F.text == SKIP_FEEDBACK)
async def feedback_skip(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lesson_num = int(data.get("lesson_num", 0) or 0)
    await state.update_data(last_lesson=lesson_num)
    await state.set_state(None)
    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции",
    }
    await message.answer(
        f"Спасибо! Твой прогресс по уроку «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» сохранен.",
        reply_markup=after_lesson_keyboard(),
    )
    await state.update_data(last_lesson=lesson_num)


@router.message(HWStates.waiting_feedback, F.text.in_(list(FEEDBACK_OPTIONS.keys())))
async def feedback_quick_choice(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lesson_num = int(data.get("lesson_num", 0) or 0)
    if lesson_num not in (1, 2, 3, 4):
        await state.clear()
        await message.answer("Сначала выбери урок в разделе «Бесплатные уроки»." )
        return
    user = await get_user_with_id(message.from_user.id)
    if not user:
        await state.clear()
        await message.answer("Перезапусти /start, чтобы загрузить профиль.")
        return
    feedback_code = FEEDBACK_OPTIONS[message.text]
    await save_lesson_feedback(user["id"], lesson_num, feedback_code)
    await state.set_state(None)
    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции",
    }
    await message.answer(
        f"Спасибо за отзыв! Твоя оценка «{message.text}» по уроку «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» сохранена.",
        reply_markup=after_lesson_keyboard(),
    )
    await state.update_data(last_lesson=lesson_num)
# ──────────────────────────────────────────────────────────────────────────────
# Обработка отмены для всех состояний
# ──────────────────────────────────────────────────────────────────────────────
@router.message(F.text.func(lambda text: (text or "").strip().lower() == CANCEL_TEXT.lower()))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if not current_state:
        return
    data = await state.get_data()
    await state.clear()
    user, is_admin = await _get_user_and_admin(message)

    if current_state in {
        TestStates.waiting_birthdate.state,
        TestStates.waiting_name.state,
    }:
        notify_admins = _get_notify_admins()
        birthdate_raw = (data or {}).get("test_birthdate") if data else None
        stored_user_id = (data or {}).get("test_user_id") if data else None
        resolved_user_id = stored_user_id or ((user or {}).get("id") if user else None)
        if notify_admins and (birthdate_raw or resolved_user_id):
            stage_label = (
                "ожидание даты рождения"
                if current_state == TestStates.waiting_birthdate.state
                else "ожидание имени"
            )
            formatted_birthdate = None
            if birthdate_raw:
                try:
                    formatted_birthdate = _format_birthdate(
                        date.fromisoformat(birthdate_raw)
                    )
                except Exception:
                    formatted_birthdate = birthdate_raw
            card_lines = [
                "🧪 Заявка на тест отменена",
                f"tg-id: <code>{message.from_user.id}</code>",
            ]
            if resolved_user_id:
                card_lines.append(f"user-id: <code>{resolved_user_id}</code>")
            if formatted_birthdate:
                card_lines.append(f"Дата рождения: {formatted_birthdate}")
            card_lines.append(f"Этап: {stage_label}")
            try:
                await notify_admins("\n".join(card_lines))
            except Exception as exc:
                logger.warning(
                    "test_request: notify_admins cancel failed tg_user_id=%s err=%s",
                    message.from_user.id,
                    exc,
                )

    if current_state == AdminContentStates.waiting_value.state and is_admin:
        group_title = (data or {}).get("content_group")
        if group_title and group_title in _ADMIN_TEXT_GROUPS:
            await message.answer(
                "Редактирование отменено. Выбери текст для изменения или вернись назад.",
                reply_markup=admin_text_items_keyboard(_admin_text_labels(group_title)),
            )
            return

        await message.answer(
            "Редактирование отменено. Можно выбрать другой текст или вернуться в админку.",
            reply_markup=admin_text_groups_keyboard(list(_ADMIN_TEXT_GROUPS.keys())),
        )
        return

    if (
        current_state
        in {
            AdminContentStates.waiting_custom_key.state,
            AdminContentStates.waiting_custom_value.state,
            AdminContentStates.waiting_view_key.state,
            AdminContentStates.waiting_history_key.state,
            AdminContentStates.waiting_history_choice.state,
            AdminContentStates.waiting_import_file.state,
        }
        and is_admin
    ):
        await message.answer(
            "Действие отменено. Возвращаю в раздел «Контент и тексты».",
            reply_markup=admin_content_keyboard(),
        )
        return

    if (
        current_state
        in {
            AdminBehaviorStates.waiting_start_text.state,
            AdminBehaviorStates.waiting_registration_text.state,
        }
        and is_admin
    ):
        await message.answer(
            "Изменения не сохранены.",
            reply_markup=admin_behavior_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if (
        current_state
        in {
            AdminBehaviorStates.waiting_onboarding_text.state,
            AdminBehaviorStates.waiting_onboarding_delete.state,
        }
        and is_admin
    ):
        await send_admin_onboarding_menu(message)
        return

    if (
        current_state
        in {
            BroadcastStates.waiting_body.state,
            BroadcastStates.waiting_confirm.state,
            BroadcastStates.waiting_template_title.state,
            BroadcastStates.waiting_template_delete.state,
            BroadcastStates.waiting_segment.state,
        }
        and is_admin
    ):
        await send_admin_broadcast_menu(message)
        return

    if (
        current_state
        in {
            AdminPaymentsStates.waiting_access_user.state,
            AdminPaymentsStates.waiting_revoke_user.state,
            AdminPaymentsStates.waiting_payment_review.state,
        }
        and is_admin
    ):
        await send_admin_payments_overview(message)
        return

    kb = await build_menu_keyboard(user=user, is_admin=is_admin, section="root")
    await message.answer("Действие отменено. Возвращаюсь в главное меню...", reply_markup=kb)

# ──────────────────────────────────────────────────────────────────────────────
# Админ-панель
# ──────────────────────────────────────────────────────────────────────────────


def _admin_toggle_key_from_text(text: str | None) -> str | None:
    if not text:
        return None
    normalized = text.strip()
    if normalized.startswith("✅") or normalized.startswith("❌"):
        normalized = normalized[1:].strip()
    for key, label in _ADMIN_SETTINGS_LABELS.items():
        if normalized == label:
            return key
    return None


def _parse_onboarding_index(text: str | None, prefix: str) -> Optional[int]:
    if not text or not prefix:
        return None
    if not text.startswith(prefix):
        return None
    tail = text[len(prefix):].strip()
    if not tail.isdigit():
        return None
    idx = int(tail) - 1
    return idx if idx >= 0 else None


@router.message(F.text == BACK_TO_BEHAVIOR)
async def admin_back_to_behavior(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_behavior_menu(message)


@router.message(F.text == ADMIN_BEHAVIOR_BUTTON)
async def admin_behavior_entry(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_behavior_menu(message)


@router.message(F.text == ADMIN_BEHAVIOR_START)
async def admin_behavior_start_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    current = await get_content(
        "menu.start",
        "Добро пожаловать в CODE: Магнетизм, {name}!",
    )
    preview = _preview_text_for_admin(current)
    placeholders_line = _admin_placeholder_hint_line("menu.start")
    if placeholders_line:
        placeholders_line = "\n" + placeholders_line

    await state.set_state(AdminBehaviorStates.waiting_start_text)
    await message.answer(
        "<b>Приветствие /start</b>\n\n"
        "Текущий текст:\n"
        f"{preview}\n\n"
        "Пришли новый вариант одним сообщением — бот сохранит его и начнёт показывать новичкам." + placeholders_line +
        "\n\nДля отмены нажми «Отмена».",
        reply_markup=cancel_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(AdminBehaviorStates.waiting_start_text, F.text.len() > 0)
async def admin_behavior_start_receive(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    new_text = prepare_admin_text_input(message.text)
    await set_content_value("menu.start", new_text, updated_by=message.from_user.id)
    await log_admin_action(
        message.from_user.id,
        "behavior_start_update",
        {"length": len(new_text)},
    )

    sample_name = (
        message.from_user.full_name
        or message.from_user.first_name
        or "друг"
    )
    preview = render_content(
        new_text,
        name=sample_name,
        NAME=sample_name,
        support=SUPPORT_CONTACT,
        SUPPORT_CONTACT=SUPPORT_CONTACT,
        support_contact=SUPPORT_CONTACT,
    )

    await message.answer(
        "<b>Так увидит пользователь:</b>",
        disable_web_page_preview=True,
    )
    await message.answer(
        preview,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await state.clear()
    await message.answer(
        "Приветствие обновлено ✅",
        reply_markup=admin_behavior_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text == ADMIN_BEHAVIOR_REGISTRATION)
async def admin_behavior_registration_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    current = await get_content(
        "menu.registration_complete",
        "Регистрация завершена, {name}!",
    )
    preview = _preview_text_for_admin(current)
    placeholders_line = _admin_placeholder_hint_line("menu.registration_complete")
    if placeholders_line:
        placeholders_line = "\n" + placeholders_line

    await state.set_state(AdminBehaviorStates.waiting_registration_text)
    await message.answer(
        "<b>Сообщение после регистрации</b>\n\n"
        "Текущий текст:\n"
        f"{preview}\n\n"
        "Пришли новый вариант одним сообщением." + placeholders_line +
        "\n\nДля отмены нажми «Отмена».",
        reply_markup=cancel_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(AdminBehaviorStates.waiting_registration_text, F.text.len() > 0)
async def admin_behavior_registration_receive(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    new_text = prepare_admin_text_input(message.text)
    await set_content_value(
        "menu.registration_complete",
        new_text,
        updated_by=message.from_user.id,
    )
    await log_admin_action(
        message.from_user.id,
        "behavior_registration_update",
        {"length": len(new_text)},
    )

    sample_name = (
        message.from_user.full_name
        or message.from_user.first_name
        or "друг"
    )
    preview = render_content(
        new_text,
        name=sample_name,
        NAME=sample_name,
        support=SUPPORT_CONTACT,
        SUPPORT_CONTACT=SUPPORT_CONTACT,
        support_contact=SUPPORT_CONTACT,
    )

    await message.answer(
        "<b>Сообщение обновлено. Предпросмотр:</b>",
        disable_web_page_preview=True,
    )
    await message.answer(
        preview,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await state.clear()
    await message.answer(
        "Готово!", reply_markup=admin_behavior_keyboard(), disable_web_page_preview=True
    )


@router.message(F.text == ADMIN_BEHAVIOR_ONBOARDING)
async def admin_behavior_onboarding_menu(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_onboarding_menu(message)


@router.message(F.text == BACK_TO_ONBOARDING)
async def admin_behavior_back_to_onboarding(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_onboarding_menu(message)


@router.message(F.text == ADD_ONBOARDING_STEP)
async def admin_onboarding_add_step(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    steps = await get_onboarding_steps()
    await _reset_state_if_needed(state)
    await state.set_state(AdminBehaviorStates.waiting_onboarding_text)
    await state.update_data(onboarding_mode="add", onboarding_index=len(steps))
    await message.answer(
        "Пришли текст нового шага онбординга. Он появится в конце списка.",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text.func(lambda text: text and text.startswith(_ONBOARDING_EDIT_PREFIX)))
async def admin_onboarding_edit_step(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    idx = _parse_onboarding_index(message.text, _ONBOARDING_EDIT_PREFIX)
    if idx is None:
        return
    steps = await get_onboarding_steps()
    if idx >= len(steps):
        await message.answer("Не удалось найти этот шаг. Обнови список и попробуй снова.")
        return

    await _reset_state_if_needed(state)
    await state.set_state(AdminBehaviorStates.waiting_onboarding_text)
    await state.update_data(onboarding_mode="edit", onboarding_index=idx)
    current = _preview_text_for_admin(steps[idx])
    await message.answer(
        f"<b>Редактирование шага {idx + 1}</b>\n\nТекущий текст:\n{current}\n\nПришли новый вариант.",
        reply_markup=cancel_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(AdminBehaviorStates.waiting_onboarding_text, F.text.len() > 0)
async def admin_onboarding_receive_text(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    mode = (data or {}).get("onboarding_mode", "edit")
    idx = (data or {}).get("onboarding_index")
    steps = await get_onboarding_steps()

    new_text = prepare_admin_text_input(message.text)
    if mode == "add" or idx is None or idx >= len(steps):
        steps.append(new_text)
    else:
        steps[idx] = new_text

    await save_onboarding_steps(steps, updated_by=message.from_user.id)
    await log_admin_action(
        message.from_user.id,
        "behavior_onboarding_update",
        {"mode": mode, "index": idx, "count": len(steps)},
    )

    await state.clear()
    await message.answer("Шаги сохранены ✅", disable_web_page_preview=True)
    await send_admin_onboarding_menu(message)


@router.message(F.text == DELETE_ONBOARDING_STEP)
async def admin_onboarding_delete_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    steps = await get_onboarding_steps()
    if not steps:
        await message.answer("Удалять нечего — список пуст.")
        return
    await _reset_state_if_needed(state)
    await state.set_state(AdminBehaviorStates.waiting_onboarding_delete)
    await message.answer(
        "Выбери шаг, который нужно удалить.",
        reply_markup=admin_onboarding_delete_keyboard(steps),
    )


@router.message(AdminBehaviorStates.waiting_onboarding_delete, F.text.func(lambda text: text and text.startswith(_ONBOARDING_DELETE_PREFIX)))
async def admin_onboarding_delete_step(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return
    idx = _parse_onboarding_index(message.text, _ONBOARDING_DELETE_PREFIX)
    if idx is None:
        await message.answer("Не удалось определить шаг. Попробуй снова.")
        return
    steps = await get_onboarding_steps()
    if idx >= len(steps):
        await state.clear()
        await send_admin_onboarding_menu(message)
        return
    removed = steps.pop(idx)
    await save_onboarding_steps(steps, updated_by=message.from_user.id)
    await log_admin_action(
        message.from_user.id,
        "behavior_onboarding_delete",
        {"index": idx, "text_length": len(removed or "")},
    )
    await state.clear()
    await message.answer("Шаг удалён.")
    await send_admin_onboarding_menu(message)


@router.message(F.text == ADMIN_USERS_BUTTON)
async def admin_users_menu_entry(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await state.set_state(AdminUserStates.choosing_segment)
    await message.answer(
        "<b>👥 Пользователи</b>\n\n"
        "Выберите сегмент, чтобы посмотреть список участниц и управлять доступом.",
        reply_markup=admin_users_segments_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(AdminUserStates.choosing_segment, F.text.func(lambda text: _admin_user_segment_from_text(text) is not None))
async def admin_users_choose_segment(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    segment = _admin_user_segment_from_text(message.text)
    if not segment:
        return
    await _show_admin_users_list(message, state, segment=segment, page=1)


@router.message(AdminUserStates.browsing_users, F.text == ADMIN_USERS_PAGE_PREV)
async def admin_users_prev_page(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    data = await state.get_data()
    segment = data.get("segment")
    if not segment:
        await message.answer("Сначала выбери сегмент.")
        return
    current_page = max(1, int(data.get("page", 1)))
    await _show_admin_users_list(message, state, segment=segment, page=max(1, current_page - 1))


@router.message(AdminUserStates.browsing_users, F.text == ADMIN_USERS_PAGE_NEXT)
async def admin_users_next_page(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    data = await state.get_data()
    segment = data.get("segment")
    if not segment:
        await message.answer("Сначала выбери сегмент.")
        return
    current_page = max(1, int(data.get("page", 1)))
    total_pages = max(1, int(data.get("total_pages", current_page)))
    next_page = current_page + 1 if current_page < total_pages else total_pages
    await _show_admin_users_list(message, state, segment=segment, page=next_page)


@router.message(AdminUserStates.browsing_users, F.text.func(lambda text: bool(text)))
async def admin_users_open_card(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    data = await state.get_data()
    mapping = data.get("page_users") or {}
    user_id = _admin_user_id_from_button(message.text, mapping)
    if not user_id:
        raise EventSkip()
    await _show_admin_user_card(message, state, user_id=user_id)


@router.message(AdminUserStates.viewing_user, F.text == ADMIN_USERS_BACK_TO_LIST)
@router.message(AdminUserStates.waiting_contacts, F.text == ADMIN_USERS_BACK_TO_LIST)
async def admin_users_back_to_list(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    data = await state.get_data()
    segment = data.get("segment")
    page = data.get("page", 1)
    if not segment:
        await admin_users_menu_entry(message, state)
        return
    await _show_admin_users_list(message, state, segment=segment, page=int(page))


@router.message(AdminUserStates.browsing_users, F.text == ADMIN_USERS_BACK_TO_SEGMENTS)
@router.message(AdminUserStates.viewing_user, F.text == ADMIN_USERS_BACK_TO_SEGMENTS)
@router.message(AdminUserStates.waiting_contacts, F.text == ADMIN_USERS_BACK_TO_SEGMENTS)
async def admin_users_back_to_segments(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await state.set_state(AdminUserStates.choosing_segment)
    await message.answer(
        "Выбери сегмент, чтобы посмотреть список.",
        reply_markup=admin_users_segments_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(AdminUserStates.viewing_user, F.text == ADMIN_USERS_GRANT_ACCESS)
@router.message(AdminUserStates.waiting_contacts, F.text == ADMIN_USERS_GRANT_ACCESS)
async def admin_users_grant_access(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    data = await state.get_data()
    user_id = data.get("selected_user_id")
    if not user_id:
        await message.answer("Не удалось определить пользователя. Вернись к списку и выбери карточку заново.")
        return
    access_until = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await execute(
        """UPDATE users SET status='member_active', access_until=$2,
                  joined_club_at=COALESCE(joined_club_at, NOW()), updated_at=NOW()
           WHERE id=$1""",
        user_id,
        access_until,
    )
    await log_admin_action(
        message.from_user.id,
        "set_paid",
        {"user_id": user_id, "access_until": access_until.isoformat(), "source": "menu"},
    )
    await _show_admin_user_card(message, state, user_id=user_id, notice="Доступ выдан ✅")


@router.message(AdminUserStates.viewing_user, F.text == ADMIN_USERS_REVOKE_ACCESS)
@router.message(AdminUserStates.waiting_contacts, F.text == ADMIN_USERS_REVOKE_ACCESS)
async def admin_users_revoke_access(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    data = await state.get_data()
    user_id = data.get("selected_user_id")
    if not user_id:
        await message.answer("Не удалось определить пользователя. Вернись к списку и выбери карточку заново.")
        return
    await execute(
        "UPDATE users SET status='member_expired', access_until=NULL, updated_at=NOW() WHERE id=$1",
        user_id,
    )
    await log_admin_action(
        message.from_user.id,
        "revoke_access",
        {"user_id": user_id, "source": "menu"},
    )
    await _show_admin_user_card(message, state, user_id=user_id, notice="Доступ отозван")


@router.message(AdminUserStates.viewing_user, F.text == ADMIN_USERS_UPDATE_CONTACTS)
@router.message(AdminUserStates.waiting_contacts, F.text == ADMIN_USERS_UPDATE_CONTACTS)
async def admin_users_prompt_contacts(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    data = await state.get_data()
    if not data.get("selected_user_id"):
        await message.answer("Выбери пользователя в списке, чтобы обновить контакты.")
        return
    await state.set_state(AdminUserStates.waiting_contacts)
    await message.answer(
        "Пришли новые контакты в формате <code>email=user@example.com phone=+7999...</code>."
        " Можно указать только один из параметров.",
        reply_markup=admin_user_card_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(
    AdminUserStates.waiting_contacts,
    F.text.len() > 0,
)
async def admin_users_update_contacts(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    user_id = data.get("selected_user_id")
    if not user_id:
        await admin_users_menu_entry(message, state)
        return
    raw = (message.text or "").replace("\n", " ")
    pairs = [chunk.strip() for chunk in raw.split() if chunk.strip()]
    kv: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        kv[key.strip().lower()] = value.strip()

    email = kv.get("email")
    phone = kv.get("phone")
    updates: list[str] = []
    params: list[Any] = [user_id]
    idx = 2

    if email:
        if not validate_email(email):
            await message.answer("email невалиден. Попробуй снова или вернись к карточке.")
            return
        updates.append(f"email=${idx}")
        params.append(email)
        idx += 1

    normalized_phone: str | None = None

    if phone:
        normalized_phone = normalize_phone(phone)
        if not validate_phone(normalized_phone):
            await message.answer("phone невалиден. Попробуй снова или вернись к карточке.")
            return
        updates.append(f"phone=${idx}")
        params.append(normalized_phone)
        idx += 1

    if not updates:
        await message.answer("Не нашла данных для обновления. Укажи email=... и/или phone=...")
        return

    updates.append("updated_at=NOW()")
    sql = f"UPDATE users SET {', '.join(updates)} WHERE id=$1"
    await execute(sql, *params)

    await log_admin_action(
        message.from_user.id,
        "bind_contacts",
        {"user_id": user_id, "email": email, "phone": normalized_phone or phone, "source": "menu"},
    )

    await _show_admin_user_card(message, state, user_id=user_id, notice="Контакты обновлены")


@router.message(F.text == ADMIN_BROADCAST_BUTTON)
async def admin_broadcast_menu_entry(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_broadcast_menu(message)


@router.message(F.text == BACK_TO_BROADCAST)
async def admin_broadcast_back_to_menu(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_broadcast_menu(message)


@router.message(F.text == BROADCAST_TEMPLATES_BUTTON)
async def admin_broadcast_templates(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_broadcast_templates(message)


@router.message(F.text == DELETE_BROADCAST_TEMPLATE_BUTTON)
async def admin_broadcast_delete_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    templates = await list_broadcast_templates()
    if not templates:
        await message.answer(
            "Пока нет сохранённых шаблонов.",
            reply_markup=admin_broadcast_keyboard(),
        )
        return
    titles = [tpl["title"] for tpl in templates]
    await _reset_state_if_needed(state)
    await state.set_state(BroadcastStates.waiting_template_delete)
    await message.answer(
        "Выбери шаблон, который нужно удалить.",
        reply_markup=admin_broadcast_delete_keyboard(titles),
    )


@router.message(BroadcastStates.waiting_template_delete, F.text.func(lambda text: text and text.startswith(_TEMPLATE_DELETE_PREFIX)))
async def admin_broadcast_delete_template(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return
    title = message.text[len(_TEMPLATE_DELETE_PREFIX):].strip()
    if not title:
        await message.answer("Не удалось определить шаблон. Попробуй снова.")
        return
    success = await delete_broadcast_template(title)
    await log_admin_action(
        message.from_user.id,
        "broadcast_template_delete",
        {"title": title, "success": success},
    )
    await state.clear()
    if success:
        await message.answer("Шаблон удалён.")
    else:
        await message.answer("Шаблон не найден — возможно, его уже удалили.")
    await send_admin_broadcast_templates(message)


@router.message(F.text.func(lambda text: text and text in _BROADCAST_BUTTON_SEGMENTS))
async def admin_broadcast_choose_segment(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    segment = _BROADCAST_BUTTON_SEGMENTS[message.text]
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == BroadcastStates.waiting_segment.state and (data or {}).get("change_segment"):
        await state.update_data(segment=segment, change_segment=False)
        body = (data or {}).get("body")
        template_title = (data or {}).get("template_title")
        if body:
            await _broadcast_preview(
                message,
                state,
                segment=segment,
                body=body,
                template_title=template_title,
            )
            await state.set_state(BroadcastStates.waiting_confirm)
        else:
            await state.set_state(BroadcastStates.waiting_body)
            await message.answer(
                "Пришли текст рассылки для нового сегмента.",
                reply_markup=cancel_keyboard(),
            )
        return

    await _reset_state_if_needed(state)
    await state.set_state(BroadcastStates.waiting_body)
    await state.update_data(segment=segment, interactive=True, template_title=None)
    segment_label = _BROADCAST_SEGMENT_LABELS.get(segment, segment)
    await message.answer(
        f"Сегмент: {segment_label}.\n\nПришли текст рассылки одним сообщением. Можно использовать плейсхолдер <code>{{name}}</code> для имени участницы.",
        reply_markup=cancel_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text.func(lambda text: text and text.startswith(BROADCAST_TEMPLATE_PREFIX)))
async def admin_broadcast_use_template(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    title = message.text[len(BROADCAST_TEMPLATE_PREFIX):].strip()
    if not title:
        return
    template = await get_broadcast_template_by_title(title)
    if not template:
        await message.answer("Не удалось найти шаблон. Обнови список и попробуй снова.")
        return
    await _reset_state_if_needed(state)
    body = template.get("body") or ""
    segment = template.get("segment") or "all"
    await state.set_state(BroadcastStates.waiting_confirm)
    await _broadcast_preview(
        message,
        state,
        segment=segment,
        body=body,
        template_title=template.get("title"),
    )

@router.message(F.text == ADMIN_CONTENT_MENU)
async def admin_content_menu(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_content_menu(message)


@router.message(F.text == ADMIN_CONTENT_TAGS_HELP)
async def admin_content_formatting_help(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    text = (
        "<b>Форматирование текста</b>\n\n"
        "Можно писать обычными словами или использовать сокращения — бот сам превратит их в теги:\n"
        "• <code>**жирный**</code> → <b>жирный</b>\n"
        "• <code>_курсив_</code> → <i>курсив</i>\n"
        "• <code>__подчёркнуто__</code> → <u>подчёркнуто</u>\n"
        "• <code>`код`</code> → <code>код</code>\n"
        "• <code>[ссылка](https://site)</code> → <a href=\"https://site\">ссылка</a>\n\n"
        "Также доступны HTML-теги напрямую: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;u&gt;</code>, <code>&lt;strong&gt;</code>, <code>&lt;em&gt;</code>, <code>&lt;code&gt;</code>, <code>&lt;a href=&quot;...&quot;&gt;</code>.\n"
        "Если нужно вывести символы <code>*</code>, <code>_</code> или <code>`</code> без форматирования — поставь перед ними обратный слеш, например <code>\\*</code>.\n"
        "Плейсхолдеры (например, <code>{name}</code>) остаются без изменений и подставляются автоматически."
    )
    await message.answer(
        text,
        reply_markup=admin_content_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


@router.message(F.text == ADMIN_CONTENT_EXPORT)
async def admin_content_export(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    await _reset_state_if_needed(state)

    export_data = await _collect_content_export_data()
    total_keys = len(export_data)

    if total_keys == 0:
        await message.answer(
            "Пока нечего экспортировать — нет ни одного ключа в базе или шаблоне.",
            reply_markup=admin_content_keyboard(),
        )
        return

    yaml_payload = yaml.safe_dump(
        dict(export_data),
        allow_unicode=True,
        sort_keys=False,
    )
    json_payload = json.dumps(export_data, ensure_ascii=False, indent=2)

    yaml_file = BufferedInputFile(
        yaml_payload.encode("utf-8"),
        filename="content-export.yaml",
    )
    json_file = BufferedInputFile(
        json_payload.encode("utf-8"),
        filename="content-export.json",
    )

    try:
        await message.bot.send_document(
            chat_id=message.chat.id,
            document=yaml_file,
            caption=f"Экспорт контента — YAML ({total_keys} ключей)",
        )
        await message.bot.send_document(
            chat_id=message.chat.id,
            document=json_file,
            caption=f"Экспорт контента — JSON ({total_keys} ключей)",
        )
    except Exception as exc:
        logger.exception("content export failed: %s", exc)
        await message.answer(
            "Не удалось отправить файлы экспорта. Попробуй ещё раз или свяжись с разработчиком.",
            reply_markup=admin_content_keyboard(),
        )
        return

    await log_admin_action(
        message.from_user.id,
        "content_export",
        {"total": total_keys},
    )

    await message.answer(
        "Готово! Отправила два файла с экспортом. Их можно загрузить обратно кнопкой «⬆️ Импорт».",
        reply_markup=admin_content_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text == ADMIN_CONTENT_IMPORT)
async def admin_content_import_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    await _reset_state_if_needed(state)
    await state.set_state(AdminContentStates.waiting_import_file)

    text = (
        "<b>Импорт контента</b>\n\n"
        "Пришли файл в формате YAML или JSON с парами <code>key: value</code>.\n"
        "Можно взять свежий экспорт через кнопку «⬇️ Экспорт», внести правки и загрузить обратно.\n\n"
        "Пока файл не отправлен, можно отменить действие кнопкой «Отмена»."
    )

    await message.answer(
        text,
        reply_markup=cancel_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


def _prepare_import_items(raw_mapping: dict) -> tuple[list[tuple[str, str]], list[str]]:
    items: list[tuple[str, str]] = []
    invalid: list[str] = []

    for raw_key, raw_value in (raw_mapping or {}).items():
        key = str(raw_key or "").strip()
        if not key or not _CONTENT_KEY_PATTERN.match(key):
            invalid.append(key or "(пусто)")
            continue

        value = "" if raw_value is None else str(raw_value)
        items.append((key, value))

    return items, invalid


@router.message(AdminContentStates.waiting_import_file, F.document)
async def admin_content_import_handle_document(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    document = message.document
    if not document:
        await message.answer(
            "Пришли файл в формате YAML или JSON.",
            reply_markup=cancel_keyboard(),
        )
        return

    buffer = io.BytesIO()
    try:
        await message.bot.download(document, destination=buffer)
    except Exception as exc:
        logger.exception("content import download failed: %s", exc)
        await message.answer(
            "Не удалось скачать файл. Попробуй ещё раз позже.",
            reply_markup=cancel_keyboard(),
        )
        return

    raw_bytes = buffer.getvalue()
    try:
        text_payload = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        await message.answer(
            "Не удалось прочитать файл как UTF-8. Убедись, что файл сохранён в кодировке UTF-8.",
            reply_markup=cancel_keyboard(),
        )
        return

    parsed: dict | None = None
    data_format = "json"

    try:
        parsed_obj = json.loads(text_payload)
        if isinstance(parsed_obj, dict):
            parsed = parsed_obj
        else:
            parsed = None
    except json.JSONDecodeError:
        parsed = None

    if parsed is None:
        data_format = "yaml"
        try:
            yaml_obj = yaml.safe_load(text_payload) or {}
            if isinstance(yaml_obj, dict):
                parsed = yaml_obj
        except yaml.YAMLError as exc:
            logger.warning("content import yaml parse failed: %s", exc)
            parsed = None

    if parsed is None:
        await message.answer(
            "Не удалось распознать файл. Используй экспорт из меню или отправь корректный YAML/JSON.",
            reply_markup=cancel_keyboard(),
        )
        return

    items, invalid_keys = _prepare_import_items(parsed)
    if invalid_keys:
        sample = ", ".join(invalid_keys[:10])
        if len(invalid_keys) > 10:
            sample += " …"
        await message.answer(
            "Некоторые ключи имеют неверный формат: "
            f"{sample}. Разрешены символы A-Z, a-z, 0-9, точка, дефис и подчёркивание.",
            reply_markup=cancel_keyboard(),
        )
        return

    if not items:
        await message.answer(
            "Файл не содержит пар ключ/значение. Добавь данные и попробуй снова.",
            reply_markup=cancel_keyboard(),
        )
        return

    sanitized_items = [(key, sanitize_html(value)) for key, value in items]
    keys = [key for key, _ in sanitized_items]

    created = 0
    updated = 0

    try:
        async with transaction() as conn:
            existing_rows = await conn.fetch(
                "SELECT key FROM content WHERE key = ANY($1::text[])",
                keys,
            )
            existing = {row["key"] for row in (existing_rows or [])}

            for key, value in sanitized_items:
                await _write_content_version(key, value, message.from_user.id, conn=conn)
                if key in existing:
                    await conn.execute(
                        "UPDATE content SET value=$2, updated_at=NOW() WHERE key=$1",
                        key,
                        value,
                    )
                    updated += 1
                else:
                    await conn.execute(
                        "INSERT INTO content(key, value, created_at, updated_at) VALUES ($1,$2,NOW(),NOW())",
                        key,
                        value,
                    )
                    created += 1
    except Exception as exc:
        logger.exception("content import failed: %s", exc)
        await message.answer(
            "Не удалось сохранить данные. Проверь файл и попробуй снова позже.",
            reply_markup=cancel_keyboard(),
        )
        return

    _CONTENT_DB_CACHE.clear()

    await log_admin_action(
        message.from_user.id,
        "content_import",
        {
            "total": len(sanitized_items),
            "created": created,
            "updated": updated,
            "format": data_format,
        },
    )

    await state.clear()

    await message.answer(
        (
            "Импорт завершён ✅\n"
            f"Добавлено новых ключей: {created}.\n"
            f"Обновлено существующих: {updated}."
        ),
        reply_markup=admin_content_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_import_file)
async def admin_content_import_waiting(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    await message.answer(
        "Пришли файл с парами ключ/значение в формате YAML или JSON, либо нажми «Отмена».",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == ADMIN_CONTENT_VIEW)
async def admin_content_view_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await state.set_state(AdminContentStates.waiting_view_key)
    suggestions = await _collect_content_suggestions()
    chunk, next_offset, total, _, _ = _suggestion_chunk(suggestions, 0)
    show_more = total > len(chunk)

    await state.update_data(
        content_suggest={
            "keys": suggestions,
            "offset": next_offset,
            "step": _CONTENT_SUGGESTION_STEP,
            "context": "view",
            "cycled": False,
        }
    )

    lines = [
        "<b>Просмотр текста</b>",
        "",
        "Выбери ключ кнопкой ниже или введи его вручную, например <code>menu.support</code>.",
        "Бот покажет текущий текст и позволит обновить его — просто ответь на сообщение новым вариантом.",
    ]

    if chunk:
        lines.extend(["", "<b>Быстрый выбор:</b>"])
        lines.extend(_format_suggestion_lines(chunk))
        if show_more:
            lines.extend([
                "",
                "Нужен другой ключ — жми «🔁 Ещё варианты».",
            ])
    else:
        lines.extend([
            "",
            "Пока нет сохранённых ключей — можно указать свой и бот сохранит его.",
        ])

    lines.append("")
    lines.append("Если передумал — нажми «Отмена».")

    keyboard = admin_content_suggestions_keyboard(chunk, show_more=show_more)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_view_key, F.text == ADMIN_CONTENT_SUGGEST_MORE)
async def admin_content_view_more_options(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    suggest_info = dict((data or {}).get("content_suggest") or {})

    suggestions = await _collect_content_suggestions()
    step = int(suggest_info.get("step", _CONTENT_SUGGESTION_STEP) or _CONTENT_SUGGESTION_STEP)
    prev_offset = int(suggest_info.get("offset", 0) or 0)
    chunk, next_offset, total, reached_end, normalized = _suggestion_chunk(suggestions, prev_offset, step)
    show_more = total > len(chunk)
    cycled_flag = bool(suggest_info.get("cycled", False))
    just_wrapped = show_more and (normalized or (cycled_flag and prev_offset == 0))

    new_cycled = reached_end and show_more
    if just_wrapped:
        new_cycled = False

    suggest_info.update(
        {
            "keys": suggestions,
            "offset": next_offset,
            "step": step,
            "cycled": new_cycled,
        }
    )
    await state.update_data(content_suggest=suggest_info)

    if chunk:
        lines = ["<b>Ещё ключи</b>", ""]
        lines.extend(_format_suggestion_lines(chunk))
        if show_more:
            if reached_end:
                lines.extend([
                    "",
                    "Это последние ключи. Кнопка «🔁 Ещё варианты» покажет список сначала.",
                ])
            elif just_wrapped:
                lines.extend([
                    "",
                    "Список начался сначала — выбирай ключ или листай дальше.",
                ])
            else:
                lines.extend([
                    "",
                    "Нужен другой ключ — жми «🔁 Ещё варианты».",
                ])
    else:
        lines = [
            "<b>Ещё ключи</b>",
            "",
            "Пока нет сохранённых ключей — можно указать свой вручную.",
        ]

    keyboard = admin_content_suggestions_keyboard(chunk, show_more=show_more)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_view_key, F.text.len() > 0)
async def admin_content_view_value(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    key = (message.text or "").strip()
    if not key:
        await message.answer(
            "Укажи ключ текста, чтобы я мог его показать.",
            reply_markup=cancel_keyboard(),
            disable_web_page_preview=True,
        )
        return

    suggestions = await _collect_content_suggestions()
    if not _CONTENT_KEY_PATTERN.match(key):
        await message.answer(
            "Ключ может содержать только латинские буквы, цифры, точки, дефисы и подчёркивания."
            "\nПримеры: <code>menu.support</code>, <code>weekly_materials</code>, <code>promo.welcome</code>.",
            reply_markup=cancel_keyboard(),
            disable_web_page_preview=True,
        )
        matches = _filter_suggestions(suggestions, key)
        await _send_content_key_suggestions(message, key, matches)
        return

    value, source = await get_content_with_source(key, default="")
    _, yaml_found = _get_yaml_value(key, default="")
    last_update = await get_content_last_update(key)
    has_value = bool(value.strip())
    preview = _preview_text_for_admin(value)

    similar = [item for item in _filter_suggestions(suggestions, key, limit=5) if item != key]

    source_label = "БД" if source == "db" else "шаблон"
    show_save_button = source == "yaml" and yaml_found

    lines = [
        f"<b>Ключ:</b> <code>{html.escape(key)}</code>",
        f"<code>Источник: {source_label}</code>",
    ]

    if source == "yaml":
        lines.extend([
            "",
            "⚠️ <i>Текст ещё не скопирован в таблицу — используется шаблон из content.yaml.</i>",
        ])
        if yaml_found:
            lines.append(
                "Нажми «📥 Сохранить шаблон», чтобы перенести текст в базу и редактировать его здесь."
            )
        else:
            lines.append("Добавь текст вручную, чтобы он появился в таблице.")

    if has_value:
        lines.extend(["", "<b>Текущее значение:</b>", preview])
        lines.extend([
            "",
            "Нужен новый текст? Ответь на это сообщение — бот сохранит обновление автоматически.",
        ])
    else:
        lines.extend([
            "",
            "По этому ключу пока ничего не сохранено.",
            "Можно добавить текст через кнопку «➕ Добавить или обновить текст».",
        ])

        if similar:
            lines.extend([
                "",
                "Возможно, подойдут другие ключи:",
                *_format_suggestion_lines(similar),
            ])

        lines.extend([
            "",
            "Отправь текст ответом на это сообщение — и он сразу появится в боте.",
        ])

    if last_update:
        updated_at_text = _format_datetime_safe(last_update.get("updated_at"))
        author_text = await _format_content_version_author(last_update.get("updated_by"))
        lines.extend([
            "",
            "<b>Последнее обновление:</b>",
            f"{updated_at_text} — {author_text}",
        ])

    history_hint = (
        f"Чтобы посмотреть историю изменений, ответь «{ADMIN_CONTENT_HISTORY}» на это сообщение"
        f" или выбери пункт «{ADMIN_CONTENT_HISTORY}» в меню."
    )
    lines.extend(["", history_hint])

    await state.update_data(
        content_current_key=key,
        content_current_source=source,
        content_current_has_yaml=yaml_found,
    )

    await log_admin_action(
        message.from_user.id,
        "content_view_menu",
        {"key": key, "has_value": has_value, "source": source},
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=admin_content_keyboard(include_save_template=show_save_button),
        disable_web_page_preview=True,
    )


@router.message(F.text == ADMIN_CONTENT_HISTORY)
async def admin_content_history_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    await _reset_state_if_needed(state)
    await state.set_state(AdminContentStates.waiting_history_key)

    suggestions = await _collect_content_suggestions()
    chunk, next_offset, total, _, _ = _suggestion_chunk(suggestions, 0)
    show_more = total > len(chunk)

    await state.update_data(
        content_suggest={
            "keys": suggestions,
            "offset": next_offset,
            "step": _CONTENT_SUGGESTION_STEP,
            "context": "history",
            "cycled": False,
        }
    )

    lines = [
        "<b>История изменений</b>",
        "",
        "Введи ключ вручную или выбери из списка, чтобы посмотреть последние сохранённые версии.",
        "После выбора покажу последние изменения и предложу откатить текст к нужной версии.",
    ]

    if chunk:
        lines.extend(["", "<b>Быстрый выбор:</b>"])
        lines.extend(_format_suggestion_lines(chunk))
        if show_more:
            lines.extend([
                "",
                "Не нашёл нужный ключ — жми «🔁 Ещё варианты».",
            ])
    else:
        lines.extend([
            "",
            "Пока нет сохранённых ключей — можно указать свой вручную.",
        ])

    lines.append("")
    lines.append("Если передумал — нажми «Отмена».")

    keyboard = admin_content_suggestions_keyboard(chunk, show_more=show_more)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_history_key, F.text == ADMIN_CONTENT_SUGGEST_MORE)
async def admin_content_history_more_options(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    suggest_info = dict((data or {}).get("content_suggest") or {})
    if suggest_info.get("context") != "history":
        await message.answer(
            "Используй команду «🕘 История версий», чтобы выбрать ключ и посмотреть прошлые значения.",
            reply_markup=admin_content_keyboard(),
        )
        await state.clear()
        return

    suggestions = await _collect_content_suggestions()
    step = int(suggest_info.get("step", _CONTENT_SUGGESTION_STEP) or _CONTENT_SUGGESTION_STEP)
    prev_offset = int(suggest_info.get("offset", 0) or 0)
    chunk, next_offset, total, reached_end, normalized = _suggestion_chunk(suggestions, prev_offset, step)
    show_more = total > len(chunk)
    cycled_flag = bool(suggest_info.get("cycled", False))
    just_wrapped = show_more and (normalized or (cycled_flag and prev_offset == 0))

    new_cycled = reached_end and show_more
    if just_wrapped:
        new_cycled = False

    suggest_info.update(
        {
            "keys": suggestions,
            "offset": next_offset,
            "step": step,
            "cycled": new_cycled,
        }
    )
    await state.update_data(content_suggest=suggest_info)

    if chunk:
        lines = ["<b>Ещё ключи</b>", ""]
        lines.extend(_format_suggestion_lines(chunk))
        if show_more:
            if reached_end:
                lines.extend([
                    "",
                    "Это последние ключи. Кнопка «🔁 Ещё варианты» вернёт список к началу.",
                ])
            elif just_wrapped:
                lines.extend([
                    "",
                    "Снова показываю ключи с начала — выбирай нужный или листай дальше.",
                ])
            else:
                lines.extend([
                    "",
                    "Не подходит? Жми «🔁 Ещё варианты».",
                ])
    else:
        lines = [
            "<b>Ещё ключи</b>",
            "",
            "Сохранённых ключей пока нет — можно ввести свой вручную.",
        ]

    keyboard = admin_content_suggestions_keyboard(chunk, show_more=show_more)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_history_key, F.text.len() > 0)
async def admin_content_history_receive_key(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    key = (message.text or "").strip()
    if not key:
        await message.answer(
            "Укажи ключ текста, чтобы посмотреть историю изменений.",
            reply_markup=cancel_keyboard(),
        )
        return

    if not _CONTENT_KEY_PATTERN.match(key):
        await message.answer(
            "Ключ может содержать только латинские буквы, цифры, точки, дефисы и подчёркивания.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()
    suggest_info = dict((data or {}).get("content_suggest") or {})
    suggestions = suggest_info.get("keys") or await _collect_content_suggestions()

    found = await _send_content_history(message, state, key, source="menu")
    if found:
        return

    similar = [item for item in _filter_suggestions(suggestions or [], key, limit=5) if item != key]
    lines = [
        f"<b>Ключ:</b> <code>{html.escape(key)}</code>",
        "",
        "Для этого ключа пока нет сохранённых версий.",
    ]
    if similar:
        lines.extend([
            "",
            "Возможно, подойдут другие ключи:",
            *_format_suggestion_lines(similar),
        ])
    lines.extend([
        "",
        "Введи другой ключ или нажми «Отмена», чтобы вернуться назад.",
    ])

    keyboard = admin_content_suggestions_keyboard(similar, show_more=False)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_history_choice, F.text.len() > 0)
async def admin_content_history_choose_version(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    data = await state.get_data()
    history = dict((data or {}).get("content_history") or {})
    key = history.get("key")
    choices = history.get("choices") or {}
    options_count = len(choices)

    if not text.startswith(ADMIN_CONTENT_ROLLBACK_PREFIX):
        await message.answer(
            "Выбери версию кнопкой «↩️ Откатить N» или нажми «Отмена».",
            reply_markup=admin_content_versions_keyboard(options_count),
        )
        return

    choice_raw = text[len(ADMIN_CONTENT_ROLLBACK_PREFIX):].strip()
    if not choice_raw.isdigit():
        await message.answer(
            "Не удалось распознать номер версии. Попробуй выбрать кнопку ещё раз.",
            reply_markup=admin_content_versions_keyboard(options_count),
        )
        return

    version_id = choices.get(choice_raw)

    if not key or not version_id:
        await state.clear()
        await message.answer(
            "Не удалось определить выбранную версию. Начни заново через «🕘 История версий».",
            reply_markup=admin_content_keyboard(),
        )
        return

    version_row = await fetchrow(
        "SELECT value, updated_at, updated_by FROM content_versions WHERE id=$1",
        version_id,
    )
    if not version_row:
        await state.clear()
        await message.answer(
            "Версия не найдена. Попробуй снова через «🕘 История версий».",
            reply_markup=admin_content_keyboard(),
        )
        return

    version_value = str(version_row.get("value") or "")
    await set_content_value(key, version_value, updated_by=message.from_user.id)

    await log_admin_action(
        message.from_user.id,
        "content_history_rollback",
        {"key": key, "version_id": version_id},
    )

    timestamp_text = _format_datetime_safe(version_row.get("updated_at"))
    author_text = await _format_content_version_author(version_row.get("updated_by"))
    preview = _preview_text_for_admin(version_value)

    lines = [
        f"<b>Ключ:</b> <code>{html.escape(key)}</code>",
        "",
        f"Текст откатан к версии от {timestamp_text} ({author_text}).",
        "",
        "<b>Текущее значение:</b>",
        preview,
        "",
        "Можно ответить на это сообщение, чтобы сохранить новый вариант.",
    ]

    await state.clear()
    await message.answer(
        "\n".join(lines),
        reply_markup=admin_content_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text == ADMIN_CONTENT_CREATE)
async def admin_content_create_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await state.set_state(AdminContentStates.waiting_custom_key)
    suggestions = await _collect_content_suggestions()
    chunk, next_offset, total, _, _ = _suggestion_chunk(suggestions, 0)
    show_more = total > len(chunk)

    await state.update_data(
        content_suggest={
            "keys": suggestions,
            "offset": next_offset,
            "step": _CONTENT_SUGGESTION_STEP,
            "context": "create",
            "cycled": False,
        }
    )

    lines = [
        "<b>Добавление текста</b>",
        "",
        "Введи ключ или выбери готовый из списка ниже. Допустимы латинские буквы, цифры, точки, дефисы и подчёркивания.",
        "Если ключ уже существует, бот покажет текущий текст и попросит новый вариант.",
    ]

    if chunk:
        lines.extend(["", "<b>Быстрый выбор:</b>"])
        lines.extend(_format_suggestion_lines(chunk))
        if show_more:
            lines.extend([
                "",
                "Не нашёл нужный ключ — жми «🔁 Ещё варианты».",
            ])
    else:
        lines.extend([
            "",
            "Пока нет сохранённых ключей — можно создать первый.",
        ])

    lines.extend([
        "",
        "Бот понимает <code>**жирный**</code>, <code>_курсив_</code> и другие сокращения — можно писать как в заметке, он всё приведёт в порядок.",
        "За подробностями нажми «ℹ️ Форматирование текста».",
        "",
        "После выбора бот покажет текущий текст и предложит отправить новый вариант одним сообщением.",
        "Для отмены нажми «Отмена».",
    ])

    keyboard = admin_content_suggestions_keyboard(chunk, show_more=show_more)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_custom_key, F.text == ADMIN_CONTENT_SUGGEST_MORE)
async def admin_content_create_more_options(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    suggest_info = dict((data or {}).get("content_suggest") or {})

    suggestions = await _collect_content_suggestions()
    step = int(suggest_info.get("step", _CONTENT_SUGGESTION_STEP) or _CONTENT_SUGGESTION_STEP)
    prev_offset = int(suggest_info.get("offset", 0) or 0)
    chunk, next_offset, total, reached_end, normalized = _suggestion_chunk(suggestions, prev_offset, step)
    show_more = total > len(chunk)
    cycled_flag = bool(suggest_info.get("cycled", False))
    just_wrapped = show_more and (normalized or (cycled_flag and prev_offset == 0))

    new_cycled = reached_end and show_more
    if just_wrapped:
        new_cycled = False

    suggest_info.update(
        {
            "keys": suggestions,
            "offset": next_offset,
            "step": step,
            "cycled": new_cycled,
        }
    )
    await state.update_data(content_suggest=suggest_info)

    if chunk:
        lines = ["<b>Ещё ключи</b>", ""]
        lines.extend(_format_suggestion_lines(chunk))
        if show_more:
            if reached_end:
                lines.extend([
                    "",
                    "Это последние ключи. Кнопка «🔁 Ещё варианты» вернёт список к началу.",
                ])
            elif just_wrapped:
                lines.extend([
                    "",
                    "Снова показываю ключи с начала — выбирай нужный или листай дальше.",
                ])
            else:
                lines.extend([
                    "",
                    "Не подходит? Жми «🔁 Ещё варианты».",
                ])
    else:
        lines = [
            "<b>Ещё ключи</b>",
            "",
            "Сохранённых ключей пока нет — можно ввести свой вручную.",
        ]

    keyboard = admin_content_suggestions_keyboard(chunk, show_more=show_more)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_custom_key, F.text.len() > 0)
async def admin_content_receive_key(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    raw_key = (message.text or "").strip()
    if not raw_key:
        await message.answer(
            "Ключ не может быть пустым. Попробуй ещё раз.",
            reply_markup=cancel_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if not _CONTENT_KEY_PATTERN.match(raw_key):
        suggestions = await _collect_content_suggestions()
        await message.answer(
            "Ключ может содержать только латинские буквы, цифры, точки, дефисы и подчёркивания."
            "\nПримеры: <code>menu.support</code>, <code>weekly_materials</code>, <code>promo.welcome</code>.",
            reply_markup=cancel_keyboard(),
            disable_web_page_preview=True,
        )
        matches = _filter_suggestions(suggestions, raw_key)
        await _send_content_key_suggestions(message, raw_key, matches)
        return

    key = raw_key
    current_value, source = await get_content_with_source(key, default="")
    _, yaml_found = _get_yaml_value(key, default="")
    has_value = bool(current_value.strip())
    preview = _preview_text_for_admin(current_value)

    await state.update_data(
        custom_key=key,
        content_current_key=key,
        content_current_source=source,
        content_current_has_yaml=yaml_found,
    )
    await state.set_state(AdminContentStates.waiting_custom_value)

    source_label = "БД" if source == "db" else "шаблон"
    show_save_button = source == "yaml" and yaml_found

    lines = [
        f"<b>Ключ:</b> <code>{html.escape(key)}</code>",
        f"<code>Источник: {source_label}</code>",
    ]

    if source == "yaml":
        lines.extend([
            "",
            "⚠️ <i>Текст ещё не скопирован в таблицу — используется шаблон из content.yaml.</i>",
        ])
        if yaml_found:
            lines.append(
                "Нажми «📥 Сохранить шаблон», чтобы скопировать текст в базу и редактировать его здесь."
            )
        else:
            lines.append("Добавь текст вручную, чтобы он появился в таблице.")

    if has_value:
        lines.extend(["", "<b>Текущее значение:</b>", preview])
    else:
        lines.extend([
            "",
            "По этому ключу пока ничего нет — введи текст и он появится в боте.",
        ])

    lines.extend([
        "",
        "Пришли новый текст одним сообщением. Допустимы теги:"
        " &lt;b&gt;, &lt;i&gt;, &lt;u&gt;, &lt;strong&gt;, &lt;em&gt;, &lt;code&gt;, &lt;a href=&quot;...&quot;&gt;ссылка&lt;/a&gt;.",
        "Можно отправить текст обычным сообщением или ответом на это сообщение — бот сохранит результат сразу.",
    ])

    await message.answer(
        "\n".join(lines),
        reply_markup=cancel_keyboard(
            extra_buttons=[ADMIN_CONTENT_SAVE_TEMPLATE_BUTTON] if show_save_button else None
        ),
        disable_web_page_preview=True,
    )


@router.message(F.text == ADMIN_CONTENT_SAVE_TEMPLATE_BUTTON)
async def admin_content_save_template(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data() or {}
    key = (data.get("content_current_key") or data.get("custom_key")) if data else None
    if not key:
        await message.answer(
            "Сначала выбери ключ текста через меню — бот покажет источник и доступные действия.",
            reply_markup=admin_content_keyboard(),
            disable_web_page_preview=True,
        )
        return

    yaml_value, yaml_found = _get_yaml_value(key, default="")
    if not yaml_found:
        current_state = await state.get_state()
        keyboard = (
            cancel_keyboard()
            if current_state == AdminContentStates.waiting_custom_value.state
            else admin_content_keyboard()
        )
        await message.answer(
            "В content.yaml нет шаблона для этого ключа — добавь текст вручную и он сохранится в таблицу.",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        return

    await set_content_value(key, yaml_value, updated_by=message.from_user.id)

    saved_value, _ = await get_content_with_source(key, default="")
    preview = _preview_text_for_admin(saved_value)

    await state.update_data(content_current_source="db")

    lines = [
        f"<b>Ключ:</b> <code>{html.escape(key)}</code>",
        "<code>Источник: БД</code>",
    ]

    if saved_value.strip():
        lines.extend(["", "<b>Текст из шаблона сохранён:</b>", preview])
    else:
        lines.extend([
            "",
            "Шаблон был пустым — в таблицу сохранено пустое значение. Можешь отправить нужный текст ответом.",
        ])

    lines.extend([
        "",
        "Теперь текст хранится в базе. Ответь на сообщение новым вариантом или выбери другую команду.",
    ])

    current_state = await state.get_state()
    keyboard = (
        cancel_keyboard()
        if current_state == AdminContentStates.waiting_custom_value.state
        else admin_content_keyboard()
    )

    await log_admin_action(
        message.from_user.id,
        "content_save_template",
        {"key": key, "length": len(saved_value)},
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_custom_value, F.text.len() > 0)
async def admin_content_receive_value(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    key = (data or {}).get("custom_key")
    if not key:
        await state.clear()
        await message.answer(
            "Не удалось определить ключ. Начни заново через «➕ Добавить или обновить текст».",
            reply_markup=admin_content_keyboard(),
        )
        return

    new_text = prepare_admin_text_input(message.text)

    missing_placeholders = _admin_missing_required_placeholders(new_text, key)
    if missing_placeholders:
        missing_tokens = ", ".join(
            f"<code>{html.escape(token)}</code>" for token in missing_placeholders
        )
        await message.answer(
            "Не удалось сохранить текст — отсутствуют обязательные плейсхолдеры: "
            f"{missing_tokens}. Добавь их и отправь текст ещё раз.",
            reply_markup=cancel_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    await set_content_value(key, new_text, updated_by=message.from_user.id)
    await log_admin_action(
        message.from_user.id,
        "content_set_custom_menu",
        {"key": key, "length": len(new_text)},
    )

    await message.answer(
        f"Текст для ключа <code>{html.escape(key)}</code> сохранён ✅",
        reply_markup=admin_content_keyboard(),
        disable_web_page_preview=True,
    )

    await state.clear()


def _extract_content_key_from_reply_message(reply: types.Message | None) -> Optional[str]:
    if not reply or not reply.from_user or not reply.from_user.is_bot:
        return None

    preview_html = reply.html_text or ""
    match = _CONTENT_PREVIEW_KEY_RE.search(preview_html)

    if match:
        return html.unescape(match.group(1) or "").strip()

    plain = reply.text or ""
    match_plain = _CONTENT_PREVIEW_KEY_PLAIN_RE.search(plain)
    if match_plain:
        return match_plain.group(1).strip()

    return None


@router.message(
    F.reply_to_message,
    F.reply_to_message.from_user.func(lambda user: user is not None and user.is_bot),
)
async def admin_content_quick_reply_update(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    if await state.get_state():
        return

    if (message.text or "").strip() == ADMIN_CONTENT_HISTORY:
        raise EventSkip()

    reply = message.reply_to_message
    if not reply or reply.from_user.id != message.bot.id:
        return

    key = _extract_content_key_from_reply_message(reply)

    if not key or not _CONTENT_KEY_PATTERN.match(key):
        return

    source_text = message.text or message.caption or ""
    new_text = prepare_admin_text_input(source_text)
    if not new_text:
        await message.answer(
            "Сообщение пустое — текст не обновлён. Пришли текст или используй меню.",
            reply_markup=admin_content_keyboard(),
            disable_web_page_preview=True,
        )
        return

    await set_content_value(key, new_text, updated_by=message.from_user.id)
    await log_admin_action(
        message.from_user.id,
        "content_quick_reply",
        {"key": key, "length": len(new_text)},
    )

    await message.answer(
        f"Текст для ключа <code>{html.escape(key)}</code> обновлён ✅",
        reply_markup=admin_content_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(
    F.reply_to_message,
    F.reply_to_message.from_user.func(lambda user: user is not None and user.is_bot),
    F.text == ADMIN_CONTENT_HISTORY,
)
async def admin_content_history_reply(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    if await state.get_state():
        return

    reply = message.reply_to_message
    if not reply or reply.from_user.id != message.bot.id:
        return

    key = _extract_content_key_from_reply_message(reply)
    if not key or not _CONTENT_KEY_PATTERN.match(key):
        await message.answer(
            "Не удалось определить ключ. Попробуй снова через меню или введи ключ вручную.",
            reply_markup=admin_content_keyboard(),
        )
        return

    found = await _send_content_history(message, state, key, source="reply")
    if found:
        return

    await message.answer(
        f"Для ключа <code>{html.escape(key)}</code> пока нет сохранённых версий.",
        reply_markup=admin_content_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text == ADMIN_STATS_BUTTON)
async def admin_stats(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    stats = await _collect_admin_stats_data()
    stats_text = _format_admin_stats_overview(stats)
    await message.answer(
        stats_text,
        reply_markup=admin_stats_keyboard(),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_STATS_REFRESH)
async def admin_stats_refresh(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    stats = await _collect_admin_stats_data()
    stats_text = _format_admin_stats_overview(stats)
    await message.answer(
        stats_text,
        reply_markup=admin_stats_keyboard(),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_STATS_USERS_BREAKDOWN)
async def admin_stats_users_breakdown(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    stats = await _collect_admin_stats_data()
    text = _format_admin_stats_users(stats)
    await message.answer(
        text,
        reply_markup=admin_stats_keyboard(),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_STATS_LESSON_PROGRESS)
async def admin_stats_lessons_breakdown(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    stats = await _collect_admin_stats_data()
    text = _format_admin_stats_lessons(stats)
    await message.answer(
        text,
        reply_markup=admin_stats_keyboard(),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_STATS_PAYMENTS_BREAKDOWN)
async def admin_stats_payments_breakdown(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    stats = await _collect_admin_stats_data()
    text = _format_admin_stats_payments(stats)
    await message.answer(
        text,
        reply_markup=admin_stats_keyboard(),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_STATS_FORMS_BREAKDOWN)
async def admin_stats_forms_breakdown(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    stats = await _collect_admin_stats_data()
    text = _format_admin_stats_forms(stats)
    await message.answer(
        text,
        reply_markup=admin_stats_keyboard(),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_STATS_RECENT_PAYMENTS)
async def admin_stats_recent_payments(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    payments = await _fetch_recent_payments(limit=10)
    timestamp_text = _format_datetime_safe(now_utc())
    if not payments:
        text = "\n".join(
            [
                "<b>🧾 Последние оплаты</b>",
                "",
                "Пока нет платежей в базе.",
                "",
                f"Обновлено: {timestamp_text}",
            ]
        )
    else:
        lines = ["<b>🧾 Последние оплаты</b>", ""]
        lines.extend(_format_admin_payment_entry(payment) for payment in payments)
        lines.extend([
            "",
            "Подробное управление доступами — в разделе «💳 Оплаты».",
            f"Обновлено: {timestamp_text}",
        ])
        text = "\n".join(lines)

    await message.answer(
        text,
        reply_markup=admin_stats_keyboard(),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_DEBUG_BUTTON)
async def admin_debug(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    config_text = (
        "<b>🛠️ Диагностика</b>\n\n"
        f"Версия: {BOT_VERSION}\n"
        f"Часовой пояс: {BOT_TIMEZONE}\n"
        f"Поддержка: {SUPPORT_CONTACT}\n"
        f"Продукт ID: {AT_PRODUCT_ID_CLUB or 'Не задан'}\n"
        f"Чат клуба: {CLUB_CHAT_ID or 'Не задан'}"
    )
    await message.answer(config_text, reply_markup=admin_main_keyboard(), disable_web_page_preview=True)


@router.message(F.text == ADMIN_SETTINGS_BUTTON)
async def admin_settings_menu(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_settings(message)


@router.message(F.text == ADMIN_PAYMENTS_BUTTON)
async def admin_payments_menu(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_payments_overview(message)


@router.message(F.text.in_({ADMIN_PAYMENTS_OPEN_WINDOW, ADMIN_PAYMENTS_CLOSE_WINDOW}))
async def admin_payments_toggle_window(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    new_value = message.text == ADMIN_PAYMENTS_OPEN_WINDOW
    await set_bool_setting("payments_open", new_value, updated_by=message.from_user.id)
    await log_admin_action(
        message.from_user.id,
        "payments_toggle_window",
        {"payments_open": new_value},
    )
    await send_admin_payments_overview(message)


@router.message(F.text == ADMIN_PAYMENTS_SHOW_LATEST)
async def admin_payments_show_latest(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_payments_overview(message)


@router.message(F.text == ADMIN_PAYMENTS_CONFIRM_ACCESS)
async def admin_payments_prompt_grant(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await state.set_state(AdminPaymentsStates.waiting_access_user)
    await message.answer(
        "Отправь @username или ID участницы и срок доступа.\n"
        "Примеры: <code>@username 30</code>, <code>123456789 2024-12-31</code>,"
        " <code>@username forever</code>.",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == ADMIN_PAYMENTS_REVOKE_ACCESS)
async def admin_payments_prompt_revoke(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await state.set_state(AdminPaymentsStates.waiting_revoke_user)
    await message.answer(
        "Отправь @username или ID участницы, чтобы приостановить доступ.",
    )


@router.message(F.text.in_({ADMIN_PAYMENTS_MARK_PAID, ADMIN_PAYMENTS_MARK_FAILED}))
async def admin_payments_prompt_review(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)

    status = "paid" if message.text == ADMIN_PAYMENTS_MARK_PAID else "failed"
    await state.set_state(AdminPaymentsStates.waiting_payment_review)
    await state.update_data(review_status=status)
    await message.answer(
        "Отправь order_id или ID платежа. Можно добавить комментарий через пробел.",
    )


@router.message(AdminPaymentsStates.waiting_access_user, F.text)
async def admin_payments_receive_access(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужны данные: отправь @username или ID участницы.")
        return

    parts = text.split()
    target = parts[0]
    user = await _admin_find_user(target)
    if not user:
        await message.answer("Не нашла такую участницу. Проверь ник или ID и попробуй снова.")
        return

    access_until, consumed = _parse_admin_access_token(parts[1] if len(parts) > 1 else None)
    comment_tokens = parts[2:] if consumed else parts[1:]
    comment = " ".join(comment_tokens).strip() or None

    if access_until is None and not consumed:
        # По умолчанию продлеваем на 30 дней
        access_until = now_utc() + timedelta(days=30)

    await _admin_set_member_active(user["id"], access_until)
    await log_admin_action(
        message.from_user.id,
        "payments_manual_grant",
        {
            "user_id": user["id"],
            "access_until": access_until.isoformat() if access_until else None,
            "comment": comment,
        },
    )

    await state.clear()

    access_text = "бессрочно" if access_until is None else _format_datetime_safe(access_until)
    await message.answer(
        (
            f"Доступ для {html.escape(_admin_user_display_name(user))} обновлён.\n"
            f"Статус: активен до {access_text}."
        ),
        parse_mode=ParseMode.HTML,
    )
    await send_admin_payments_overview(message)


@router.message(AdminPaymentsStates.waiting_revoke_user, F.text)
async def admin_payments_receive_revoke(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Отправь @username или ID, чтобы приостановить доступ.")
        return

    user = await _admin_find_user(text)
    if not user:
        await message.answer("Не нашла такую участницу. Проверь данные и попробуй снова.")
        return

    await _admin_set_member_expired(user["id"])
    await log_admin_action(
        message.from_user.id,
        "payments_manual_revoke",
        {"user_id": user["id"]},
    )

    await state.clear()

    await message.answer(
        f"Доступ для {html.escape(_admin_user_display_name(user))} приостановлен.",
        parse_mode=ParseMode.HTML,
    )
    await send_admin_payments_overview(message)


@router.message(AdminPaymentsStates.waiting_payment_review, F.text)
async def admin_payments_receive_review(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    data = await state.get_data()
    status = data.get("review_status", "paid")

    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужно указать order_id или ID платежа.")
        return

    parts = text.split(maxsplit=1)
    identifier = parts[0]
    comment = parts[1].strip() if len(parts) > 1 else None

    payment_row = None
    if identifier.isdigit():
        payment_row = await fetchrow("SELECT * FROM payments WHERE id=$1", int(identifier))
    if not payment_row:
        payment_row = await fetchrow("SELECT * FROM payments WHERE order_id=$1", identifier)

    if not payment_row:
        await message.answer("Платёж не найден. Проверь order_id или ID и попробуй снова.")
        return

    payment = dict(payment_row)
    await execute(
        """
        UPDATE payments
           SET status=$2,
               paid_at = CASE WHEN $2='paid' THEN COALESCE(paid_at, NOW()) ELSE NULL END,
               raw_payload = COALESCE(raw_payload, '{}'::jsonb)
                    || jsonb_build_object(
                        'manual_checked_at', NOW(),
                        'manual_checked_by', $3,
                        'manual_status', $2,
                        'manual_comment', $4
                    )
         WHERE id=$1
        """,
        payment["id"],
        status,
        str(message.from_user.id),
        comment,
    )

    await log_admin_action(
        message.from_user.id,
        "payments_mark_status",
        {
            "payment_id": payment["id"],
            "order_id": payment.get("order_id"),
            "status": status,
            "comment": comment,
        },
    )

    await state.clear()

    await message.answer(
        (
            f"Платёж <code>{html.escape(payment.get('order_id') or str(payment['id']))}</code>"
            f" отмечен как {status}."
        ),
        parse_mode=ParseMode.HTML,
    )
    await send_admin_payments_overview(message)


@router.message(F.text == ADMIN_TEXTS_ENTRY)
async def admin_texts_entry(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_text_groups(message)


@router.message(F.text == BACK_TO_TEXT_GROUPS)
async def admin_texts_back_to_groups(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_text_groups(message)


@router.message(F.text.func(lambda text: text in _ADMIN_TEXT_GROUPS))
async def admin_texts_open_group(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_text_items(message, message.text)


@router.message(F.text.func(lambda text: _admin_find_text_entry(text or "")[1] is not None))
async def admin_texts_edit_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    group_title, key = _admin_find_text_entry(message.text or "")
    if not key:
        return

    await _reset_state_if_needed(state)
    await state.set_state(AdminContentStates.waiting_value)
    await state.update_data(
        content_key=key,
        content_group=group_title,
        content_label=message.text,
        content_preview_text=current_text,
    )

    current_text = await get_content(key, default="")
    preview = _preview_text_for_admin(current_text)

    placeholders_line = _admin_placeholder_hint_line(key)

    text_lines = [
        f"<b>Редактирование текста:</b> {html.escape(message.text or key)}",
        "",
        "<b>Текущий текст:</b>",
        preview,
        "",
        "Можно писать обычным текстом — бот преобразует <code>**жирный**</code>, <code>_курсив_</code> и другие сокращения в поддерживаемые теги.",
        "Если нужна памятка по форматированию — нажми «ℹ️ Форматирование текста».",
        "",
        "Отправь новый текст одним сообщением — бот сохранит его и сразу начнёт использовать.",
        "Допустимы теги: &lt;b&gt;, &lt;i&gt;, &lt;u&gt;, &lt;strong&gt;, &lt;em&gt;, &lt;code&gt;, &lt;a href=&quot;...&quot;&gt;ссылка&lt;/a&gt;.",
        "Можно отправить текст обычным сообщением или ответом на это сообщение — бот обработает оба варианта.",
    ]

    if placeholders_line:
        text_lines.extend(["", placeholders_line])

    text_lines.append("\nДля отмены нажми «Отмена».")

    await message.answer(
        "\n".join(text_lines),
        reply_markup=cancel_keyboard(extra_buttons=[ADMIN_TEXTS_PREVIEW_BUTTON]),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_value, F.text == ADMIN_TEXTS_PREVIEW_BUTTON)
async def admin_texts_preview(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data() or {}
    preview_text = (data.get("content_preview_text") or "").strip()

    if not preview_text:
        await message.answer(
            "Предпросмотр недоступен — текст пустой. Отправь новый текст и попробуй ещё раз.",
            reply_markup=cancel_keyboard(extra_buttons=[ADMIN_TEXTS_PREVIEW_BUTTON]),
            disable_web_page_preview=True,
        )
        return

    rendered = render_content(preview_text, **_ADMIN_TEXT_PREVIEW_SAMPLE_DATA)
    rendered = rendered.strip()

    if not rendered:
        response_text = "<b>Предпросмотр пустой.</b>"
    else:
        label = data.get("content_label") or data.get("content_key")
        label_text = f"<b>Предпросмотр: {html.escape(label or '')}</b>" if label else "<b>Предпросмотр:</b>"
        response_text = f"{label_text}\n\n{rendered}"

    await message.answer(
        response_text,
        reply_markup=cancel_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


@router.message(AdminContentStates.waiting_value, F.text.len() > 0)
async def admin_texts_receive_value(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    key = data.get("content_key")
    label = data.get("content_label") or key
    group_title = data.get("content_group")

    if not key:
        await state.clear()
        await message.answer("Не удалось определить, какой текст обновить. Попробуй ещё раз.")
        return

    new_text = prepare_admin_text_input(message.text)
    await state.update_data(content_preview_text=new_text)

    missing_placeholders = _admin_missing_required_placeholders(new_text, key)
    if missing_placeholders:
        missing_tokens = ", ".join(
            f"<code>{html.escape(token)}</code>" for token in missing_placeholders
        )
        await message.answer(
            "Не удалось сохранить текст — отсутствуют обязательные плейсхолдеры: "
            f"{missing_tokens}. Добавь их и отправь текст ещё раз.",
            reply_markup=cancel_keyboard(extra_buttons=[ADMIN_TEXTS_PREVIEW_BUTTON]),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    await set_content_value(key, new_text, updated_by=message.from_user.id)
    await log_admin_action(
        message.from_user.id,
        "content_set_menu",
        {"key": key, "length": len(new_text)},
    )

    await message.answer(
        f"Текст «{label}» обновлён ✅",
        reply_markup=admin_text_groups_keyboard(list(_ADMIN_TEXT_GROUPS.keys())),
    )

    await state.clear()

    if group_title:
        await send_admin_text_items(message, group_title)
    else:
        await send_admin_text_groups(message)


@router.message(F.text == BACK_TO_ADMIN)
async def admin_back(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_menu(message)


@router.message(F.text.func(lambda text: _admin_toggle_key_from_text(text) is not None))
async def admin_toggle_settings(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    key = _admin_toggle_key_from_text(message.text)
    if not key:
        return
    current = await get_bool_setting(key, _ADMIN_SETTINGS_DEFAULTS[key])
    new_value = not current
    await set_bool_setting(key, new_value, updated_by=message.from_user.id)
    await log_admin_action(message.from_user.id, "toggle_setting", {"key": key, "value": new_value})
    await send_admin_settings(message)


# ──────────────────────────────────────────────────────────────────────────────
# Админка: доступ/помощь
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: types.Message, command: CommandObject, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    await _reset_state_if_needed(state)

    if not command.args:
        await send_admin_menu(message)
        return
    
    args = command.args.strip().split()
    sub = args[0].lower()
    
    if sub == "user":
        if len(args) < 2:
            await message.answer("Использование: /admin user <code>username или tg_id</code>")
            return
        target = args[1]
        user_row = None
        if target.startswith("@"):
            user_row = await fetchrow("SELECT * FROM users WHERE username=$1", target[1:])
        else:
            try:
                tg_id = int(target)
            except ValueError:
                await message.answer("tg_id должен быть числом.")
                return
            user_row = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_id)
        
        if not user_row:
            await message.answer("Пользователь не найден.")
            return
        
        rows = await fetch(
            "SELECT lesson_num, hw_status FROM funnel_progress WHERE user_id=$1 ORDER BY lesson_num",
            user_row["id"]
        )
        progress = ", ".join([f"{r['lesson_num']}:{r['hw_status']}" for r in rows]) if rows else "—"
        
        last_activity = user_row.get("last_activity_at") or "—"
        if last_activity != "—":
            try:
                if isinstance(last_activity, str):
                    last_activity = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
                last_activity = tz_aware_msk(last_activity)
            except (ValueError, AttributeError):
                pass
        
        text = (
            f"Пользователь #{user_row['id']}\n\n"
            f"Telegram: {user_row['tg_user_id']} @{user_row.get('username')}\n"
            f"Имя: {user_row.get('name')}\n"
            f"Фамилия: {user_row.get('full_name')}\n"
            f"Статус: {user_row.get('status')}\n"
            f"Доступ до: {user_row.get('access_until')}\n"
            f"Последняя активность: {last_activity}\n\n"
            f"Прогресс: {progress}\n\n"
            f"Email: {user_row.get('email') or '—'}\n"
            f"Телефон: {user_row.get('phone') or '—'}\n\n"
            f"UTM: {user_row.get('utm_source')}/{user_row.get('utm_medium')}/{user_row.get('utm_campaign')}"
        )
        await message.answer(text)
        return
    
    elif sub == "set_paid":
        if len(args) < 2:
            await message.answer("Использование: /admin set_paid <code>username</code> [days или YYYY-MM-DD]")
            return
        username = args[1]
        
        access_until = datetime(2030, 1, 1, tzinfo=timezone.utc)
        
        user_row = await fetchrow("SELECT * FROM users WHERE username=$1", username.lstrip("@"))
        if not user_row:
            await message.answer("Пользователь не найден.")
            return
        
        await execute(
            """UPDATE users SET status='member_active', access_until=$2,
                      joined_club_at=COALESCE(joined_club_at, NOW()), updated_at=NOW()
               WHERE id=$1""",
            user_row["id"], access_until
        )
        
        await log_admin_action(
            message.from_user.id,
            "set_paid",
            {
                "user_id": user_row["id"],
                "access_until": access_until.isoformat()
            }
        )
        
        invite = await generate_invite_link_or_placeholder(message.bot, CLUB_CHAT_ID)
        onboard0 = await get_content("onboarding.0", f"Добро пожаловать! Начни с этого поста: {WELCOME_POST_URL}")
        
        try:
            await message.bot.send_message(
                user_row["tg_user_id"],
                f"Поздравляем! Твой доступ в клуб открыт!\n\n"
                f"Доступ активен навсегда.\n\n"
                f"Твой инвайт (активен 24ч): {invite}\n\n"
                f"{onboard0}"
            )
        except Exception as e:
            logger.error(f"Failed to send invite to user {user_row['tg_user_id']}: {e}")
            invite = "Не удалось отправить инвайт автоматически"
        
        await message.answer(
            f"Статус обновлён: member_active навсегда.\n\n"
            f"Инвайт: {invite}"
        )
        return
    
    elif sub == "access":
        if len(args) < 2:
            await message.answer("Использование: /admin access <code>username</code> [revoke или status]")
            return
        username = args[1]
        action = args[2].lower() if len(args) > 2 else "status"
        
        user_row = await fetchrow("SELECT * FROM users WHERE username=$1", username.lstrip("@"))
        if not user_row:
            await message.answer("Пользователь не найден.")
            return
        
        if action == "revoke":
            await execute(
                "UPDATE users SET status='member_expired', access_until=NULL, updated_at=NOW() WHERE id=$1",
                user_row["id"]
            )
            
            await log_admin_action(
                message.from_user.id,
                "revoke_access",
                {"user_id": user_row["id"]}
            )
            
            await message.answer(f"Доступ пользователя @{username} отозван.")
            
            try:
                await message.bot.send_message(
                    user_row["tg_user_id"],
                    "Твой доступ в клуб был приостановлен\n\n"
                    "Для выяснения причин обратитесь в поддержку: " + SUPPORT_CONTACT
                )
            except Exception:
                pass
                
        elif action == "status":
            status = user_row.get("status", "unknown")
            access_until = user_row.get("access_until", "—")
            if access_until != "—":
                access_until = tz_aware_msk(access_until)
            
            await message.answer(
                f"Статус пользователя @{username}\n\n"
                f"• Статус: {status}\n"
                f"• Доступ до: {access_until}"
            )
        else:
            await message.answer("Неизвестное действие. Используйте revoke или status.")
        return
    
    elif sub == "bind":
        if len(args) < 2:
            await message.answer("Использование: /admin bind <code>username или tg_id</code> email=<code>email</code> phone=<code>phone</code>")
            return
        target = args[1]
        kv = {}
        for pair in args[2:]:
            if "=" in pair:
                k, v = pair.split("=", 1)
                kv[k.strip().lower()] = v.strip()
        
        email = kv.get("email")
        phone = kv.get("phone")
        user_row = None
        
        if target.startswith("@"):
            user_row = await fetchrow("SELECT * FROM users WHERE username=$1", target[1:])
        else:
            try:
                tg_id = int(target)
            except ValueError:
                await message.answer("tg_id должен быть числом.")
                return
            user_row = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_id)
        
        if not user_row:
            await message.answer("Пользователь не найден.")
            return
        
        sets = []
        params = [user_row["id"]]
        if email:
            if not validate_email(email):
                await message.answer("email невалиден.")
                return
            sets.append("email=$2")
            params.append(email)
        if phone:
            phone = normalize_phone(phone)
            if not validate_phone(phone):
                await message.answer("phone невалиден.")
                return
            if not email:
                sets.append("phone=$2")
            else:
                sets.append("phone=$3")
            params.append(phone)
        if not sets:
            await message.answer("Нечего привязывать. Укажи email=... и/или phone=...")
            return
        
        sql = f"UPDATE users SET {', '.join(sets)}, updated_at=NOW() WHERE id=$1"
        await execute(sql, *params)
        
        await log_admin_action(
            message.from_user.id,
            "bind_contacts",
            {
                "user_id": user_row["id"],
                "email": email,
                "phone": phone
            }
        )
        
        await message.answer("Ок, контакты привязаны")
        return
    
    elif sub == "run" and args[1] == "job":
        if len(args) < 3:
            await message.answer("Использование: /admin run job <code>job_name</code>")
            return
        job_name = args[2]
        
        await message.answer(f"Запускаю джобу: {job_name}")
        logger.info(f"Admin {message.from_user.id} manually triggered job: {job_name}")
        
        if job_name == "daily_lessons":
            await message.answer("Джоба daily_lessons выполнена")
        elif job_name == "soft_reminders":
            await message.answer("Джоба soft_reminders выполнена")
        elif job_name == "access_expiry":
            await message.answer("Джоба access_expiry выполнена")
        else:
            await message.answer(f"Неизвестная джоба: {job_name}")
        return
    
    await message.answer("Неизвестная команда. Справка: /admin")
# ──────────────────────────────────────────────────────────────────────────────
# Админ-CRUD контента
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("content_keys"))
async def cmd_content_keys(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    
    db_keys = await list_content_keys_db()
    y_keys = list(_flatten_yaml_keys(_load_yaml_content()))
    text = (
        "Контентные ключи\n\n"
        f"В БД ({len(db_keys)}): " + (", ".join(db_keys) if db_keys else "—") + "\n\n"
        f"В YAML ({len(y_keys)}): " + (", ".join(y_keys[:80]) + (" …" if len(y_keys) > 80 else ""))
    )
    await message.answer(text)

@router.message(Command("content_get"))
async def cmd_content_get(message: types.Message, command: CommandObject):
    if not is_admin_id(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("Использование: /content_get <code>key</code>")
        return
    
    key = command.args.strip()
    val = await get_content(key, default="(пусто)")
    if len(val) > 3500:
        val = val[:3500] + " …"
    await message.answer(f"{key}\n\n{val}")

@router.message(Command("content_set"))
async def cmd_content_set(message: types.Message, command: CommandObject):
    if not is_admin_id(message.from_user.id):
        return
    
    if not command.args:
        await message.answer("Использование: /content_set <code>key</code>\nТекст укажи ответом (reply) на это сообщение.")
        return
    
    key = command.args.strip()
    if not message.reply_to_message or not (message.reply_to_message.text or message.reply_to_message.caption):
        await message.answer("Пришли новый текст ответом (reply) на команду /content_set <key>.")
        return
    
    source_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    new_text = prepare_admin_text_input(source_text)
    await set_content_value(key, new_text, updated_by=message.from_user.id)
    
    await log_admin_action(
        message.from_user.id,
        "content_set",
        {"key": key, "length": len(new_text)}
    )
    
    await message.answer(f"Сохранено! key=<code>{key}</code> len={len(new_text)}")
# ──────────────────────────────────────────────────────────────────────────────
# Админ-рассылки
# ──────────────────────────────────────────────────────────────────────────────
async def _select_segment_users(segment: str) -> list[dict]:
    segment = (segment or "").lower().strip()
    base_query = "SELECT tg_user_id, name, full_name, username FROM users"
    if segment == "all":
        rows = await fetch(base_query)
    elif segment == "lead_funnel":
        rows = await fetch(f"{base_query} WHERE status='lead_funnel'")
    elif segment in ("member_active", "member"):
        rows = await fetch(
            f"{base_query} WHERE status='member_active' AND (access_until IS NULL OR access_until > NOW())"
        )
    elif segment in ("member_expired", "expired"):
        rows = await fetch(
            f"{base_query} WHERE status='member_expired' OR (access_until IS NOT NULL AND access_until <= NOW())"
        )
    else:
        rows = []
    return [dict(row) for row in rows] if rows else []


async def _broadcast(
    bot,
    users: list[dict],
    text: str,
    *,
    chunk: int = 25,
    pause: float = 0.06,
    parse_mode: ParseMode | None = ParseMode.HTML,
) -> tuple[int, int]:
    ok = fail = 0
    backoff = 1

    safe_text = text or ""

    for i in range(0, len(users), chunk):
        for user in users[i:i + chunk]:
            tg_id = user.get("tg_user_id") if isinstance(user, dict) else None
            if not tg_id:
                continue
            display_name = (
                (user.get("name") if isinstance(user, dict) else None)
                or (user.get("full_name") if isinstance(user, dict) else None)
                or (user.get("username") if isinstance(user, dict) else None)
                or "друг"
            )
            message_text = render_content(
                safe_text,
                name=display_name,
                NAME=display_name,
                support=SUPPORT_CONTACT,
                SUPPORT_CONTACT=SUPPORT_CONTACT,
                support_contact=SUPPORT_CONTACT,
            )
            try:
                await bot.send_message(
                    tg_id,
                    message_text,
                    parse_mode=parse_mode if parse_mode else None,
                    disable_web_page_preview=True,
                )
                ok += 1
            except TelegramRetryAfter as e:
                logger.warning(f"Rate limit hit, waiting {e.retry_after} seconds")
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.send_message(
                        tg_id,
                        message_text,
                        parse_mode=parse_mode if parse_mode else None,
                        disable_web_page_preview=True,
                    )
                    ok += 1
                except Exception as e:
                    fail += 1
                    logger.warning(f"broadcast fail uid=%s err=%s", tg_id, e)
            except Exception as e:
                fail += 1
                logger.warning(f"broadcast fail uid=%s err=%s", tg_id, e)

        await asyncio.sleep(pause * backoff)
        backoff = min(backoff * 1.5, 5)

    return ok, fail


async def _broadcast_preview(
    message: types.Message,
    state: FSMContext,
    *,
    segment: str,
    body: str,
    template_title: str | None = None,
) -> None:
    users = await _select_segment_users(segment)
    recipients = [u for u in users if u.get("tg_user_id")]
    sample_name = (
        message.from_user.full_name
        or message.from_user.first_name
        or "подруга"
    )
    preview = render_content(
        body,
        name=sample_name,
        NAME=sample_name,
        support=SUPPORT_CONTACT,
        SUPPORT_CONTACT=SUPPORT_CONTACT,
        support_contact=SUPPORT_CONTACT,
    )

    await message.answer(
        preview,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

    segment_label = _BROADCAST_SEGMENT_LABELS.get(segment, segment)
    lines = ["<b>Проверь рассылку</b>"]
    if template_title:
        lines.append(f"Шаблон: <b>{html.escape(template_title)}</b>")
    lines.extend(
        [
            "",
            f"Сегмент: <code>{segment_label}</code>",
            f"Получателей сейчас: {len(recipients)}",
            "",
            "Если всё верно — нажми «🚀 Отправить». Можно изменить текст, сегмент или сохранить шаблон.",
        ]
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=admin_broadcast_confirm_keyboard(include_change_segment=True),
        disable_web_page_preview=True,
    )

    await state.update_data(
        segment=segment,
        body=body,
        recipients=len(recipients),
        interactive=True,
        template_title=template_title,
        change_segment=False,
    )

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return

    if not command.args:
        await message.answer(
            "Рассылка пользователям\n\n"
            "Использование: /broadcast <code>segment</code> [--html]\n\n"
            "Сегменты: all, lead_funnel, member_active, member_expired, expired\n\n"
            "Текст пришли ответом (reply) на эту команду.\n"
            "Подсказка: в админке есть кнопка «📢 Рассылка» с мастером и шаблонами."
        )
        return

    args = command.args.strip().split()
    segment = args[0].lower()
    use_html = "--html" in args

    if segment not in {"all", "lead_funnel", "member_active", "member_expired", "expired"}:
        await message.answer("Неизвестный сегмент. Разрешены: all, lead_funnel, member_active, member_expired, expired")
        return

    if not message.reply_to_message or not (message.reply_to_message.text or message.reply_to_message.caption):
        await state.set_state(BroadcastStates.waiting_body)
        await state.update_data(segment=segment, use_html=use_html, interactive=False)
        await message.answer(
            f"Отправь текст рассылки\n\n"
            f"Сегмент: <code>{segment}</code>\n"
            f"HTML: {'Да' if use_html else 'Нет'}\n\n"
            "Пришли текст рассылки одним сообщением (это сообщение должно быть ответом на твою команду)."
        )
        return

    body_source = message.reply_to_message.text or message.reply_to_message.caption or ""
    body = body_source if use_html else sanitize_html(body_source)
    users = await _select_segment_users(segment)
    await message.answer(
        f"Стартую рассылку по сегменту <b>{segment}</b>, получателей: {len(users)}…",
        disable_web_page_preview=True,
    )

    ok, fail = await _broadcast(
        message.bot,
        users,
        body,
        parse_mode=ParseMode.HTML,
    )

    await log_admin_action(
        message.from_user.id,
        "broadcast",
        {
            "segment": segment,
            "recipients": len(users),
            "ok": ok,
            "fail": fail,
            "use_html": use_html,
        },
    )

    await message.answer(
        f"Готово! доставлено: {ok}, ошибок: {fail}",
        disable_web_page_preview=True,
    )


@router.message(BroadcastStates.waiting_body, F.text.len() > 0)
async def broadcast_receive_body(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    segment = data.get("segment", "all")
    interactive = data.get("interactive", False)
    body_text = (message.text or "").strip()

    if interactive:
        sanitized = sanitize_html(body_text)
        template_title = data.get("template_title")
        await _broadcast_preview(
            message,
            state,
            segment=segment,
            body=sanitized,
            template_title=template_title,
        )
        await state.set_state(BroadcastStates.waiting_confirm)
        return

    use_html = data.get("use_html", False)
    prepared_text = body_text if use_html else sanitize_html(body_text)
    users = await _select_segment_users(segment)

    await message.answer(
        f"Стартую рассылку по сегменту <b>{segment}</b>, получателей: {len(users)}…",
        disable_web_page_preview=True,
    )

    ok, fail = await _broadcast(
        message.bot,
        users,
        prepared_text,
        parse_mode=ParseMode.HTML,
    )

    await log_admin_action(
        message.from_user.id,
        "broadcast",
        {
            "segment": segment,
            "recipients": len(users),
            "ok": ok,
            "fail": fail,
            "use_html": use_html,
        },
    )

    await message.answer(
        f"Готово! доставлено: {ok}, ошибок: {fail}",
        disable_web_page_preview=True,
    )
    await state.clear()


@router.message(BroadcastStates.waiting_confirm, F.text == SEND_BROADCAST_BUTTON)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    segment = data.get("segment", "all")
    body = (data or {}).get("body")
    if not body:
        await message.answer("Нет текста для отправки. Пришли сообщение заново.")
        await state.set_state(BroadcastStates.waiting_body)
        await state.update_data(interactive=True)
        return

    users = await _select_segment_users(segment)
    await message.answer(
        f"Отправляю рассылку. Получателей: {len(users)}…",
        disable_web_page_preview=True,
    )
    ok, fail = await _broadcast(
        message.bot,
        users,
        body,
        parse_mode=ParseMode.HTML,
    )

    await log_admin_action(
        message.from_user.id,
        "broadcast",
        {
            "segment": segment,
            "recipients": len(users),
            "ok": ok,
            "fail": fail,
            "template": data.get("template_title"),
        },
    )

    await message.answer(
        f"Готово! доставлено: {ok}, ошибок: {fail}",
        disable_web_page_preview=True,
    )
    await state.clear()
    await send_admin_broadcast_menu(message)


@router.message(BroadcastStates.waiting_confirm, F.text == EDIT_BROADCAST_BUTTON)
async def admin_broadcast_edit(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    segment = data.get("segment", "all")
    await state.set_state(BroadcastStates.waiting_body)
    await state.update_data(interactive=True, segment=segment)
    await message.answer(
        "Пришли новый текст рассылки одним сообщением.",
        reply_markup=cancel_keyboard(),
    )


@router.message(BroadcastStates.waiting_confirm, F.text == SAVE_BROADCAST_TEMPLATE_BUTTON)
async def admin_broadcast_save_template_prompt(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    if not (data or {}).get("body"):
        await message.answer("Нет текста для сохранения. Сначала напиши сообщение.")
        return

    await state.set_state(BroadcastStates.waiting_template_title)
    await message.answer(
        "Как назвать шаблон? Отправь короткое название (до 60 символов).",
        reply_markup=cancel_keyboard(),
    )


@router.message(BroadcastStates.waiting_confirm, F.text == CHANGE_BROADCAST_SEGMENT_BUTTON)
async def admin_broadcast_change_segment(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return
    await state.set_state(BroadcastStates.waiting_segment)
    await state.update_data(change_segment=True)
    await message.answer(
        "Выбери новый сегмент для рассылки.",
        reply_markup=admin_broadcast_keyboard(),
    )


@router.message(BroadcastStates.waiting_template_title, F.text.len() > 0)
async def admin_broadcast_save_template(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("Название слишком короткое. Попробуй ещё раз.", reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    segment = data.get("segment", "all")
    body = data.get("body", "")
    template = await upsert_broadcast_template(title, segment, body)
    await log_admin_action(
        message.from_user.id,
        "broadcast_template_save",
        {"title": template["title"], "segment": segment},
    )

    await state.set_state(BroadcastStates.waiting_confirm)
    await state.update_data(template_title=template["title"])
    await message.answer(
        "Шаблон сохранён ✅",
        reply_markup=admin_broadcast_confirm_keyboard(include_change_segment=True),
        disable_web_page_preview=True,
    )
# ──────────────────────────────────────────────────────────────────────────────
# Диагностика
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("debug"))
async def cmd_debug(message: types.Message, command: CommandObject):
    if not is_admin_id(message.from_user.id):
        return
    
    if not command.args:
        await message.answer(
            "Диагностика\n\n"
            "Доступные команды:\n"
            "/debug config — показать конфигурацию\n"
            "/debug ping — проверить работу бота\n"
            "/debug stats — статистика"
        )
        return
    
    subcommand = command.args.strip().lower()
    
    if subcommand == "config":
        config_text = (
            "Конфигурация бота\n\n"
            f"Версия: {BOT_VERSION}\n"
            f"Часовой пояс: {BOT_TIMEZONE}\n"
            f"Поддержка: {SUPPORT_CONTACT}\n"
            f"Продукт ID: {AT_PRODUCT_ID_CLUB or 'Не задан'}\n"
            f"Чат клуба: {CLUB_CHAT_ID or 'Не задан'}"
        )
        await message.answer(config_text)
    
    elif subcommand == "ping":
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        msk_time = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M:%S MSK")
        
        ping_text = (
            f"Pong!\n\n"
            f"Время сервера: {current_time}\n"
            f"Время MSK: {msk_time}\n"
            f"Версия бота: {BOT_VERSION}"
        )
        await message.answer(ping_text)
    
    elif subcommand == "stats":
        users_count = (await fetchrow("SELECT COUNT(*) as count FROM users"))["count"]
        active_users = (await fetchrow("SELECT COUNT(*) as count FROM users WHERE status='member_active' AND access_until > NOW()"))["count"]
        lessons_completed = (await fetchrow("SELECT COUNT(*) as count FROM funnel_progress WHERE hw_status='submitted'"))["count"]
        feedback_count = (await fetchrow("SELECT COUNT(*) as count FROM lesson_feedback"))["count"]
        
        stats_text = (
            f"Статистика\n\n"
            f"Всего пользователей: {users_count}\n"
            f"Активных участников: {active_users}\n"
            f"Выполнено уроков: {lessons_completed}\n"
            f"Оставлено отзывов: {feedback_count}"
        )
        await message.answer(stats_text)
    
    else:
        await message.answer("Неизвестная команда. Используйте /debug для списка команд.")


# ──────────────────────────────────────────────────────────────────────────────
# Fallback — должен регистрироваться последним
# ──────────────────────────────────────────────────────────────────────────────
@router.message(
    ~F.via_bot,
    F.text,
    ~F.text.startswith("/"),
    F.text.func(lambda text: text.strip().lower() != "отмена"),
)
async def fallback(message: types.Message, state: FSMContext):
    """Отвечает на произвольный текст, если не сработал ни один другой хэндлер."""

    cur = await state.get_state()
    if cur in (
        HWStates.waiting_answer,
        HWStates.waiting_feedback,
        RegistrationStates.waiting_name,
        RegistrationStates.waiting_email,
        RegistrationStates.waiting_phone,
        ProfileStates.waiting_email,
        ProfileStates.waiting_phone,
        AdminContentStates.waiting_value,
        AdminContentStates.waiting_custom_key,
        AdminContentStates.waiting_custom_value,
        AdminContentStates.waiting_view_key,
        AdminContentStates.waiting_history_key,
        AdminContentStates.waiting_history_choice,
        AdminContentStates.waiting_import_file,
    ):
        return

    await message.answer("Используй кнопки меню ниже. Если клавиатура пропала — набери /start.")
