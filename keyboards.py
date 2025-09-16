# keyboards.py
import os
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# ──────────────────────────────────────────────────────────────────────────────
# ENV / helpers
# ──────────────────────────────────────────────────────────────────────────────
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@codemagnetic").strip()

def _support_url() -> str:
    handle = SUPPORT_CONTACT.lstrip("@")
    return f"https://t.me/{handle}" if handle else "https://t.me/"

# ──────────────────────────────────────────────────────────────────────────────
# Главное меню (UX-вариант)
# ──────────────────────────────────────────────────────────────────────────────
def main_menu(is_member: bool = False, has_pay: bool = False) -> ReplyKeyboardMarkup:
    """
    Реплай-клавиатура основного меню для использования в чатах.
    """
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text="О клубе"),
            KeyboardButton(text="FAQ"),
        ],
        [
            KeyboardButton(text="Бесплатные уроки"),
            KeyboardButton(text="Мой прогресс"),
        ],
        [
            KeyboardButton(text="Поддержка"),
            KeyboardButton(text="Правила"),
        ],
        [
            KeyboardButton(text="Записаться на разбор"),
            KeyboardButton(text="Пройти тест"),
        ],
    ]

    if has_pay:
        rows.append([KeyboardButton(text="Оплатить доступ")])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел",
    )

# ──────────────────────────────────────────────────────────────────────────────
# Список уроков (карта уроков)
# ──────────────────────────────────────────────────────────────────────────────
def lessons_list_keyboard(next_available: int) -> InlineKeyboardMarkup:
    """
    Клавиатура списка уроков:
    - до next_available: открыты/пройдены (✅ / ⏳),
    - после — замок (🔒) и при нажатии дадим alert в хэндлере.
    """
    rows: list[list[InlineKeyboardButton]] = []
    titles = {
        1: "Введение",
        2: "Основы",
        3: "Практики",
        4: "Интеграция",
    }
    for i in range(1, 5):
        status = "✅" if i < next_available else ("⏳" if i == next_available else "🔒")
        rows.append([InlineKeyboardButton(
            text=f"{status} Урок {i}: {titles.get(i,'')}",
            callback_data=f"funnel:lesson:{i}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ──────────────────────────────────────────────────────────────────────────────
# Клавиатура под карточкой урока
# ──────────────────────────────────────────────────────────────────────────────
def lesson_keyboard(lesson_num: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"funnel:done:{lesson_num}"),
                InlineKeyboardButton(text="⏭️ Пропустить", callback_data=f"funnel:skip:{lesson_num}"),
            ],
            [InlineKeyboardButton(text="❓ Задать вопрос", callback_data=f"funnel:q:{lesson_num}")],
            [InlineKeyboardButton(text="⬅️ Назад к меню", callback_data="menu:main")],
        ]
    )

# ──────────────────────────────────────────────────────────────────────────────
# После сдачи ДЗ
# ──────────────────────────────────────────────────────────────────────────────
def after_lesson_keyboard(prev_lesson_num: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Следующий урок", callback_data=f"funnel:next:{prev_lesson_num}")],
            [InlineKeyboardButton(text="📋 Мой прогресс", callback_data="menu:progress")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )

# ──────────────────────────────────────────────────────────────────────────────
# Профиль/контакты
# ──────────────────────────────────────────────────────────────────────────────
def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Изменить email", callback_data="profile:email")],
            [InlineKeyboardButton(text="📞 Изменить телефон", callback_data="profile:phone")],
            [InlineKeyboardButton(text="🆘 Поддержка", url=_support_url())],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="menu:main")],
        ]
    )

# ──────────────────────────────────────────────────────────────────────────────
# Cancel / Back
# ──────────────────────────────────────────────────────────────────────────────
def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")]]
    )

def cancel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )
