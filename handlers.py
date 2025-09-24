# handlers.py
import asyncio
import os
import re
import yaml
import logging
import time
import html
from datetime import datetime, timedelta, timezone
from typing import Optional, Iterable, Dict, List, Callable, Awaitable
from aiogram import Router, F, types
from aiogram.types import ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.utils.chat_action import ChatActionSender
from aiogram.exceptions import TelegramRetryAfter
from urllib.parse import parse_qs
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from db import fetchrow, fetch, execute
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
    admin_text_groups_keyboard,
    admin_text_items_keyboard,
    BACK_TO_MAIN,
    BACK_TO_LEARNING,
    BACK_TO_ADMIN,
    BACK_TO_TEXT_GROUPS,
    BACK_TO_LESSONS,
    LESSON_DONE,
    LESSON_SKIP,
    LESSON_QUESTION,
    NEXT_LESSON,
    WRITE_FEEDBACK,
    SKIP_FEEDBACK,
    FEEDBACK_OPTIONS,
    CANCEL_TEXT,
    ADMIN_TEXTS_ENTRY,
)
# ──────────────────────────────────────────────────────────────────────────────
# Логгер
# ──────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger("handlers")
# ──────────────────────────────────────────────────────────────────────────────
# Конфиг из окружения
# ──────────────────────────────────────────────────────────────────────────────
BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Europe/Moscow")
WELCOME_POST_URL = os.getenv("WELCOME_POST_URL", "https://t.me/")
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@Tokyo_tokyo")
AT_PRODUCT_ID_CLUB = os.getenv("AT_PRODUCT_ID_CLUB", "")
CLUB_CHAT_ID = os.getenv("CLUB_CHAT_ID", "")  # ID приватной группы/канала (опц.)
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",") if os.getenv("ADMIN_IDS") else []
BOT_VERSION = "1.0.0"


def is_admin_id(user_id: int | str | None) -> bool:
    if user_id is None:
        return False
    try:
        uid_str = str(int(user_id))
    except (ValueError, TypeError):
        uid_str = str(user_id)
    return uid_str in ADMIN_IDS
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
# ──────────────────────────────────────────────────────────────────────────────
# Контент: content.yaml + БД content (fallback-логика)
# ──────────────────────────────────────────────────────────────────────────────
_CONTENT_CACHE: dict = {}
_CONTENT_FILE = os.path.join(os.path.dirname(__file__), "content.yaml")
_CONTENT_DB_CACHE: Dict[str, str] = {}
_CONTENT_LAST_RELOAD = None
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
async def get_content(key: str, default: str = "") -> str:
    """
    1) Пытаемся достать из БД content.value по key.
    2) Если нет — из content.yaml (поддержка вложенных ключей "onboarding.0").
    """
    # Проверяем кэш БД сначала
    if key in _CONTENT_DB_CACHE:
        return _CONTENT_DB_CACHE[key]
    
    # Если нет в кэше, проверяем БД
    row = await fetchrow("SELECT value FROM content WHERE key=$1", key)
    if row and row.get("value"):
        _CONTENT_DB_CACHE[key] = row["value"]
        return row["value"]
    # Fallback to YAML
    y = _load_yaml_content()
    if "." in key:
        cur = y
        try:
            for part in key.split("."):
                if part.isdigit():
                    cur = cur[int(part)]
                else:
                    cur = cur[part]
            if isinstance(cur, (list, dict)):
                return yaml.safe_dump(cur, allow_unicode=True)
            return str(cur)
        except Exception:
            return default
    return str(y.get(key, default))
async def set_content_value(key: str, value: str) -> None:
    """
    Upsert контента в таблицу content.
    Если нет уникального индекса по key — используем UPDATE → INSERT.
    """
    # Очищаем HTML перед сохранением
    value = sanitize_html(value)
    
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
async def list_content_keys_db() -> list[str]:
    rows = await fetch("SELECT key FROM content ORDER BY key ASC")
    return [r["key"] for r in rows] if rows else []
