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
BACK_TO_BEHAVIOR = "⬅️ К геймификации"
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
ADMIN_CONTENT_HISTORY = "🕘 История версий"
ADMIN_CONTENT_TAGS_HELP = "ℹ️ Форматирование текста"
ADMIN_CONTENT_SAVE_TEMPLATE_BUTTON = "📥 Сохранить шаблон"
ADMIN_CONTENT_SUGGEST_MORE = "🔁 Ещё варианты"
ADMIN_CONTENT_ROLLBACK_PREFIX = "↩️ Откатить"
ADMIN_CONTENT_EXPORT = "⬇️ Экспорт"
ADMIN_CONTENT_IMPORT = "⬆️ Импорт"
ADMIN_CATEGORY_USERS = "👥 Пользователи"
ADMIN_CATEGORY_CONTENT = "🧾 Контент"
ADMIN_CATEGORY_COMMUNICATIONS = "📣 Коммуникации"
ADMIN_CATEGORY_SERVICE = "🛠️ Служебное"

ADMIN_USERS_BUTTON = "📋 Управление участницами (участниками)"
ADMIN_SCHEDULE_BUTTON = "📆 Расписание"
ADMIN_SCHEDULE_ADD_EVENT = "➕ Добавить событие"
ADMIN_SCHEDULE_EDIT_EVENT = "✏️ Изменить событие"
ADMIN_SCHEDULE_ARCHIVE_EVENT = "🗄️ Архивировать событие"
ADMIN_SCHEDULE_RESTORE_EVENT = "♻️ Восстановить событие"
ADMIN_SCHEDULE_SHOW_ARCHIVE = "📂 Архив событий"
ADMIN_SCHEDULE_SHOW_ACTIVE = "📅 Активные события"
ADMIN_USERS_SEGMENT_LEADS = "🎯 Лиды"
ADMIN_USERS_SEGMENT_ACTIVE = "🔥 Активные"
ADMIN_USERS_SEGMENT_EXPIRED = "🧊 Завершившие"
ADMIN_USERS_PAGE_PREV = "⬅️ Предыдущие"
ADMIN_USERS_PAGE_NEXT = "➡️ Следующие"
ADMIN_USERS_BACK_TO_SEGMENTS = "📋 Сегменты"
ADMIN_USERS_BACK_TO_LIST = "📋 К списку"
ADMIN_USERS_GRANT_ACCESS = "✅ Выдать доступ"
ADMIN_USERS_REVOKE_ACCESS = "🚫 Отозвать доступ"
ADMIN_USERS_UPDATE_CONTACTS = "✏️ Обновить контакты"
ADMIN_MATERIALS_BUTTON = "📚 Материалы"
ADMIN_BROADCAST_BUTTON = "📣 Рассылки"
ADMIN_STATS_BUTTON = "📊 Статистика"
ADMIN_STATS_REFRESH = "🔄 Обновить сводку"
ADMIN_STATS_USERS_BREAKDOWN = "📋 Статусы пользователей"
ADMIN_STATS_LESSON_PROGRESS = "🎯 Прогресс уроков"
ADMIN_STATS_PAYMENTS_BREAKDOWN = "💰 Статистика оплат"
ADMIN_STATS_RECENT_PAYMENTS = "🧾 Последние оплаты"
ADMIN_STATS_FORMS_BREAKDOWN = "🗂 Формы и консультации"
ADMIN_DEBUG_BUTTON = "🛠️ Диагностика"
ADMIN_SETTINGS_BUTTON = "⚙️ Настройки"
ADMIN_PAYMENTS_BUTTON = "💳 Оплаты"
ADMIN_MATERIALS_BUTTON = "📚 Материалы"
ADMIN_KEYS_BUTTON = "🔑 Ключи"
ADMIN_BEHAVIOR_BUTTON = "🎛 Логика бота"
ADMIN_BROADCAST_REMINDER_TEXT = "✏️ Текст напоминаний"
ADMIN_BROADCAST_NEW_BUTTON = "🆕 Новая рассылка"
ADMIN_BROADCAST_HISTORY_BUTTON = "📜 История рассылок"
BROADCAST_HISTORY_MORE_BUTTON = "➕ Ещё"

ADMIN_MATERIALS_LIST = "📂 Список категорий"
ADMIN_MATERIALS_CREATE = "➕ Добавить категорию"
ADMIN_MATERIALS_UPDATE = "✏️ Изменить категорию"
ADMIN_MATERIALS_DELETE = "🗑️ Удалить категорию"
ADMIN_MATERIALS_GRANT = "✅ Выдать доступ"
ADMIN_MATERIALS_REVOKE = "🚫 Отозвать доступ"

