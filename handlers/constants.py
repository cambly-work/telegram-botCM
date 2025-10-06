"""Core constants used across bot handlers."""
from collections import OrderedDict

TELEGRAM_MESSAGE_LIMIT = 4096

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

ANALYSIS_REQUEST_STATUS_LABELS: dict[str, str] = OrderedDict(
    (
        ("new", "Новая"),
        ("scheduled", "Запланирована"),
        ("in_progress", "В работе"),
        ("done", "Завершена"),
        ("archived", "В архиве"),
        ("deleted", "Удалена"),
    )
)
ANALYSIS_REQUEST_STATUS_ORDER: tuple[str, ...] = tuple(ANALYSIS_REQUEST_STATUS_LABELS)
ANALYSIS_REQUEST_CLOSED_STATUSES: set[str] = {"archived", "deleted"}

WEEKLY_KEY_STATUS_ACTIVE = "active"
USER_KEY_STATUS_AVAILABLE = "available"
USER_KEY_STATUS_CLAIMED = "claimed"
USER_KEY_STATUS_REVOKED = "revoked"
SYSTEM_ADMIN_ACTOR = 0

_ADMIN_SETTINGS_DEFAULTS: dict[str, bool] = {
    "payments_open": True,
    "payments_manual_review": False,
    "show_weekly_materials": True,
    "show_schedule": True,
    "notify_registration": True,
    "notify_form_analysis": True,
    "notify_form_test": True,
}

_ADMIN_BROADCAST_SETTINGS_DEFAULTS: dict[str, bool] = {
    "broadcast_form_reminders_enabled": True,
    "broadcast_soft_reminders_enabled": True,
    "broadcast_access_expiry_enabled": True,
}

_ADMIN_BROADCAST_SETTINGS_LABELS: dict[str, str] = {
    "broadcast_form_reminders_enabled": "Напоминания анкет",
    "broadcast_soft_reminders_enabled": "Напоминания уроков",
    "broadcast_access_expiry_enabled": "Напоминания об окончании доступа",
}

_ADMIN_SETTINGS_LABELS: dict[str, str] = {
    "payments_open": "Окно оплаты",
    "payments_manual_review": "Ручная проверка оплат",
    "show_weekly_materials": "Материалы недели",
    "show_schedule": "Расписание",
    "notify_registration": "Уведомления о регистрациях",
    "notify_form_analysis": "Уведомления о разборе",
    "notify_form_test": "Уведомления о тесте",
}

_ADMIN_SETTINGS_STATUS_TEXTS: dict[str, tuple[str, str]] = {
    "payments_open": ("открыто", "закрыто"),
    "payments_manual_review": ("включена", "выключена"),
    "show_weekly_materials": ("доступны", "скрыты"),
    "show_schedule": ("показывается", "скрыто"),
    "notify_registration": ("включены", "выключены"),
    "notify_form_analysis": ("включены", "выключены"),
    "notify_form_test": ("включены", "выключены"),
}

_FORM_NOTIFY_FLAGS: dict[str, str] = {
    FORM_SLUG_ANALYSIS: "notify_form_analysis",
    FORM_SLUG_TEST: "notify_form_test",
}

__all__ = [
    "TELEGRAM_MESSAGE_LIMIT",
    "FORM_SLUG_ANALYSIS",
    "FORM_SLUG_TEST",
    "FORM_LABELS",
    "FORM_ALIASES",
    "ANALYSIS_REQUEST_STATUS_LABELS",
    "ANALYSIS_REQUEST_STATUS_ORDER",
    "ANALYSIS_REQUEST_CLOSED_STATUSES",
    "WEEKLY_KEY_STATUS_ACTIVE",
    "USER_KEY_STATUS_AVAILABLE",
    "USER_KEY_STATUS_CLAIMED",
    "USER_KEY_STATUS_REVOKED",
    "SYSTEM_ADMIN_ACTOR",
    "_ADMIN_SETTINGS_DEFAULTS",
    "_ADMIN_BROADCAST_SETTINGS_DEFAULTS",
    "_ADMIN_BROADCAST_SETTINGS_LABELS",
    "_ADMIN_SETTINGS_LABELS",
    "_ADMIN_SETTINGS_STATUS_TEXTS",
    "_FORM_NOTIFY_FLAGS",
]