def _flatten_yaml_keys(src: dict, prefix: str = "") -> Iterable[str]:
    for k, v in (src or {}).items():
        full = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            yield from _flatten_yaml_keys(v, full)
        else:
            yield full
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
    waiting_body = State()    # ждём текст рассылки ({"segment": str})
class ProfileStates(StatesGroup):
    waiting_email = State()
    waiting_phone = State()


class AdminContentStates(StatesGroup):
    waiting_value = State()
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
    "show_weekly_materials": True,
    "show_schedule": True,
}

_ADMIN_SETTINGS_LABELS: dict[str, str] = {
    "payments_open": "Окно оплаты",
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
        ("Окно «Поддержка»", "menu.support"),
    ],
}

_ADMIN_TEXT_PLACEHOLDERS: dict[str, list[str]] = {
    "menu.start": ["{name}", "{{NAME}}"],
    "menu.registration_complete": ["{name}", "{{NAME}}"],
    "menu.pay": ["{checkout_url}", "{{CHECKOUT_URL}}"],
    "menu.support": ["{support}", "{{SUPPORT_CONTACT}}"],
}


def _admin_text_labels(group_title: str) -> list[str]:
    entries = _ADMIN_TEXT_GROUPS.get(group_title, [])
    return [label for label, _ in entries]


def _admin_find_text_entry(label: str) -> tuple[Optional[str], Optional[str]]:
    for group_title, entries in _ADMIN_TEXT_GROUPS.items():
        for entry_label, key in entries:
            if entry_label == label:
                return group_title, key
    return None, None


async def get_bool_setting(key: str, default: bool = True) -> bool:
    raw_value = await get_content(f"settings.{key}", "true" if default else "false")
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "y", "да"}:
        return True
    if normalized in {"0", "false", "no", "off", "n", "нет"}:
        return False
    return default


async def set_bool_setting(key: str, value: bool) -> None:
    await set_content_value(f"settings.{key}", "true" if value else "false")


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
        "CODE: Магнетизм — закрытое пространство для тех, кто хочет:\n\n"
        "- Управлять вниманием, мыслями и эмоциями\n"
        "- Укрепить уверенность и личный магнетизм\n"
        "- Изменить сценарии в отношениях и деньгах\n\n"
        "Внутри тебя ждут:\n"
        "- Подкасты и практики\n"
        "- Челленджи и разборы\n"
        "- Структурная система развития\n\n"
        "Готова присоединиться? Оформи доступ в меню.",
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
        "FAQ.\n\n"
        "Как получить доступ? — Оформи участие в разделе «Оплата».\n\n"
        "Как проходят уроки? — Видеоуроки + практики, доступ через меню.\n\n"
        f"Как задать вопрос? — Кнопка «Вопрос» в уроке или {SUPPORT_CONTACT}.\n\n"
        "Как продлить доступ? — Раздел «Оплата».",
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
        "Правила CODE: Магнетизм.\n\n"
        "1. Уважение к участникам.\n"
        "2. Только полезный контент.\n"
        "3. Без спама и рекламы.\n"
        "4. Конфиденциальность.\n"
        "5. Без оскорблений и дискриминации.\n\n"
        "Нарушение = блокировка доступа.",
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
    analysis_text = await get_content(
        "menu.analysis",
        "Персональный разбор.\n\n"
        "Заполни форму → мы назначим время.\n\n"
        "https://forms.example.com/analysis",
    )

    await answer_with_main_menu(
        message,
        user,
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
) -> None:
    test_text = await get_content(
        "menu.test",
        "Тест: определение уровня.\n\n"
        "Ссылка: https://forms.example.com/test\n\n"
        "После теста ты получишь анализ, рекомендации и сможешь записаться на разбор.",
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        test_text,
        section="learning",
        from_callback=from_callback,
    )


