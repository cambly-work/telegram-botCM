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
BACK_TO_BEHAVIOR = "⬅️ К логике бота"
BACK_TO_ONBOARDING = "⬅️ К шагам онбординга"
LESSON_DONE = "✅ Выполнено"
LESSON_SKIP = "⏭️ Пропустить"
LESSON_QUESTION = "❓ Задать вопрос"
NEXT_LESSON = "➡️ Следующий урок"
WRITE_FEEDBACK = "📝 Написать отзыв"
SKIP_FEEDBACK = "Пропустить отзыв"
CANCEL_TEXT = "Отмена"
ADMIN_TEXTS_ENTRY = "📄 Тексты экранов"
ADMIN_CONTENT_MENU = "🧾 Контент и тексты"
ADMIN_CONTENT_VIEW = "🔍 Посмотреть текст"
ADMIN_CONTENT_CREATE = "➕ Добавить или обновить текст"
ADMIN_CONTENT_SUGGEST_MORE = "🔁 Ещё варианты"
ADMIN_USERS_BUTTON = "👥 Пользователи"
ADMIN_BROADCAST_BUTTON = "📢 Рассылка"
ADMIN_STATS_BUTTON = "📊 Статистика"
ADMIN_DEBUG_BUTTON = "🛠️ Диагностика"
ADMIN_SETTINGS_BUTTON = "⚙️ Настройки"
ADMIN_BEHAVIOR_BUTTON = "🎛 Логика бота"

ADMIN_BEHAVIOR_START = "✉️ Приветствие /start"
ADMIN_BEHAVIOR_REGISTRATION = "✅ Сообщение после регистрации"
ADMIN_BEHAVIOR_ONBOARDING = "🚀 Шаги онбординга"

ADD_ONBOARDING_STEP = "➕ Добавить шаг"
DELETE_ONBOARDING_STEP = "🗑️ Удалить шаг"

BROADCAST_ALL_BUTTON = "📣 Всем"
BROADCAST_LEADS_BUTTON = "🎯 Лиды"
BROADCAST_MEMBERS_BUTTON = "🔥 Активные"
BROADCAST_EXPIRED_BUTTON = "🧊 Завершившие"
BROADCAST_TEMPLATES_BUTTON = "🗂 Шаблоны рассылок"

SEND_BROADCAST_BUTTON = "🚀 Отправить"
EDIT_BROADCAST_BUTTON = "✏️ Изменить текст"
SAVE_BROADCAST_TEMPLATE_BUTTON = "💾 Сохранить шаблон"
CHANGE_BROADCAST_SEGMENT_BUTTON = "🌐 Изменить сегмент"
BACK_TO_BROADCAST = "⬅️ К сегментам"
DELETE_BROADCAST_TEMPLATE_BUTTON = "🗑️ Удалить шаблон"

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


def lesson_keyboard(lesson_num: int) -> ReplyKeyboardMarkup:
    """Alias for the основной клавиатуры урока.

    Планировщик использует эту функцию, поэтому оставляем совместимый
    интерфейс с номером урока на будущее (можно будет расширить поведение
    в зависимости от номера урока).
    """

    # Пока для всех уроков клавиатура одинакова, поэтому просто
    # возвращаем базовую клавиатуру действий.
    return lesson_actions_keyboard()


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
        [KeyboardButton(text=ADMIN_USERS_BUTTON), KeyboardButton(text=ADMIN_BROADCAST_BUTTON)],
        [KeyboardButton(text=ADMIN_CONTENT_MENU), KeyboardButton(text=ADMIN_BEHAVIOR_BUTTON)],
        [KeyboardButton(text=ADMIN_STATS_BUTTON), KeyboardButton(text=ADMIN_DEBUG_BUTTON)],
        [KeyboardButton(text=ADMIN_SETTINGS_BUTTON)],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Админ-панель — выберите раздел",
    )


