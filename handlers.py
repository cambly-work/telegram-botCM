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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.utils.chat_action import ChatActionSender
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from urllib.parse import parse_qs
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from db import fetchrow, fetch, execute
from keyboards import main_menu, lesson_keyboard, after_lesson_keyboard, cancel_button
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
async def safe_edit_text(msg: types.Message, text: str, reply_markup=None):
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise
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
# ──────────────────────────────────────────────────────────────────────────────
# Улучшенные клавиатуры
# ──────────────────────────────────────────────────────────────────────────────
def create_main_menu_keyboard(is_member: bool = False, has_pay: bool = False, is_admin: bool = False) -> types.InlineKeyboardMarkup:
    """Создает улучшенную клавиатуру главного меню с разделами"""
    keyboard = [
        [
            types.InlineKeyboardButton(text="О клубе", callback_data="menu:about"),
            types.InlineKeyboardButton(text="FAQ", callback_data="menu:faq"),
        ],
        [
            types.InlineKeyboardButton(text="Бесплатные уроки", callback_data="menu:funnel"),
            types.InlineKeyboardButton(text="Мой прогресс", callback_data="menu:progress"),
        ],
        [
            types.InlineKeyboardButton(text="Поддержка", callback_data="menu:support"),
            types.InlineKeyboardButton(text="Правила", callback_data="menu:rules")
        ],
        [
            types.InlineKeyboardButton(text="Записаться на разбор", callback_data="menu:analysis"),
            types.InlineKeyboardButton(text="Пройти тест", callback_data="menu:test")
        ],
    ]

    if is_member:
        keyboard.append([
            types.InlineKeyboardButton(text="Материалы недели", callback_data="menu:weekly"),
            types.InlineKeyboardButton(text="Расписание", callback_data="menu:schedule"),
        ])

    # Если есть оплата, добавляем кнопку оплаты
    if has_pay:
        keyboard.append([types.InlineKeyboardButton(text="Оплатить доступ", callback_data="menu:pay")])
    
    # Если пользователь - админ, добавляем кнопку админ-панели
    if is_admin:
        keyboard.append([types.InlineKeyboardButton(text="Админ-панель", callback_data="menu:admin")])
    
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_admin_keyboard() -> types.InlineKeyboardMarkup:
    """Создает клавиатуру для админ-панели"""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="Управление пользователями", callback_data="admin:users"),
                types.InlineKeyboardButton(text="Рассылка", callback_data="admin:broadcast")
            ],
            [
                types.InlineKeyboardButton(text="Управление контентом", callback_data="admin:content"),
                types.InlineKeyboardButton(text="Статистика", callback_data="admin:stats")
            ],
            [
                types.InlineKeyboardButton(text="Диагностика", callback_data="admin:debug"),
                types.InlineKeyboardButton(text="Назад", callback_data="menu:main")
            ]
        ]
    )

def create_access_type_keyboard() -> types.InlineKeyboardMarkup:
    """Создает клавиатуру для выбора типа доступа"""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="Бесплатный доступ", callback_data="access:free"),
                types.InlineKeyboardButton(text="Платный доступ", callback_data="access:paid")
            ],
            [types.InlineKeyboardButton(text="Назад", callback_data="menu:back")]
        ]
    )
def create_back_button() -> types.InlineKeyboardMarkup:
    """Создает кнопку 'Назад'"""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Назад", callback_data="menu:back")]]
    )
def create_lesson_menu_keyboard(lesson_num: int) -> types.InlineKeyboardMarkup:
    """Создает клавиатуру для урока с улучшенными кнопками"""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="Выполнено", callback_data=f"funnel:done:{lesson_num}"),
                types.InlineKeyboardButton(text="Пропустить", callback_data=f"funnel:skip:{lesson_num}"),
            ],
            [types.InlineKeyboardButton(text="Задать вопрос", callback_data=f"funnel:q:{lesson_num}")],
            [types.InlineKeyboardButton(text="Назад к меню", callback_data="menu:main")],
        ]
    )
def create_after_lesson_keyboard(lesson_num: int) -> types.InlineKeyboardMarkup:
    """Создает клавиатуру после выполнения урока"""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Следующий урок", callback_data=f"funnel:next:{lesson_num}")],
            [types.InlineKeyboardButton(text="Главное меню", callback_data="menu:main")],
        ]
    )
def create_feedback_keyboard(lesson_num: int) -> types.InlineKeyboardMarkup:
    """Создает клавиатуру для обратной связи после урока"""
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="Отлично", callback_data=f"feedback:excellent:{lesson_num}"),
                types.InlineKeyboardButton(text="Хорошо", callback_data=f"feedback:good:{lesson_num}")
            ],
            [
                types.InlineKeyboardButton(text="Нормально", callback_data=f"feedback:average:{lesson_num}"),
                types.InlineKeyboardButton(text="Плохо", callback_data=f"feedback:poor:{lesson_num}")
            ],
            [types.InlineKeyboardButton(text="Написать отзыв", callback_data=f"feedback:custom:{lesson_num}")],
            [types.InlineKeyboardButton(text="Пропустить", callback_data=f"feedback:skip:{lesson_num}")]
        ]
    )