ADMIN_KEYS_BULK_GRANT = "🎁 Массовая выдача"
ADMIN_KEYS_REVOKE = "🔄 Отозвать ключ"
ADMIN_KEYS_UPLOAD = "⬆️ Загрузить описания"

ADMIN_BEHAVIOR_START = "✉️ Приветствие /start"
ADMIN_BEHAVIOR_REGISTRATION = "✅ Сообщение после регистрации"
ADMIN_BEHAVIOR_ONBOARDING = "🚀 Шаги онбординга"

ADD_ONBOARDING_STEP = "➕ Добавить шаг"
DELETE_ONBOARDING_STEP = "🗑️ Удалить шаг"

BROADCAST_ALL_BUTTON = "📣 Всем"
BROADCAST_LEADS_BUTTON = "🎯 Лиды"
BROADCAST_MEMBERS_BUTTON = "🔥 Активные"
BROADCAST_EXPIRED_BUTTON = "🧊 Завершившие"
BROADCAST_KEYS_BUTTON = "🔑 Ключи"
BROADCAST_PRACTICE_BUTTON = "🧘 Практика"
BROADCAST_TEMPLATES_BUTTON = "🗂 Шаблоны рассылок"
BROADCAST_TEMPLATE_PREFIX = "🗂 Шаблон: "

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

LEARNING_PROGRESS_BUTTON = "Мой прогресс"
ADMIN_USERS_EDIT_PROGRESS = "📈 Обновить прогресс"
MATERIALS_CATALOG_BUTTON = "Каталог материалов"
MATERIALS_PODCASTS_BUTTON = "Подкасты"
MATERIALS_PRACTICES_BUTTON = "Практики"
MATERIALS_CHALLENGES_BUTTON = "Челленджи"
MATERIALS_ARCHIVE_BUTTON = "Архив недель"

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
        [
            KeyboardButton(text="Бесплатные уроки"),
            KeyboardButton(text=LEARNING_PROGRESS_BUTTON),
        ],
        [
            KeyboardButton(text="Окно в Магнетизм"),
            KeyboardButton(text="Записаться на разбор"),
        ],
        [KeyboardButton(text="Пройти тест")],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def materials_menu_keyboard(
    *,
    weekly_enabled: bool,
    schedule_enabled: bool,
    submenu: str | None = None,
    submenu_items: list[dict] | None = None,
) -> ReplyKeyboardMarkup:
    weekly_text = "Материалы недели" if weekly_enabled else "Материалы недели 🔒"
    schedule_text = "Расписание" if schedule_enabled else "Расписание 🔒"

    if submenu:
        rows: list[list[KeyboardButton]] = []
        for item in submenu_items or []:
            title = item.get("title", "")
            locked = item.get("locked", False)
            has_children = item.get("has_children", False)
            label = title
            if locked:
                label = f"{label} 🔒"
            elif has_children:
                label = f"{label} ▶️"
            rows.append([KeyboardButton(text=label)])

        rows.append([KeyboardButton(text=BACK_TO_MATERIALS)])
        rows.append([KeyboardButton(text=BACK_TO_MAIN)])

        placeholder_map = {
            "catalog": "Каталог материалов",
        }
        placeholder = placeholder_map.get(submenu, "Выбери материалы")
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=True,
            input_field_placeholder=placeholder,
        )

    rows = [
        [
            KeyboardButton(text=weekly_text),
            KeyboardButton(text=MATERIALS_CATALOG_BUTTON),
        ],
        [KeyboardButton(text=schedule_text)],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Раздел «Материалы»",
    )


def profile_menu_keyboard(
    *,
    has_pay: bool,
    payments_open: bool,
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text="Мой профиль"),
            KeyboardButton(text=LEARNING_PROGRESS_BUTTON),
        ],
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