def admin_behavior_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_BEHAVIOR_START)],
        [KeyboardButton(text=ADMIN_BEHAVIOR_REGISTRATION)],
        [KeyboardButton(text=ADMIN_BEHAVIOR_ONBOARDING)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_onboarding_steps_keyboard(steps: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for idx, _ in enumerate(steps, start=1):
        rows.append([KeyboardButton(text=f"✏️ Шаг {idx}")])
    rows.append([KeyboardButton(text=ADD_ONBOARDING_STEP)])
    if steps:
        rows.append([KeyboardButton(text=DELETE_ONBOARDING_STEP)])
    rows.append([KeyboardButton(text=BACK_TO_BEHAVIOR), KeyboardButton(text=BACK_TO_ADMIN)])
    rows.append([KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_onboarding_delete_keyboard(steps: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for idx, _ in enumerate(steps, start=1):
        rows.append([KeyboardButton(text=f"🗑️ Шаг {idx}")])
    rows.append([KeyboardButton(text=BACK_TO_ONBOARDING)])
    rows.append([KeyboardButton(text=BACK_TO_BEHAVIOR), KeyboardButton(text=BACK_TO_ADMIN)])
    rows.append([KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_broadcast_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BROADCAST_ALL_BUTTON), KeyboardButton(text=BROADCAST_LEADS_BUTTON)],
        [KeyboardButton(text=BROADCAST_MEMBERS_BUTTON), KeyboardButton(text=BROADCAST_EXPIRED_BUTTON)],
        [KeyboardButton(text=BROADCAST_TEMPLATES_BUTTON)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_broadcast_confirm_keyboard(include_change_segment: bool = True) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=SEND_BROADCAST_BUTTON)],
        [KeyboardButton(text=EDIT_BROADCAST_BUTTON), KeyboardButton(text=SAVE_BROADCAST_TEMPLATE_BUTTON)],
    ]
    if include_change_segment:
        rows.append([KeyboardButton(text=CHANGE_BROADCAST_SEGMENT_BUTTON)])
    rows.append([KeyboardButton(text=BACK_TO_BROADCAST), KeyboardButton(text=BACK_TO_ADMIN)])
    rows.append([KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_broadcast_templates_keyboard(titles: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for title in titles:
        rows.append([KeyboardButton(text=f"📄 {title}")])
    if titles:
        rows.append([KeyboardButton(text=DELETE_BROADCAST_TEMPLATE_BUTTON)])
    rows.append([KeyboardButton(text=BACK_TO_BROADCAST), KeyboardButton(text=BACK_TO_ADMIN)])
    rows.append([KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_broadcast_delete_keyboard(titles: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for title in titles:
        rows.append([KeyboardButton(text=f"🗑️ {title}")])
    rows.append([KeyboardButton(text=BACK_TO_BROADCAST)])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_settings_keyboard(
    flags: dict[str, bool],
    labels: dict[str, str],
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for key, label in labels.items():
        status = "✅" if flags.get(key, True) else "❌"
        rows.append([KeyboardButton(text=f"{status} {label}")])
    rows.append([
        KeyboardButton(text=ADMIN_CONTENT_MENU),
        KeyboardButton(text=ADMIN_TEXTS_ENTRY),
    ])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_content_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_TEXTS_ENTRY)],
        [
            KeyboardButton(text=ADMIN_CONTENT_VIEW),
            KeyboardButton(text=ADMIN_CONTENT_CREATE),
        ],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_text_groups_keyboard(group_titles: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for title in group_titles:
        rows.append([KeyboardButton(text=title)])
    rows.append([KeyboardButton(text=ADMIN_CONTENT_MENU)])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_text_items_keyboard(options: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for label in options:
        rows.append([KeyboardButton(text=label)])
    rows.append([KeyboardButton(text=BACK_TO_TEXT_GROUPS)])
    rows.append([KeyboardButton(text=ADMIN_CONTENT_MENU)])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_content_suggestions_keyboard(
    options: list[str],
    *,
    show_more: bool = False,
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []

    for i in range(0, len(options), 2):
        chunk = options[i:i + 2]
        rows.append([KeyboardButton(text=opt) for opt in chunk])

    if show_more:
        rows.append([KeyboardButton(text=ADMIN_CONTENT_SUGGEST_MORE)])

    rows.append([KeyboardButton(text=CANCEL_TEXT)])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