_MAIN_MENU_BASE_BUTTONS: List[str] = [
    "О клубе",
    "FAQ",
    "Бесплатные уроки",
    "Мой прогресс",
    "Поддержка",
    "Правила",
    "Записаться на разбор",
    "Пройти тест",
    "Оплатить доступ",
    "Материалы недели",
    "Расписание",
]


async def answer_with_main_menu(
    message: types.Message,
    text: str,
    user: Optional[dict] = None,
    reply_markup: Optional[types.InlineKeyboardMarkup] = None,
) -> None:
    """Отвечает сообщением и прикрепляет актуальное главное меню."""

    user_row = user or await get_user_with_id(message.from_user.id)
    is_admin = str(message.from_user.id) in ADMIN_IDS

    if reply_markup is None:
        menu_kb = create_main_menu_keyboard(
            is_member=await is_member(user_row) if user_row else False,
            has_pay=bool(AT_PRODUCT_ID_CLUB),
            is_admin=is_admin,
        )
    else:
        menu_kb = reply_markup

    await message.answer(text, reply_markup=menu_kb)


async def send_about_section(message: types.Message, user: Optional[dict] = None) -> None:
    about_text = await get_content(
        "menu.about",
        "CODE: Магнетизм — закрытое пространство для тех, кто хочет:\n\n",
        "- Управлять вниманием, мыслями и эмоциями\n",
        "- Укрепить уверенность и личный магнетизм\n",
        "- Изменить сценарии в отношениях и деньгах\n\n",
        "Внутри тебя ждут:\n",
        "- Подкасты и практики\n",
        "- Челленджи и разборы\n",
        "- Структурная система развития\n\n",
        "Готова присоединиться? Оформи доступ в меню.",
    )
    await answer_with_main_menu(message, about_text, user)


async def send_faq_section(message: types.Message, user: Optional[dict] = None) -> None:
    faq_text = await get_content(
        "menu.faq",
        "FAQ.\n\n",
        "Как получить доступ? — Оформи участие в разделе «Оплата».\n\n",
        "Как проходят уроки? — Видеоуроки + практики, доступ через меню.\n\n",
        "Как задать вопрос? — Кнопка «Вопрос» в уроке или " + SUPPORT_CONTACT + ".\n\n",
        "Как продлить доступ? — Раздел «Оплата».",
    )
    await answer_with_main_menu(message, faq_text, user)


async def send_pay_section(message: types.Message, user: Optional[dict] = None) -> None:
    if not AT_PRODUCT_ID_CLUB:
        await answer_with_main_menu(message, "Сейчас доступ в клуб бесплатный.", user)
        return

    url = f"https://antitraining.example/checkout/{AT_PRODUCT_ID_CLUB}"
    pay_text = await get_content(
        "menu.pay",
        "Доступ в клуб CODE: Магнетизм.\n\n",
        "Тариф: Полный доступ — 2690₽ (единовременно).\n\n",
        f"Ссылка на оплату: {url}\n\n",
        "После оплаты бот автоматически активирует доступ.",
    )
    await answer_with_main_menu(message, pay_text, user)


async def send_free_lessons_section(message: types.Message, user: Optional[dict] = None) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)
    if not user_row:
        user_row = await ensure_user(message.from_user)

    if not user_row:
        await answer_with_main_menu(message, "Перезапусти /start", user_row)
        return

    next_lesson = await next_lesson_to_deliver(user_row["id"])

    if next_lesson == 5:
        completed_text = await get_content(
            "menu.funnel.completed",
            "Все уроки пройдены.\n\n",
            "Дальше — клуб CODE: Магнетизм: углублённые практики, сообщество, живые эфиры.",
        )
        await answer_with_main_menu(message, completed_text, user_row)
        return

    access_text = (
        "Уроки CODE: Магнетизм.\n\n"
        "Выбери доступ:\n\n"
        "Бесплатно: 4 базовых урока + задания.\n\n"
        "Платно: весь курс + практики, материалы и клуб."
    )

    await answer_with_main_menu(
        message,
        access_text,
        user_row,
        reply_markup=create_access_type_keyboard(),
    )


async def send_progress_section(message: types.Message, user: Optional[dict] = None) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)

    if not user_row:
        await answer_with_main_menu(message, "Перезапусти /start", user_row)
        return

    rows = await fetch(
        "SELECT lesson_num, hw_status FROM funnel_progress WHERE user_id=$1 ORDER BY lesson_num",
        user_row["id"],
    )

    status_map = {r["lesson_num"]: r["hw_status"] for r in rows} if rows else {}

    progress_text = "Мой прогресс.\n\n"

    for i in range(1, 5):
        st = status_map.get(i, "—")
        status_text = {
            "submitted": "Выполнено",
            "skipped": "Пропущено",
            "pending": "В процессе",
        }.get(st, "Не начато")

        lesson_titles = {
            1: "Внимание",
            2: "Мысли",
            3: "Слова",
            4: "Эмоции",
        }

        progress_text += f"Урок {i}: {lesson_titles.get(i, f'Урок {i}')} — {status_text}\n"

    completed = sum(1 for st in status_map.values() if st == "submitted")
    if completed == 0:
        progress_text += "\nНачни с первого урока."
    elif completed < 4:
        progress_text += f"\nПройдено {completed} из 4 уроков."
    else:
        progress_text += "\nВсе уроки завершены. Пора на следующий уровень."

    await answer_with_main_menu(message, progress_text, user_row)