async def send_support_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    support_template = await get_content(
        "menu.support",
        "Поддержка.\n\n"
        "Если есть вопросы или сложности — пиши сюда: {support}. Мы отвечаем лично и максимально быстро.",
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
            "Материалы недели доступны участницам клуба.\n\n"
            "Оформи доступ в разделе «Оплатить доступ», и бот пришлёт ссылку.",
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
        "📚 Материалы недели:\n"
        "• Подкаст: [ссылка]\n"
        "• Практика: [ссылка]\n"
        "• Челлендж: [описание]\n"
        "• Дневник: [шаблон]",
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
            "Расписание доступно участницам клуба.\n\n"
            "Активируй доступ — и бот пришлёт ближайшие эфиры.",
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
        "🗓️ Расписание эфиров:\n"
        "• Понедельник 20:00 — Вводный эфир\n"
        "• Четверг 19:00 — Практика в группе\n"
        "• Воскресенье 18:00 — Подведение итогов",
    )

    await answer_with_main_menu(
        message,
        user_row,
        is_admin,
        schedule_text,
        section="materials",
        from_callback=from_callback,
    )


async def send_progress_section(
    message: types.Message,
    user: dict,
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    rows = await fetch(
        "SELECT lesson_num, hw_status FROM funnel_progress WHERE user_id=$1 ORDER BY lesson_num",
        user["id"],
    )

    status_map = {r["lesson_num"]: r["hw_status"] for r in rows} if rows else {}

    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции",
    }

    status_texts = {
        "submitted": "Выполнено",
        "skipped": "Пропущено",
        "pending": "В процессе",
    }

    progress_lines = ["Мой прогресс.\n"]
    for i in range(1, 5):
        st = status_map.get(i, "—")
        human_status = status_texts.get(st, "Не начато")
        progress_lines.append(f"Урок {i}: {lesson_titles.get(i, f'Урок {i}')} — {human_status}")

    completed = sum(1 for st in status_map.values() if st == "submitted")
    if completed == 0:
        progress_lines.append("\nНачни с первого урока.")
    elif completed < 4:
        progress_lines.append(f"\nПройдено {completed} из 4 уроков.")
    else:
        progress_lines.append("\nВсе уроки завершены. Пора на следующий уровень.")

    progress_text = "\n".join(progress_lines)

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        progress_text,
        section="learning",
        from_callback=from_callback,
    )


async def send_pay_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    if not AT_PRODUCT_ID_CLUB:
        await answer_with_main_menu(
            message,
            user,
            is_admin,
            "Сейчас доступ в клуб бесплатный.",
            section="root",
            from_callback=from_callback,
        )
        return

    payments_open = await get_bool_setting(
        "payments_open", _ADMIN_SETTINGS_DEFAULTS["payments_open"]
    )
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

    url = f"https://antitraining.example/checkout/{AT_PRODUCT_ID_CLUB}"
    pay_template = await get_content(
        "menu.pay",
        "Доступ в клуб CODE: Магнетизм.\n\n"
        "Тариф: Полный доступ — 2690₽ (единовременно).\n\n"
        "Ссылка на оплату: {checkout_url}\n\n"
        "После оплаты бот автоматически активирует доступ.",
    )
    pay_text = render_content(
        pay_template,
        checkout_url=url,
        CHECKOUT_URL=url,
    )

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
            "Все уроки пройдены.\n\n"
            "Дальше — клуб CODE: Магнетизм: углублённые практики, сообщество, живые эфиры.",
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
        "Админ-панель\n\n"
        "Выберите действие:"
    )
    await message.answer(admin_text, reply_markup=admin_main_keyboard())


async def send_admin_settings(
    message: types.Message,
    *,
    from_callback: bool = False,
) -> None:
    flags = await get_menu_flags()
    text = (
        "Тонкие настройки бота\n\n"
        f"Окно оплаты: {'открыто' if flags.get('payments_open', True) else 'закрыто'}\n"
        f"Материалы недели: {'доступны' if flags.get('show_weekly_materials', True) else 'скрыты'}\n"
        f"Расписание: {'показывается' if flags.get('show_schedule', True) else 'скрыто'}\n\n"
        "Используй кнопки ниже, чтобы включать и выключать опции или перейти к редактору текстов."
    )
    keyboard = admin_settings_keyboard(flags, _ADMIN_SETTINGS_LABELS)

    await message.answer(text, reply_markup=keyboard)