def cancel_keyboard(*, extra_buttons: list[str] | None = None) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if extra_buttons:
        rows.append([KeyboardButton(text=btn) for btn in extra_buttons])
    rows.append([KeyboardButton(text=CANCEL_TEXT)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


ADMIN_PAYMENTS_OPEN_WINDOW = "🔓 Открыть окно оплат"
ADMIN_PAYMENTS_CLOSE_WINDOW = "🔒 Закрыть окно оплат"
ADMIN_PAYMENTS_SHOW_LATEST = "🧾 Последние платежи"
ADMIN_PAYMENTS_CONFIRM_ACCESS = "✅ Подтвердить доступ"
ADMIN_PAYMENTS_REVOKE_ACCESS = "🚫 Приостановить доступ"
ADMIN_PAYMENTS_MARK_PAID = "☑️ Отметить платёж"
ADMIN_PAYMENTS_MARK_FAILED = "❗ Пометить как ошибку"


def admin_main_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(text=ADMIN_CATEGORY_USERS),
            KeyboardButton(text=ADMIN_CATEGORY_CONTENT),
        ],
        [
            KeyboardButton(text=ADMIN_CATEGORY_COMMUNICATIONS),
            KeyboardButton(text=ADMIN_CATEGORY_SERVICE),
        ],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Админ-панель — выберите категорию",
    )