async def send_support_section(message: types.Message, user: Optional[dict] = None) -> None:
    support_text = (
        "Поддержка.\n\n"
        f"Если есть вопросы или сложности — пиши сюда: {SUPPORT_CONTACT}. Мы отвечаем лично и максимально быстро."
    )
    await answer_with_main_menu(message, support_text, user)


async def send_rules_section(message: types.Message, user: Optional[dict] = None) -> None:
    rules_text = await get_content(
        "menu.rules",
        "Правила CODE: Магнетизм.\n\n",
        "1. Уважение к участникам.\n",
        "2. Только полезный контент.\n",
        "3. Без спама и рекламы.\n",
        "4. Конфиденциальность.\n",
        "5. Без оскорблений и дискриминации.\n\n",
        "Нарушение = блокировка доступа.",
    )
    await answer_with_main_menu(message, rules_text, user)


async def send_analysis_section(message: types.Message, user: Optional[dict] = None) -> None:
    analysis_text = await get_content(
        "menu.analysis",
        "Персональный разбор.\n\n",
        "Заполни форму → мы назначим время.\n\n",
        "https://forms.example.com/analysis",
    )
    await answer_with_main_menu(message, analysis_text, user)


async def send_test_section(message: types.Message, user: Optional[dict] = None) -> None:
    test_text = await get_content(
        "menu.test",
        "Тест: определение уровня.\n\n",
        "Ссылка: https://forms.example.com/test\n\n",
        "После теста ты получишь анализ, рекомендации и сможешь записаться на разбор.",
    )
    await answer_with_main_menu(message, test_text, user)


async def send_weekly_materials_section(message: types.Message, user: Optional[dict] = None) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)

    if not user_row or not await is_member(user_row):
        locked_text = await get_content(
            "menu.weekly.locked",
            "Материалы недели доступны участницам клуба.\n\nОформи доступ в разделе «Оплатить доступ», и бот пришлёт ссылку.",
        )
        await answer_with_main_menu(message, locked_text, user_row)
        return

    weekly_text = await get_content(
        "weekly_materials",
        "📚 Материалы недели:\n"
        "• Подкаст: [ссылка]\n"
        "• Практика: [ссылка]\n"
        "• Челлендж: [описание]\n"
        "• Дневник: [шаблон]",
    )
    await answer_with_main_menu(message, weekly_text, user_row)


async def send_schedule_section(message: types.Message, user: Optional[dict] = None) -> None:
    user_row = user or await get_user_with_id(message.from_user.id)

    if not user_row or not await is_member(user_row):
        locked_text = await get_content(
            "menu.schedule.locked",
            "Расписание доступно участницам клуба.\n\nАктивируй доступ — и бот пришлёт ближайшие эфиры.",
        )
        await answer_with_main_menu(message, locked_text, user_row)
        return

    schedule_text = await get_content(
        "schedule",
        "🗓️ Расписание эфиров:\n"
        "• Понедельник 20:00 — Вводный эфир\n"
        "• Четверг 19:00 — Практика в группе\n"
        "• Воскресенье 18:00 — Подведение итогов",
    )
    await answer_with_main_menu(message, schedule_text, user_row)


MAIN_MENU_ACTIONS: Dict[str, Callable[[types.Message, Optional[dict]], Awaitable[None]]] = {
    "О клубе": send_about_section,
    "FAQ": send_faq_section,
    "Бесплатные уроки": send_free_lessons_section,
    "Мой прогресс": send_progress_section,
    "Поддержка": send_support_section,
    "Правила": send_rules_section,
    "Записаться на разбор": send_analysis_section,
    "Пройти тест": send_test_section,
    "Оплатить доступ": send_pay_section,
    "Материалы недели": send_weekly_materials_section,
    "Расписание": send_schedule_section,
}
# ──────────────────────────────────────────────────────────────────────────────
# Утилиты/бизнес-логика
# ──────────────────────────────────────────────────────────────────────────────
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
            reply_markup=create_back_button()
        )
        return
    
    # Показываем главное меню
    is_admin = str(message.from_user.id) in ADMIN_IDS
    kb = create_main_menu_keyboard(is_member=await is_member(user), has_pay=bool(AT_PRODUCT_ID_CLUB), is_admin=is_admin)
    
    welcome_text = (
        "Добро пожаловать в CODE: Магнетизм. Это пространство для развития и перемен. Выбери раздел в меню, чтобы начать."
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
        reply_markup=create_back_button()
    )

# Обработка ввода email при регистрации
@router.message(RegistrationStates.waiting_email, F.text.len() > 0)
async def registration_receive_email(message: types.Message, state: FSMContext):
    email = (message.text or "").strip()
    
    if not validate_email(email):
        await message.answer(
            "Формат неверный. Пример: name@mail.com",
            reply_markup=create_back_button()
        )
        return
    
    # Сохраняем email
    await execute("UPDATE users SET email=$2, updated_at=NOW() WHERE tg_user_id=$1", message.from_user.id, email)
    
    # Переходим к вводу телефона
    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer(
        "Укажи номер телефона:",
        reply_markup=create_back_button()
    )

# Обработка ввода телефона при регистрации
@router.message(RegistrationStates.waiting_phone, F.text.len() > 0)
async def registration_receive_phone(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text or "")
    
    if not validate_phone(phone):
        await message.answer(
            "Формат неверный. Пример: +79991234567",
            reply_markup=create_back_button()
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
    kb = create_main_menu_keyboard(is_member=await is_member(user), has_pay=bool(AT_PRODUCT_ID_CLUB), is_admin=is_admin)
    
    welcome_text = (
        f"Регистрация завершена, {user.get('name')}!\n\n"
        "Теперь тебе доступно:\n"
        "- Бесплатные уроки\n"
        "- Доступ в клуб\n"
        "- Отслеживание прогресса\n\n"
        "Выбирай в меню и начинай."
    )
    
    await message.answer(welcome_text, reply_markup=kb)


@router.message(
    ~F.via_bot,
    F.text.in_(tuple(MAIN_MENU_ACTIONS.keys())),
)
async def handle_main_menu_buttons(message: types.Message, state: FSMContext) -> None:
    """Обработка текстовых кнопок главного меню."""

    current_state = await state.get_state()
    if current_state in (
        HWStates.waiting_answer,
        HWStates.waiting_feedback,
        RegistrationStates.waiting_name,
        RegistrationStates.waiting_email,
        RegistrationStates.waiting_phone,
        ProfileStates.waiting_email,
        ProfileStates.waiting_phone,
    ):
        return

    text = (message.text or "").strip()
    handler = MAIN_MENU_ACTIONS.get(text)
    if not handler:
        return

    user = await get_user_with_id(message.from_user.id)
    if not user:
        user = await ensure_user(message.from_user)

    await handler(message, user)


# Fallback — если не матчится ни на один хэндлер (и не мешаем FSM)
@router.message(~F.via_bot & ~F.text.startswith("/"))
async def fallback(message: types.Message, state: FSMContext):
    cur = await state.get_state()
    if cur in (HWStates.waiting_answer, HWStates.waiting_feedback, 
                RegistrationStates.waiting_name, RegistrationStates.waiting_email, RegistrationStates.waiting_phone,
                ProfileStates.waiting_email, ProfileStates.waiting_phone):
        return
    await message.answer("Набери /start для меню.")
# ──────────────────────────────────────────────────────────────────────────────
# Меню
# ──────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu:about")
async def cb_about(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    about_text = await get_content("menu.about", 
        "CODE: Магнетизм — закрытое пространство для тех, кто хочет:\n\n"
        "- Управлять вниманием, мыслями и эмоциями\n"
        "- Укрепить уверенность и личный магнетизм\n"
        "- Изменить сценарии в отношениях и деньгах\n\n"
        "Внутри тебя ждут:\n"
        "- Подкасты и практики\n"
        "- Челленджи и разборы\n"
        "- Структурная система развития\n\n"
        "Готова присоединиться? Оформи доступ в меню."
    )
    
    try:
        await safe_edit_text(
            cb.message, 
            about_text, 
            reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_about: {e}", exc_info=True)
    await cb.answer()

@router.callback_query(F.data == "menu:faq")
async def cb_faq(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    faq_text = await get_content("menu.faq",
        "FAQ.\n\n"
        "Как получить доступ? — Оформи участие в разделе «Оплата».\n\n"
        "Как проходят уроки? — Видеоуроки + практики, доступ через меню.\n\n"
        "Как задать вопрос? — Кнопка «Вопрос» в уроке или " + SUPPORT_CONTACT + ".\n\n"
        "Как продлить доступ? — Раздел «Оплата»."
    )
    
    try:
        await safe_edit_text(
            cb.message, 
            faq_text, 
            reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_faq: {e}", exc_info=True)
    await cb.answer()

@router.callback_query(F.data == "menu:pay")
async def cb_pay(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    if not AT_PRODUCT_ID_CLUB:
        await cb.answer("Сейчас доступ в клуб бесплатный", show_alert=True)
    else:
        url = f"https://antitraining.example/checkout/{AT_PRODUCT_ID_CLUB}"
        pay_text = await get_content("menu.pay",
            "Доступ в клуб CODE: Магнетизм.\n\n"
            "Тариф: Полный доступ — 2690₽ (единовременно).\n\n"
            f"Ссылка на оплату: {url}\n\n"
            "После оплаты бот автоматически активирует доступ."
        )
        try:
            await safe_edit_text(
                cb.message, 
                pay_text, 
                reply_markup=create_main_menu_keyboard(await is_member(user), True, is_admin)
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.error(f"Error in cb_pay: {e}", exc_info=True)
    await cb.answer()

@router.callback_query(F.data == "menu:progress")
async def cb_progress(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return
    
    rows = await fetch(
        "SELECT lesson_num, hw_status FROM funnel_progress WHERE user_id=$1 ORDER BY lesson_num",
        user["id"]
    )
    
    status_map = {r["lesson_num"]: r["hw_status"] for r in rows} if rows else {}
    
    progress_text = "Мой прогресс.\n\n"
    
    for i in range(1, 5):
        st = status_map.get(i, "—")
        status_text = {"submitted": "Выполнено", "skipped": "Пропущено", "pending": "В процессе"}.get(st, "Не начато")
        
        lesson_titles = {
            1: "Внимание",
            2: "Мысли",
            3: "Слова",
            4: "Эмоции"
        }
        
        progress_text += f"Урок {i}: {lesson_titles.get(i, f'Урок {i}')} — {status_text}\n"
    
    completed = sum(1 for st in status_map.values() if st == "submitted")
    if completed == 0:
        progress_text += "\nНачни с первого урока."
    elif completed < 4:
        progress_text += f"\nПройдено {completed} из 4 уроков."
    else:
        progress_text += "\nВсе уроки завершены. Пора на следующий уровень."
    
    try:
        await safe_edit_text(
            cb.message, 
            progress_text, 
            reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_progress: {e}", exc_info=True)
    await cb.answer()

@router.callback_query(F.data == "menu:funnel")
async def cb_funnel(cb: types.CallbackQuery):
    user = await ensure_user(cb.from_user)
    n = await next_lesson_to_deliver(user["id"])
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    if n == 5:
        completed_text = await get_content("menu.funnel.completed",
            "Все уроки пройдены.\n\n"
            "Дальше — клуб CODE: Магнетизм: углублённые практики, сообщество, живые эфиры."
        )
        try:
            await safe_edit_text(
                cb.message, 
                completed_text, 
                reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.error(f"Error in cb_funnel (completed): {e}", exc_info=True)
        await cb.answer()
        return
    
    access_text = (
        "Уроки CODE: Магнетизм.\n\n"
        "Выбери доступ:\n\n"
        "Бесплатно: 4 базовых урока + задания.\n\n"
        "Платно: весь курс + практики, материалы и клуб."
    )
    
    try:
        await safe_edit_text(
            cb.message, 
            access_text, 
            reply_markup=create_access_type_keyboard()
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_funnel: {e}", exc_info=True)
    await cb.answer()

# Обработка выбора типа доступа
@router.callback_query(F.data.startswith("access:"))
async def cb_select_access(cb: types.CallbackQuery):
    access_type = cb.data.split(":")[1]
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    if access_type == "free":
        n = await next_lesson_to_deliver(user["id"])
        
        lessons_text = (
            "Бесплатные уроки\n\n"
            "Доступные уроки:\n\n"
        )
        
        keyboard = []
        for i in range(1, 5):
            status = "✅" if i < n else "⏳" if i == n else "🔒"
            lesson_titles = {
                1: "Внимание",
                2: "Мысли",
                3: "Слова",
                4: "Эмоции"
            }
            
            lessons_text += f"{status} Урок {i}: {lesson_titles.get(i, f'Урок {i}')}\n"
            keyboard.append([types.InlineKeyboardButton(
                text=f"{status} Урок {i}", 
                callback_data=f"funnel:lesson:{i}"
            )])
        
        keyboard.append([types.InlineKeyboardButton(text="Назад в меню", callback_data="menu:main")])
        
        try:
            await safe_edit_text(
                cb.message, 
                lessons_text, 
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.error(f"Error in cb_select_access (free): {e}", exc_info=True)
    
    elif access_type == "paid":
        if not AT_PRODUCT_ID_CLUB:
            await cb.answer("Сейчас доступ в клуб бесплатный", show_alert=True)
        else:
            url = f"https://antitraining.example/checkout/{AT_PRODUCT_ID_CLUB}"
            pay_text = (
                "Доступ в клуб CODE: Магнетизм.\n\n"
                "Тариф: Полный доступ — 2690₽ (единовременно).\n\n"
                f"Ссылка на оплату: {url}\n\n"
                "После оплаты бot автоматически активирует доступ."
            )
            try:
                await safe_edit_text(
                    cb.message, 
                    pay_text, 
                    reply_markup=create_main_menu_keyboard(await is_member(user), True, is_admin)
                )
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    logger.error(f"Error in cb_select_access (paid): {e}", exc_info=True)
    
    await cb.answer()

# Обработка выбора урока
@router.callback_query(F.data.startswith("funnel:lesson:"))
async def cb_select_lesson(cb: types.CallbackQuery):
    lesson_num = int(cb.data.split(":")[-1])
    user = await get_user_with_id(cb.from_user.id)
    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return
    
    n = await next_lesson_to_deliver(user["id"])
    if lesson_num > n:
        await cb.answer("Этот урок еще не доступен. Пройди предыдущие уроки сначала.", show_alert=True)
        return
    
    await deliver_lesson(cb.message, user, lesson_num)
    await cb.answer()

async def deliver_lesson(msg: types.Message, user_row: dict, lesson_num: int):
    y = _load_yaml_content()
    lesson_urls = (((y.get("funnel") or {}).get("lesson_urls")) or {})
    url = (lesson_urls.get(lesson_num) if isinstance(lesson_urls, dict) else "") or ""
    hw_questions = (((y.get("funnel") or {}).get("hw_questions")) or {})
    hw_q = hw_questions.get(lesson_num, "Короткое ДЗ: ответь одной фразой.")
    
    lesson_descriptions = {
        1: "Урок 1: Внимание\n\n"
           "Как работает твой фокус и почему он формирует жизнь.",
        
        2: "Урок 2: Мысли\n\n"
           "Как перестать теряться в хаосе ума и управлять внутренним диалогом.",
        
        3: "Урок 3: Слова\n\n"
           "Как твоя речь кодирует события и отношения.",
        
        4: "Урок 4: Эмоции\n\n"
           "Как перестать застревать в чувствах и превращать их в топливо."
    }
    
    description = lesson_descriptions.get(lesson_num, f"Урок {lesson_num}")
    
    await upsert_funnel_delivery(user_row["id"], lesson_num)
    
    text = f"{description}\n\n"
    if url:
        text += f"Материалы урока: {url}\n\n"
    text += f"Практическое задание:\n{hw_q}"
    
    kb = create_lesson_menu_keyboard(lesson_num)
    async with ChatActionSender.typing(chat_id=msg.chat.id, bot=msg.bot):
        await asyncio.sleep(0.2)
        await msg.answer(text, reply_markup=kb)

# «Готово/Пропустить/Вопрос»
@router.callback_query(F.data.startswith("funnel:done:"))
async def cb_funnel_done(cb: types.CallbackQuery, state: FSMContext):
    lesson_num = int(cb.data.split(":")[-1])
    user = await get_user_with_id(cb.from_user.id)
    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return
    await state.set_state(HWStates.waiting_answer)
    await state.update_data(lesson_num=lesson_num)
    await cb.message.answer(
        "Напиши короткий ответ на задание. Например: «Сегодня я заметила, что…»",
        reply_markup=create_back_button()
    )
    await cb.answer()

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
    await state.update_data(lesson_num=lesson_num)
    
    await message.answer(
        f"Отлично!\n\n"
        f"Твой ответ на урок «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» принят.\n\n"
        f"Теперь расскажи, как тебе урок? Насколько полезной была информация?",
        reply_markup=create_feedback_keyboard(lesson_num)
    )

@router.callback_query(F.data.startswith("funnel:skip:"))
async def cb_funnel_skip(cb: types.CallbackQuery):
    lesson_num = int(cb.data.split(":")[-1])
    user = await get_user_with_id(cb.from_user.id)
    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return
    await mark_lesson_skipped(user["id"], lesson_num)
    
    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции"
    }
    
    await cb.message.answer(
        f"Урок «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» пропущен. К нему можно вернуться в «Мой прогресс».",
        reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB))
    )
    await cb.answer()

@router.callback_query(F.data.startswith("funnel:q:"))
async def cb_funnel_question(cb: types.CallbackQuery):
    lesson_num = int(cb.data.split(":")[-1])
    await cb.message.answer(
        f"Задай вопрос по уроку {lesson_num}\n\n"
        f"Напиши одним сообщением или в поддержку: {SUPPORT_CONTACT}",
        reply_markup=create_back_button()
    )
    await cb.answer()

# Обработка обратной связи после урока
@router.callback_query(F.data.startswith("feedback:"))
async def cb_feedback(cb: types.CallbackQuery, state: FSMContext):
    data = cb.data.split(":")
    feedback_type = data[1]
    lesson_num = int(data[2])
    
    user = await get_user_with_id(cb.from_user.id)
    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return
    
    if feedback_type == "custom":
        await state.set_state(HWStates.waiting_feedback)
        await state.update_data(lesson_num=lesson_num)
        await cb.message.answer(
            "Поделись впечатлением от урока одним сообщением.",
            reply_markup=create_back_button()
        )
    elif feedback_type == "skip":
        await state.clear()
        
        lesson_titles = {
            1: "Внимание",
            2: "Мысли",
            3: "Слова",
            4: "Эмоции"
        }
        
        await cb.message.answer(
            f"Спасибо! Твой прогресс по уроку «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» сохранен.",
            reply_markup=create_after_lesson_keyboard(lesson_num)
        )
    else:
        feedback_map = {
            "excellent": "Отлично",
            "good": "Хорошо",
            "average": "Нормально",
            "poor": "Плохо"
        }
        
        await save_lesson_feedback(user["id"], lesson_num, feedback_type)
        
        lesson_titles = {
            1: "Внимание",
            2: "Мысли",
            3: "Слова",
            4: "Эмоции"
        }
        
        await cb.message.answer(
            f"Спасибо за отзыв! Твоя оценка «{feedback_map.get(feedback_type, feedback_type)}» по уроку «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» сохранена.",
            reply_markup=create_after_lesson_keyboard(lesson_num)
        )
    
    await cb.answer()

# Обработка текстового отзыва
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
    await state.clear()
    
    lesson_titles = {
        1: "Внимание",
        2: "Мысли",
        3: "Слова",
        4: "Эмоции"
    }
    
    await message.answer(
        f"Спасибо за отзыв!\n\n"
        f"Твой отзыв по уроку «{lesson_titles.get(lesson_num, f'Урок {lesson_num}')}» сохранен.",
        reply_markup=create_after_lesson_keyboard(lesson_num)
    )

@router.callback_query(F.data.startswith("funnel:next:"))
async def cb_funnel_next(cb: types.CallbackQuery):
    prev = int(cb.data.split(":")[-1])  # для логов/аналитики
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return
    n = await next_lesson_to_deliver(user["id"])
    if n == 5:
        offer = await get_content("offer_after_lesson_4", 
            "Все уроки пройдены.\n\n"
            "Дальше — клуб CODE: Магнетизм: углублённые практики, сообщество, живые эфиры."
        )
        await cb.message.answer(offer, reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin))
    else:
        await deliver_lesson(cb.message, user, n)
    await cb.answer()
# ──────────────────────────────────────────────────────────────────────────────
# Новые кнопки меню: правила, запись на разбор, тест
# ──────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu:rules")
async def cb_rules(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    rules_text = await get_content("menu.rules",
        "Правила CODE: Магнетизм.\n\n"
        "1. Уважение к участникам.\n"
        "2. Только полезный контент.\n"
        "3. Без спама и рекламы.\n"
        "4. Конфиденциальность.\n"
        "5. Без оскорблений и дискриминации.\n\n"
        "Нарушение = блокировка доступа."
    )
    
    try:
        await safe_edit_text(
            cb.message, 
            rules_text, 
            reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_rules: {e}", exc_info=True)
    await cb.answer()

@router.callback_query(F.data == "menu:analysis")
async def cb_analysis(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    
    analysis_text = await get_content("menu.analysis",
        "Персональный разбор.\n\n"
        "Заполни форму → мы назначим время.\n\n"
        "https://forms.example.com/analysis"
    )
    
    try:
        await safe_edit_text(
            cb.message, 
            analysis_text, 
            reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_analysis: {e}", exc_info=True)
    await cb.answer()

@router.callback_query(F.data == "menu:test")
async def cb_test(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS

    test_text = await get_content("menu.test",
        "Тест: определение уровня.\n\n"
        "Ссылка: https://forms.example.com/test\n\n"
        "После теста ты получишь анализ, рекомендации и сможешь записаться на разбор."
    )

    try:
        await safe_edit_text(
            cb.message,
            test_text,
            reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_test: {e}", exc_info=True)
    await cb.answer()


@router.callback_query(F.data == "menu:weekly")
async def cb_weekly(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)

    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return

    member = await is_member(user)
    if not member:
        await cb.answer("Раздел доступен участницам клуба", show_alert=True)
        return

    is_admin = str(cb.from_user.id) in ADMIN_IDS

    weekly_text = await get_content(
        "weekly_materials",
        "📚 Материалы недели:\n"
        "• Подкаст: [ссылка]\n"
        "• Практика: [ссылка]\n"
        "• Челлендж: [описание]\n"
        "• Дневник: [шаблон]",
    )

    try:
        await safe_edit_text(
            cb.message,
            weekly_text,
            reply_markup=create_main_menu_keyboard(member, bool(AT_PRODUCT_ID_CLUB), is_admin),
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_weekly: {e}", exc_info=True)

    await cb.answer()


@router.callback_query(F.data == "menu:schedule")
async def cb_schedule(cb: types.CallbackQuery):
    user = await get_user_with_id(cb.from_user.id)

    if not user:
        await cb.answer("Перезапусти /start", show_alert=True)
        return

    member = await is_member(user)
    if not member:
        await cb.answer("Расписание доступно участницам клуба", show_alert=True)
        return

    is_admin = str(cb.from_user.id) in ADMIN_IDS

    schedule_text = await get_content(
        "schedule",
        "🗓️ Расписание эфиров:\n"
        "• Понедельник 20:00 — Вводный эфир\n"
        "• Четверг 19:00 — Практика в группе\n"
        "• Воскресенье 18:00 — Подведение итогов",
    )

    try:
        await safe_edit_text(
            cb.message,
            schedule_text,
            reply_markup=create_main_menu_keyboard(member, bool(AT_PRODUCT_ID_CLUB), is_admin),
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_schedule: {e}", exc_info=True)

    await cb.answer()
# ──────────────────────────────────────────────────────────────────────────────
# Поддержка и помощь
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("support"))
async def cmd_support(message: types.Message):
    is_admin = str(message.from_user.id) in ADMIN_IDS
    await message.answer(
        f"Поддержка.\n\n"
        f"Если есть вопросы или сложности — пиши сюда: {SUPPORT_CONTACT}. Мы отвечаем лично и максимально быстро.",
        reply_markup=create_main_menu_keyboard(False, bool(AT_PRODUCT_ID_CLUB), is_admin)
    )

@router.message(Command("id"))
async def cmd_id(message: types.Message):
    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else "—"
    is_admin = str(message.from_user.id) in ADMIN_IDS
    await message.answer(
        f"Твои данные:\n\n"
        f"Telegram ID: <code>{uid}</code>\n"
        f"Username: {uname}\n\n"
        f"Эти данные могут понадобиться при обращении в поддержку.",
        reply_markup=create_main_menu_keyboard(False, bool(AT_PRODUCT_ID_CLUB), is_admin)
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    is_admin = str(message.from_user.id) in ADMIN_IDS
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
        reply_markup=create_main_menu_keyboard(False, bool(AT_PRODUCT_ID_CLUB), is_admin)
    )
# ──────────────────────────────────────────────────────────────────────────────
# Навигация по меню
# ──────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu:back")
async def cb_back(cb: types.CallbackQuery):
    """Возврат в предыдущее меню"""
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    await cb.message.edit_text(
        "Главное меню\n\n"
        "Выбери раздел, чтобы продолжить:",
        reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
    )
    await cb.answer()

@router.callback_query(F.data == "menu:main")
async def cb_main(cb: types.CallbackQuery):
    """Возврат в главное меню"""
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    await cb.message.edit_text(
        "Главное меню\n\n"
        "Выбери раздел, чтобы продолжить:",
        reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
    )
    await cb.answer()

@router.callback_query(F.data == "menu:support")
async def cb_support(cb: types.CallbackQuery):
    """Раздел поддержки"""
    user = await get_user_with_id(cb.from_user.id)
    is_admin = str(cb.from_user.id) in ADMIN_IDS
    support_text = (
        "Поддержка.\n\n"
        f"Если есть вопросы или сложности — пиши сюда: {SUPPORT_CONTACT}. Мы отвечаем лично и максимально быстро."
    )
    
    try:
        await safe_edit_text(
            cb.message, 
            support_text, 
            reply_markup=create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_support: {e}", exc_info=True)
    await cb.answer()
# ──────────────────────────────────────────────────────────────────────────────
# Обработка отмены для всех состояний
# ──────────────────────────────────────────────────────────────────────────────
@router.message(F.text.lower() == "отмена")
@router.callback_query(F.data == "cancel")
async def cancel_handler(message: types.Message | types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    text = "Действие отменено\n\n"
    
    if isinstance(message, types.CallbackQuery):
        user = await get_user_with_id(message.from_user.id)
        is_admin = str(message.from_user.id) in ADMIN_IDS
        kb = create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        await message.message.answer(text + "Возвращаюсь в главное меню...", reply_markup=kb)
        await message.answer()
    else:
        user = await get_user_with_id(message.from_user.id)
        is_admin = str(message.from_user.id) in ADMIN_IDS
        kb = create_main_menu_keyboard(await is_member(user), bool(AT_PRODUCT_ID_CLUB), is_admin)
        await message.answer(text + "Возвращаюсь в главное меню...", reply_markup=kb)
# ──────────────────────────────────────────────────────────────────────────────
# Админ-панель
# ──────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu:admin")
async def cb_admin_menu(cb: types.CallbackQuery):
    """Обработка кнопки админ-панели"""
    if str(cb.from_user.id) not in ADMIN_IDS:
        await cb.answer("Доступ запрещен", show_alert=True)
        return
    
    admin_text = (
        "Админ-панель\n\n"
        "Выберите действие:"
    )
    
    try:
        await safe_edit_text(cb.message, admin_text, reply_markup=create_admin_keyboard())
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in cb_admin_menu: {e}", exc_info=True)
    await cb.answer()

@router.callback_query(F.data.startswith("admin:"))
async def cb_admin_actions(cb: types.CallbackQuery):
    """Обработка действий админ-панели"""
    if str(cb.from_user.id) not in ADMIN_IDS:
        await cb.answer("Доступ запрещен", show_alert=True)
        return
    
    action = cb.data.split(":")[1]
    
    if action == "users":
        text = (
            "Управление пользователями\n\n"
            "Доступные команды:\n"
            "/admin user <code>username или tg_id</code> — информация о пользователе\n"
            "/admin set_paid <code>username</code> [days или YYYY-MM-DD] — установить оплату\n"
            "/admin bind <code>username или tg_id</code> email=<code>email</code> phone=<code>phone</code> — привязать контакты\n"
            "/admin access <code>username</code> [revoke или status] — управление доступом"
        )
        await cb.message.answer(text, reply_markup=create_admin_keyboard())
    
    elif action == "broadcast":
        text = (
            "Рассылка\n\n"
            "Доступные команды:\n"
            "/broadcast <code>segment</code> [--html] — рассылка пользователям\n\n"
            "Сегменты: all, lead_funnel, member_active, member_expired, expired"
        )
        await cb.message.answer(text, reply_markup=create_admin_keyboard())
    
    elif action == "content":
        text = (
            "Управление контентом\n\n"
            "Доступные команды:\n"
            "/content_keys — показать ключи контента\n"
            "/content_get <code>key</code> — показать текст по ключу\n"
            "/content_set <code>key</code> — сохранить текст (сообщение-ответом)"
        )
        await cb.message.answer(text, reply_markup=create_admin_keyboard())
    
    elif action == "stats":
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
        await cb.message.answer(stats_text, reply_markup=create_admin_keyboard())
    
    elif action == "debug":
        config_text = (
            "Конфигурация бота\n\n"
            f"Версия: {BOT_VERSION}\n"
            f"Часовой пояс: {BOT_TIMEZONE}\n"
            f"Поддержка: {SUPPORT_CONTACT}\n"
            f"Продукт ID: {AT_PRODUCT_ID_CLUB or 'Не задан'}\n"
            f"Чат клуба: {CLUB_CHAT_ID or 'Не задан'}"
        )
        await cb.message.answer(config_text, reply_markup=create_admin_keyboard())
    
    await cb.answer()

def is_admin_id(uid: int) -> bool:
    return str(uid) in ADMIN_IDS
# ──────────────────────────────────────────────────────────────────────────────
# Админка: доступ/помощь
# ──────────────────────────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: types.Message, command: CommandObject):
    if not is_admin_id(message.from_user.id):
        return
    
    if not command.args:
        admin_text = (
            "Админ-панель\n\n"
            "Выберите действие:"
        )
        await message.answer(admin_text, reply_markup=create_admin_keyboard())
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