async def send_admin_text_groups(message: types.Message) -> None:
    text = (
        "Редактор текстов бота\n\n"
        "Выбери раздел, в котором нужно изменить тексты."
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
        f"Группа «{group_title}».\n\n"
        "Выбери текст, который нужно обновить."
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
        if access_until and access_until > now_utc():
            return True
        # Если срок доступа истек, обновляем статус
        if access_until and access_until <= now_utc():
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
    is_admin = str(message.from_user.id) in ADMIN_IDS
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
    is_admin = str(message.from_user.id) in ADMIN_IDS

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

# Fallback — если не матчится ни на один хэндлер (и не мешаем FSM)
@router.message(
    ~F.via_bot,
    F.text,
    ~F.text.startswith("/"),
    F.text.func(lambda text: text.strip().lower() != "отмена"),
)
async def fallback(message: types.Message, state: FSMContext):
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
    ):
        return
    await message.answer("Используй кнопки меню ниже. Если клавиатура пропала — набери /start.")
# ──────────────────────────────────────────────────────────────────────────────
# Меню
# ──────────────────────────────────────────────────────────────────────────────
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
    is_admin = str(message.from_user.id) in ADMIN_IDS
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
    is_admin = str(message.from_user.id) in ADMIN_IDS
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

    is_admin = str(message.from_user.id) in ADMIN_IDS
    user = await get_user_with_id(message.from_user.id)
    await message.answer(
        f"Поддержка.\n\n"
        f"Если есть вопросы или сложности — пиши сюда: {SUPPORT_CONTACT}. Мы отвечаем лично и максимально быстро.",
        reply_markup=await build_menu_keyboard(user=user, is_admin=is_admin, section="root"),
    )

