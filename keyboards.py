# keyboards.py
import os
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
def main_menu(is_member: bool = False, has_pay: bool = False) -> InlineKeyboardMarkup:
    """
    Аккуратное, предсказуемое меню:
    - верхний ряд: инфо/FAQ
    - второй ряд: бесплатные уроки/прогресс
    - третий ряд: профиль/поддержка
    - опционально: оплата/разделы участника
    """
    rows: list[list[InlineKeyboardButton]] = []

    # Инфо-блок
    rows.append([
        InlineKeyboardButton(text="🌟 О клубе", callback_data="menu:about"),
        InlineKeyboardButton(text="❓ FAQ", callback_data="menu:faq"),
    ])

    # Обучение
    rows.append([
        InlineKeyboardButton(text="📚 Бесплатные уроки", callback_data="menu:funnel"),
        InlineKeyboardButton(text="📊 Мой прогресс", callback_data="menu:progress"),
    ])

    # Профиль/поддержка
    rows.append([
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu:support"),
    ])

    # Монетизация
    if has_pay:
        rows.append([InlineKeyboardButton(text="💳 Продлить доступ", callback_data="menu:pay")])

    # Разделы участника
    if is_member:
        rows.append([
            InlineKeyboardButton(text="🗂️ Материалы недели", callback_data="menu:weekly"),
            InlineKeyboardButton(text="📅 Расписание", callback_data="menu:schedule"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)

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
