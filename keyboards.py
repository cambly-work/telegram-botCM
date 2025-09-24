# keyboards.py
import os
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ──────────────────────────────────────────────────────────────────────────────
# ENV / helpers
# ──────────────────────────────────────────────────────────────────────────────
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@codemagnetic").strip()

# ──────────────────────────────────────────────────────────────────────────────
# Общие тексты для кнопок
# ──────────────────────────────────────────────────────────────────────────────
BACK_TO_MAIN = "⬅️ В главное меню"
BACK_TO_LEARNING = "⬅️ К обучению"
BACK_TO_MATERIALS = "⬅️ К материалам"
BACK_TO_PROFILE = "⬅️ К профилю"
BACK_TO_ADMIN = "⬅️ В админку"
BACK_TO_TEXT_GROUPS = "⬅️ К списку текстов"
BACK_TO_LESSONS = "⬅️ К списку уроков"
LESSON_DONE = "✅ Выполнено"
LESSON_SKIP = "⏭️ Пропустить"
LESSON_QUESTION = "❓ Задать вопрос"
NEXT_LESSON = "➡️ Следующий урок"
WRITE_FEEDBACK = "📝 Написать отзыв"
SKIP_FEEDBACK = "Пропустить отзыв"
CANCEL_TEXT = "Отмена"
ADMIN_TEXTS_ENTRY = "📝 Тексты окон"

FEEDBACK_OPTIONS: dict[str, str] = {
    "Отлично": "excellent",
    "Хорошо": "good",
    "Нормально": "average",
    "Плохо": "poor",
}

# ──────────────────────────────────────────────────────────────────────────────
# Главное меню и разделы
# ──────────────────────────────────────────────────────────────────────────────
def main_menu_keyboard(
    *,
    is_admin: bool,
    has_pay: bool,
    payments_open: bool,
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text="ℹ️ О клубе"),
            KeyboardButton(text="🎓 Обучение"),
        ],
        [
            KeyboardButton(text="📦 Материалы"),
            KeyboardButton(text="👤 Профиль"),
        ],
        [
            KeyboardButton(text="🆘 Поддержка"),
        ],
    ]

    if has_pay:
        pay_text = "💳 Оплата" if payments_open else "🔒 Оплата"
        rows[-1].append(KeyboardButton(text=pay_text))

    if is_admin:
        rows.append([KeyboardButton(text="⚙️ Админка")])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


def info_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="О клубе"), KeyboardButton(text="FAQ")],
        [KeyboardButton(text="Правила")],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def learning_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Бесплатные уроки"), KeyboardButton(text="Мой прогресс")],
        [KeyboardButton(text="Записаться на разбор"), KeyboardButton(text="Пройти тест")],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def materials_menu_keyboard(
    *,
    weekly_enabled: bool,
    schedule_enabled: bool,
) -> ReplyKeyboardMarkup:
    weekly_text = "Материалы недели" if weekly_enabled else "Материалы недели 🔒"
    schedule_text = "Расписание" if schedule_enabled else "Расписание 🔒"
    rows = [
        [KeyboardButton(text=weekly_text)],
        [KeyboardButton(text=schedule_text)],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def profile_menu_keyboard(
    *,
    has_pay: bool,
    payments_open: bool,
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="Мой профиль")],
        [KeyboardButton(text="Изменить email"), KeyboardButton(text="Изменить телефон")],
    ]

    if has_pay:
        pay_text = "💳 Оплата" if payments_open else "🔒 Оплата"
        rows.append([KeyboardButton(text=pay_text)])

    rows.append([KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def lessons_overview_keyboard(next_available: int) -> ReplyKeyboardMarkup:
    titles = {
        1: "Введение",
        2: "Основы",
        3: "Практики",
        4: "Интеграция",
    }

    rows: list[list[KeyboardButton]] = []
    for i in range(1, 5):
        status = "✅" if i < next_available else ("⏳" if i == next_available else "🔒")
        rows.append([
            KeyboardButton(text=f"{status} Урок {i}: {titles.get(i, '')}")
        ])

    rows.append([KeyboardButton(text=BACK_TO_LEARNING)])
    rows.append([KeyboardButton(text=BACK_TO_MAIN)])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def lesson_actions_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=LESSON_DONE), KeyboardButton(text=LESSON_SKIP)],
        [KeyboardButton(text=LESSON_QUESTION)],
        [KeyboardButton(text=BACK_TO_LESSONS), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def after_lesson_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=NEXT_LESSON)],
        [KeyboardButton(text=BACK_TO_LESSONS), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def feedback_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=option) for option in ("Отлично", "Хорошо")],
        [KeyboardButton(text=option) for option in ("Нормально", "Плохо")],
        [KeyboardButton(text=WRITE_FEEDBACK)],
        [KeyboardButton(text=SKIP_FEEDBACK)],
        [KeyboardButton(text=BACK_TO_LESSONS)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_TEXT)]],
        resize_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def admin_main_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Управление пользователями"), KeyboardButton(text="Рассылка")],
        [KeyboardButton(text="Управление контентом"), KeyboardButton(text="Статистика")],
        [KeyboardButton(text="Диагностика"), KeyboardButton(text="Тонкие настройки")],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_settings_keyboard(
    flags: dict[str, bool],
    labels: dict[str, str],
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for key, label in labels.items():
        status = "✅" if flags.get(key, True) else "❌"
        rows.append([KeyboardButton(text=f"{status} {label}")])
    rows.append([KeyboardButton(text=ADMIN_TEXTS_ENTRY)])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_text_groups_keyboard(group_titles: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for title in group_titles:
        rows.append([KeyboardButton(text=title)])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_text_items_keyboard(options: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for label in options:
        rows.append([KeyboardButton(text=label)])
    rows.append([KeyboardButton(text=BACK_TO_TEXT_GROUPS)])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