def admin_users_category_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_USERS_BUTTON)],
        [KeyboardButton(text=ADMIN_PAYMENTS_BUTTON)],
        [KeyboardButton(text=ADMIN_KEYS_BUTTON)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_content_category_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_CONTENT_MENU)],
        [KeyboardButton(text=ADMIN_MATERIALS_BUTTON)],
        [KeyboardButton(text=ADMIN_BEHAVIOR_BUTTON)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_communications_category_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_BROADCAST_BUTTON)],
        [KeyboardButton(text=ADMIN_SCHEDULE_BUTTON)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_service_category_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_STATS_BUTTON)],
        [KeyboardButton(text=ADMIN_SETTINGS_BUTTON)],
        [KeyboardButton(text=ADMIN_DEBUG_BUTTON)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_materials_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_MATERIALS_LIST)],
        [KeyboardButton(text=ADMIN_MATERIALS_CREATE), KeyboardButton(text=ADMIN_MATERIALS_UPDATE)],
        [KeyboardButton(text=ADMIN_MATERIALS_DELETE)],
        [KeyboardButton(text=ADMIN_MATERIALS_GRANT), KeyboardButton(text=ADMIN_MATERIALS_REVOKE)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_keys_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_KEYS_BULK_GRANT)],
        [KeyboardButton(text=ADMIN_KEYS_REVOKE)],
        [KeyboardButton(text=ADMIN_KEYS_UPLOAD)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_materials_categories_keyboard(categories: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=slug)] for slug in categories
    ]

    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_stats_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_STATS_REFRESH)],
        [KeyboardButton(text=ADMIN_STATS_USERS_BREAKDOWN)],
        [KeyboardButton(text=ADMIN_STATS_LESSON_PROGRESS)],
        [KeyboardButton(text=ADMIN_STATS_PAYMENTS_BREAKDOWN)],
        [KeyboardButton(text=ADMIN_STATS_RECENT_PAYMENTS)],
        [KeyboardButton(text=ADMIN_STATS_FORMS_BREAKDOWN)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_users_segments_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_USERS_SEGMENT_LEADS)],
        [KeyboardButton(text=ADMIN_USERS_SEGMENT_ACTIVE)],
        [KeyboardButton(text=ADMIN_USERS_SEGMENT_EXPIRED)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_users_pagination_keyboard(
    user_buttons: list[str],
    *,
    has_prev: bool,
    has_next: bool,
) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [[KeyboardButton(text=text)] for text in user_buttons]

    nav_row: list[KeyboardButton] = []
    if has_prev:
        nav_row.append(KeyboardButton(text=ADMIN_USERS_PAGE_PREV))
    nav_row.append(KeyboardButton(text=ADMIN_USERS_BACK_TO_SEGMENTS))
    if has_next:
        nav_row.append(KeyboardButton(text=ADMIN_USERS_PAGE_NEXT))

    rows.append(nav_row)
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_user_card_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [
            KeyboardButton(text=ADMIN_USERS_GRANT_ACCESS),
            KeyboardButton(text=ADMIN_USERS_REVOKE_ACCESS),
        ],
        [
            KeyboardButton(text=ADMIN_USERS_UPDATE_CONTACTS),
            KeyboardButton(text=ADMIN_USERS_EDIT_PROGRESS),
        ],
        [KeyboardButton(text=ADMIN_USERS_BACK_TO_LIST)],
        [KeyboardButton(text=ADMIN_USERS_BACK_TO_SEGMENTS)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_schedule_keyboard(*, archive_mode: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if not archive_mode:
        rows.append([KeyboardButton(text=ADMIN_SCHEDULE_ADD_EVENT)])
        rows.append([
            KeyboardButton(text=ADMIN_SCHEDULE_EDIT_EVENT),
            KeyboardButton(text=ADMIN_SCHEDULE_ARCHIVE_EVENT),
        ])
        rows.append([KeyboardButton(text=ADMIN_SCHEDULE_SHOW_ARCHIVE)])
    else:
        rows.append([KeyboardButton(text=ADMIN_SCHEDULE_RESTORE_EVENT)])
        rows.append([KeyboardButton(text=ADMIN_SCHEDULE_SHOW_ACTIVE)])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_behavior_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_BEHAVIOR_START)],
        [KeyboardButton(text=ADMIN_BEHAVIOR_REGISTRATION)],
        [KeyboardButton(text=ADMIN_BEHAVIOR_ONBOARDING)],
        [KeyboardButton(text=ADMIN_PAYMENTS_BUTTON)],
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


def admin_broadcast_keyboard(status_flags: dict[str, bool]) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_BROADCAST_NEW_BUTTON)],
        [KeyboardButton(text=BROADCAST_TEMPLATES_BUTTON), KeyboardButton(text=ADMIN_BROADCAST_HISTORY_BUTTON)],
        [KeyboardButton(text=ADMIN_BROADCAST_REMINDER_TEXT)],
    ]
    for label, enabled in status_flags.items():
        status = "✅" if enabled else "❌"
        rows.append([KeyboardButton(text=f"{status} {label}")])
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_broadcast_segments_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BROADCAST_ALL_BUTTON), KeyboardButton(text=BROADCAST_LEADS_BUTTON)],
        [KeyboardButton(text=BROADCAST_MEMBERS_BUTTON), KeyboardButton(text=BROADCAST_EXPIRED_BUTTON)],
        [KeyboardButton(text=BROADCAST_KEYS_BUTTON)],
        [KeyboardButton(text=BACK_TO_BROADCAST), KeyboardButton(text=BACK_TO_ADMIN)],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_broadcast_history_keyboard(*, has_more: bool) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if has_more:
        rows.append([KeyboardButton(text=BROADCAST_HISTORY_MORE_BUTTON)])
    rows.append([KeyboardButton(text=BACK_TO_BROADCAST), KeyboardButton(text=BACK_TO_ADMIN)])
    rows.append([KeyboardButton(text=BACK_TO_MAIN)])
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
        rows.append([KeyboardButton(text=f"{BROADCAST_TEMPLATE_PREFIX}{title}")])
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
    rows.append([KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_payments_keyboard(*, payments_open: bool) -> ReplyKeyboardMarkup:
    toggle_text = (
        ADMIN_PAYMENTS_CLOSE_WINDOW if payments_open else ADMIN_PAYMENTS_OPEN_WINDOW
    )
    rows = [
        [KeyboardButton(text=toggle_text)],
        [KeyboardButton(text=ADMIN_PAYMENTS_SHOW_LATEST)],
        [
            KeyboardButton(text=ADMIN_PAYMENTS_CONFIRM_ACCESS),
            KeyboardButton(text=ADMIN_PAYMENTS_REVOKE_ACCESS),
        ],
        [
            KeyboardButton(text=ADMIN_PAYMENTS_MARK_PAID),
            KeyboardButton(text=ADMIN_PAYMENTS_MARK_FAILED),
        ],
        [KeyboardButton(text=BACK_TO_BEHAVIOR), KeyboardButton(text=BACK_TO_ADMIN)],
        [KeyboardButton(text=BACK_TO_MAIN)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_content_keyboard(*, include_save_template: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=ADMIN_TEXTS_ENTRY)],
    ]

    if include_save_template:
        rows.append([KeyboardButton(text=ADMIN_CONTENT_SAVE_TEMPLATE_BUTTON)])

    rows.extend([
        [
            KeyboardButton(text=ADMIN_CONTENT_VIEW),
            KeyboardButton(text=ADMIN_CONTENT_CREATE),
        ],
        [KeyboardButton(text=ADMIN_CONTENT_HISTORY)],
        [
            KeyboardButton(text=ADMIN_CONTENT_EXPORT),
            KeyboardButton(text=ADMIN_CONTENT_IMPORT),
        ],
        [KeyboardButton(text=ADMIN_CONTENT_TAGS_HELP)],
        [KeyboardButton(text=BACK_TO_ADMIN), KeyboardButton(text=BACK_TO_MAIN)],
    ])
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


def admin_content_versions_keyboard(options_count: int) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []

    for idx in range(1, options_count + 1):
        rows.append([KeyboardButton(text=f"{ADMIN_CONTENT_ROLLBACK_PREFIX} {idx}")])

    rows.append([KeyboardButton(text=CANCEL_TEXT)])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