@router.message(Command("id"))
async def cmd_id(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else "—"
    is_admin = str(message.from_user.id) in ADMIN_IDS
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
    is_admin = str(message.from_user.id) in ADMIN_IDS
    await send_profile_overview(message, user, is_admin)


@router.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    is_admin = str(message.from_user.id) in ADMIN_IDS
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
# Поддержка и помощь
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("support"))
async def cmd_support(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    is_admin = str(message.from_user.id) in ADMIN_IDS
    user = await get_user_with_id(message.from_user.id)
    await message.answer(
        f"Поддержка.\n\n"
        f"Если есть вопросы или сложности — пиши сюда: {SUPPORT_CONTACT}. Мы отвечаем лично и максимально быстро.",
        reply_markup=await build_menu_keyboard(user=user, is_admin=is_admin, section="root"),
    )

@router.message(Command("id"))
async def cmd_id(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else "—"
    is_admin = str(message.from_user.id) in ADMIN_IDS
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
    is_admin = str(message.from_user.id) in ADMIN_IDS
    await send_profile_overview(message, user, is_admin)


@router.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)

    is_admin = str(message.from_user.id) in ADMIN_IDS
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
    return user, str(message.from_user.id) in ADMIN_IDS


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
    is_admin = str(message.from_user.id) in ADMIN_IDS
    await send_funnel_section(message, user, is_admin)


@router.message(F.text == "Мой прогресс")
async def menu_progress(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user = await get_user_with_id(message.from_user.id)
    is_admin = str(message.from_user.id) in ADMIN_IDS
    if not user:
        await message.answer("Перезапусти /start, чтобы загрузить профиль.")
        return
    await send_progress_section(message, user, is_admin)


@router.message(F.text == "Записаться на разбор")
async def menu_analysis(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_analysis_section(message, user, is_admin)


@router.message(F.text == "Пройти тест")
async def menu_test(message: types.Message, state: FSMContext):
    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    await send_test_section(message, user, is_admin)


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
    is_admin = str(message.from_user.id) in ADMIN_IDS
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
        is_admin=str(message.from_user.id) in ADMIN_IDS,
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


@router.message(F.text == "Управление пользователями")
async def admin_users_help(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    text = (
        "Управление пользователями\n\n"
        "Команды:\n"
        "/admin user <code>username или tg_id</code> — информация о пользователе\n"
        "/admin set_paid <code>username</code> [days или YYYY-MM-DD] — установить оплату\n"
        "/admin bind <code>username или tg_id</code> email=<code>email</code> phone=<code>phone</code> — привязать контакты\n"
        "/admin access <code>username</code> [revoke или status] — управление доступом"
    )
    await message.answer(text, reply_markup=admin_main_keyboard())


@router.message(F.text == "Рассылка")
async def admin_broadcast_help(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    text = (
        "Рассылка\n\n"
        "Команда:\n"
        "/broadcast <code>segment</code> [--html] — рассылка пользователям\n\n"
        "Сегменты: all, lead_funnel, member_active, member_expired, expired"
    )
    await message.answer(text, reply_markup=admin_main_keyboard())


@router.message(F.text == "Управление контентом")
async def admin_content_help(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    text = (
        "Управление контентом\n\n"
        "/content_keys — показать ключи\n"
        "/content_get <code>key</code> — показать текст\n"
        "/content_set <code>key</code> — сохранить текст (ответом)"
    )
    await message.answer(text, reply_markup=admin_main_keyboard())


@router.message(F.text == "Статистика")
async def admin_stats(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    users_count = (await fetchrow("SELECT COUNT(*) as count FROM users"))["count"]
    active_users = (await fetchrow("SELECT COUNT(*) as count FROM users WHERE status='member_active' AND access_until > NOW()"))["count"]
    lessons_completed = (await fetchrow("SELECT COUNT(*) as count FROM funnel_progress WHERE hw_status='submitted'"))["count"]
    feedback_count = (await fetchrow("SELECT COUNT(*) as count FROM lesson_feedback"))["count"]
    stats_text = (
        f"Статистика\n\n"
        f"Всего пользователей: {users_count}\n"
        f"Активных участниц: {active_users}\n"
        f"Выполнено уроков: {lessons_completed}\n"
        f"Оставлено отзывов: {feedback_count}"
    )
    await message.answer(stats_text, reply_markup=admin_main_keyboard())


@router.message(F.text == "Диагностика")
async def admin_debug(message: types.Message):
    if not is_admin_id(message.from_user.id):
        return
    config_text = (
        "Конфигурация бота\n\n"
        f"Версия: {BOT_VERSION}\n"
        f"Часовой пояс: {BOT_TIMEZONE}\n"
        f"Поддержка: {SUPPORT_CONTACT}\n"
        f"Продукт ID: {AT_PRODUCT_ID_CLUB or 'Не задан'}\n"
        f"Чат клуба: {CLUB_CHAT_ID or 'Не задан'}"
    )
    await message.answer(config_text, reply_markup=admin_main_keyboard())


@router.message(F.text == "Тонкие настройки")
async def admin_settings_menu(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    await _reset_state_if_needed(state)
    await send_admin_settings(message)


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
    await state.update_data(content_key=key, content_group=group_title, content_label=message.text)

    current_text = await get_content(key, default="")
    preview = current_text if len(current_text) <= 1500 else current_text[:1500] + "…"

    placeholders = _ADMIN_TEXT_PLACEHOLDERS.get(key, [])
    placeholders_line = ""
    if placeholders:
        placeholders_line = "Плейсхолдеры: " + ", ".join(
            f"<code>{html.escape(token)}</code>" for token in placeholders
        )

    text_lines = [
        f"<b>Редактирование текста:</b> {html.escape(message.text or key)}",
        "",
        "<b>Текущий текст:</b>",
        html.escape(preview) if preview else "(пусто)",
        "",
        "Отправь новый текст одним сообщением.",
        "Допустимы теги: &lt;b&gt;, &lt;i&gt;, &lt;u&gt;, &lt;strong&gt;, &lt;em&gt;, &lt;code&gt;, &lt;a href=&quot;...&quot;&gt;ссылка&lt;/a&gt;.",
    ]

    if placeholders_line:
        text_lines.extend(["", placeholders_line])

    text_lines.append("\nДля отмены нажми «Отмена».")

    await message.answer(
        "\n".join(text_lines),
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
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

    new_text = message.text.strip()
    await set_content_value(key, new_text)
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
    await set_bool_setting(key, new_value)
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
        admin_text = (
            "Админ-панель\n\n"
            "Выберите действие:"
        )
        await message.answer(admin_text, reply_markup=admin_main_keyboard())
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
    
    new_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    await set_content_value(key, new_text)
    
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
    if segment == "all":
        rows = await fetch("SELECT tg_user_id FROM users")
    elif segment == "lead_funnel":
        rows = await fetch("SELECT tg_user_id FROM users WHERE status='lead_funnel'")
    elif segment in ("member_active", "member"):
        rows = await fetch("SELECT tg_user_id FROM users WHERE status='member_active' AND (access_until IS NULL OR access_until > NOW())")
    elif segment in ("member_expired", "expired"):
        rows = await fetch("SELECT tg_user_id FROM users WHERE status='member_expired' OR (access_until IS NOT NULL AND access_until <= NOW())")
    else:
        rows = []
    return rows or []

async def _broadcast(bot, tg_ids: list[int], text: str, chunk: int = 25, pause: float = 0.06) -> tuple[int, int]:
    ok = fail = 0
    backoff = 1
    
    for i in range(0, len(tg_ids), chunk):
        for uid in tg_ids[i:i+chunk]:
            try:
                await bot.send_message(uid, text)
                ok += 1
            except TelegramRetryAfter as e:
                logger.warning(f"Rate limit hit, waiting {e.retry_after} seconds")
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.send_message(uid, text)
                    ok += 1
                except Exception as e:
                    fail += 1
                    logger.warning(f"broadcast fail uid=%s err=%s", uid, e)
            except Exception as e:
                fail += 1
                logger.warning(f"broadcast fail uid=%s err=%s", uid, e)
        
        await asyncio.sleep(pause * backoff)
        backoff = min(backoff * 1.5, 5)
    
    return ok, fail

@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        return
    
    if not command.args:
        await message.answer(
            "Рассылка пользователям\n\n"
            "Использование: /broadcast <code>segment</code> [--html]\n\n"
            "Сегменты: all, lead_funnel, member_active, member_expired, expired\n\n"
            "Текст пришли ответом (reply) на эту команду."
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
        await state.update_data(segment=segment, use_html=use_html)
        await message.answer(
            f"Отправь текст рассылки\n\n"
            f"Сегмент: <code>{segment}</code>\n"
            f"HTML: {'Да' if use_html else 'Нет'}\n\n"
            "Пришли текст рассылки одним сообщением (это сообщение должно быть ответом на твою команду)."
        )
        return
    
    body = message.reply_to_message.text or message.reply_to_message.caption
    rows = await _select_segment_users(segment)
    tg_ids = [r["tg_user_id"] for r in rows if r.get("tg_user_id")]
    
    await message.answer(f"Стартую рассылку по сегменту <b>{segment}</b>, получателей: {len(tg_ids)}…")
    
    ok, fail = await _broadcast(message.bot, tg_ids, body)
    
    await log_admin_action(
        message.from_user.id,
        "broadcast",
        {
            "segment": segment,
            "recipients": len(tg_ids),
            "ok": ok,
            "fail": fail,
            "use_html": use_html
        }
    )
    
    await message.answer(f"Готово! доставлено: {ok}, ошибок: {fail}")

@router.message(BroadcastStates.waiting_body, F.text.len() > 0)
async def broadcast_receive_body(message: types.Message, state: FSMContext):
    if not is_admin_id(message.from_user.id):
        await state.clear()
        return
    
    data = await state.get_data()
    segment = data.get("segment", "all")
    use_html = data.get("use_html", False)
    body = message.text.strip()
    
    rows = await _select_segment_users(segment)
    tg_ids = [r["tg_user_id"] for r in rows if r.get("tg_user_id")]
    
    await message.answer(f"Стартую рассылку по сегменту <b>{segment}</b>, получателей: {len(tg_ids)}…")
    
    ok, fail = await _broadcast(message.bot, tg_ids, body)
    
    await log_admin_action(
        message.from_user.id,
        "broadcast",
        {
            "segment": segment,
            "recipients": len(tg_ids),
            "ok": ok,
            "fail": fail,
            "use_html": use_html
        }
    )
    
    await message.answer(f"Готово! доставлено: {ok}, ошибок: {fail}")
    await state.clear()
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
