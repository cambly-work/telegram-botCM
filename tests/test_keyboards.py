from keyboards import (
    ADMIN_BEHAVIOR_BUTTON,
    ADMIN_BEHAVIOR_ONBOARDING,
    ADMIN_BEHAVIOR_REGISTRATION,
    ADMIN_BEHAVIOR_START,
    ADMIN_CATEGORY_USERS,
    ADMIN_CATEGORY_CONTENT,
    ADMIN_CATEGORY_COMMUNICATIONS,
    ADMIN_CATEGORY_SERVICE,
    ADMIN_BROADCAST_BUTTON,
    ADMIN_SCHEDULE_BUTTON,
    ADMIN_BROADCAST_HISTORY_BUTTON,
    ADMIN_BROADCAST_NEW_BUTTON,
    ADMIN_BROADCAST_REMINDER_TEXT,
    ADMIN_CONTENT_MENU,
    ADMIN_TEXTS_ENTRY,
    ADMIN_DEBUG_BUTTON,
    ADMIN_MATERIALS_BUTTON,
    ADMIN_KEYS_BUTTON,
    ADMIN_MATERIALS_LIST,
    ADMIN_MATERIALS_CREATE,
    ADMIN_MATERIALS_UPDATE,
    ADMIN_MATERIALS_DELETE,
    ADMIN_MATERIALS_GRANT,
    ADMIN_MATERIALS_REVOKE,
    ADMIN_PAYMENTS_BUTTON,
    ADMIN_PAYMENTS_CLOSE_WINDOW,
    ADMIN_PAYMENTS_CONFIRM_ACCESS,
    ADMIN_PAYMENTS_MARK_FAILED,
    ADMIN_PAYMENTS_MARK_PAID,
    ADMIN_PAYMENTS_OPEN_WINDOW,
    ADMIN_PAYMENTS_REVOKE_ACCESS,
    ADMIN_PAYMENTS_SHOW_LATEST,
    ADMIN_MATERIALS_BUTTON,
    ADMIN_SETTINGS_BUTTON,
    ADMIN_STATS_BUTTON,
    ADMIN_USERS_BUTTON,
    ADMIN_USERS_EDIT_PROGRESS,
    ADMIN_USERS_BACK_TO_LIST,
    ADMIN_USERS_BACK_TO_SEGMENTS,
    ADMIN_USERS_DELETE_USER,
    ADMIN_USERS_CONFIRM_DELETE,
    BACK_TO_ADMIN,
    BACK_TO_BROADCAST,
    BACK_TO_BEHAVIOR,
    BACK_TO_MAIN,
    BACK_TO_MATERIALS,
    BROADCAST_ALL_BUTTON,
    BROADCAST_EXPIRED_BUTTON,
    BROADCAST_LEADS_BUTTON,
    BROADCAST_MEMBERS_BUTTON,
    BROADCAST_KEYS_BUTTON,
    BROADCAST_PRACTICE_BUTTON,
    BROADCAST_TEMPLATES_BUTTON,
    CANCEL_TEXT,
    LEARNING_PROGRESS_BUTTON,
    MATERIALS_CATALOG_BUTTON,
    analysis_confirm_keyboard,
    cancel_keyboard,
    materials_menu_keyboard,
    learning_menu_keyboard,
    profile_menu_keyboard,
    admin_behavior_keyboard,
    admin_broadcast_keyboard,
    admin_broadcast_segments_keyboard,
    admin_main_keyboard,
    admin_staff_keyboard,
    admin_users_category_keyboard,
    admin_content_category_keyboard,
    admin_communications_category_keyboard,
    admin_service_category_keyboard,
    admin_materials_keyboard,
    admin_materials_categories_keyboard,
    admin_payments_keyboard,
    admin_settings_keyboard,
    admin_user_card_keyboard,
    admin_user_delete_confirm_keyboard,
)


def _keyboard_texts(markup):
    return [[button.text for button in row] for row in markup.keyboard]


def test_admin_broadcast_keyboard_includes_status_flags():
    statuses = {
        "Напоминания анкет": True,
        "Напоминания уроков": False,
        "Напоминания об окончании доступа": True,
    }

    rows = _keyboard_texts(admin_broadcast_keyboard(statuses))

    assert rows[0] == [ADMIN_BROADCAST_NEW_BUTTON]
    assert rows[1] == [BROADCAST_TEMPLATES_BUTTON, ADMIN_BROADCAST_HISTORY_BUTTON]
    assert rows[2] == [ADMIN_BROADCAST_REMINDER_TEXT]
    assert rows[3] == ["✅ Напоминания анкет"]
    assert rows[4] == ["❌ Напоминания уроков"]
    assert rows[5] == ["✅ Напоминания об окончании доступа"]
    assert rows[6] == [BACK_TO_ADMIN, BACK_TO_MAIN]

    assert len(rows) == len(statuses) + 4

    flattened = [text for row in rows for text in row]
    assert BROADCAST_ALL_BUTTON not in flattened
    assert BROADCAST_LEADS_BUTTON not in flattened
    assert BROADCAST_MEMBERS_BUTTON not in flattened
    assert BROADCAST_EXPIRED_BUTTON not in flattened


def test_admin_main_keyboard_layout():
    rows = _keyboard_texts(admin_main_keyboard())
    assert rows == [
        [ADMIN_CATEGORY_USERS, ADMIN_CATEGORY_CONTENT],
        [ADMIN_CATEGORY_COMMUNICATIONS, ADMIN_CATEGORY_SERVICE],
        [BACK_TO_MAIN],
    ]
    flattened = [text for row in rows for text in row]
    assert ADMIN_PAYMENTS_BUTTON not in flattened
    assert ADMIN_CONTENT_MENU not in flattened
    assert ADMIN_STATS_BUTTON not in flattened


def test_admin_staff_keyboard_layout():
    rows = _keyboard_texts(admin_staff_keyboard())
    assert rows == [
        [ADMIN_STATS_BUTTON],
        [ADMIN_PAYMENTS_BUTTON],
        [BACK_TO_MAIN],
    ]


def test_admin_users_category_keyboard_layout():
    rows = _keyboard_texts(admin_users_category_keyboard())
    assert rows == [
        [ADMIN_USERS_BUTTON],
        [ADMIN_PAYMENTS_BUTTON],
        [ADMIN_KEYS_BUTTON],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_content_category_keyboard_layout():
    rows = _keyboard_texts(admin_content_category_keyboard())
    assert rows == [
        [ADMIN_CONTENT_MENU],
        [ADMIN_MATERIALS_BUTTON],
        [ADMIN_BEHAVIOR_BUTTON],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_communications_category_keyboard_layout():
    rows = _keyboard_texts(admin_communications_category_keyboard())
    assert rows == [
        [ADMIN_BROADCAST_BUTTON],
        [ADMIN_SCHEDULE_BUTTON],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_service_category_keyboard_layout():
    rows = _keyboard_texts(admin_service_category_keyboard())
    assert rows == [
        [ADMIN_STATS_BUTTON],
        [ADMIN_SETTINGS_BUTTON],
        [ADMIN_DEBUG_BUTTON],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_materials_keyboard_layout():
    rows = _keyboard_texts(admin_materials_keyboard())
    assert rows == [
        [ADMIN_CONTENT_MENU],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_materials_keyboard_layout():
    rows = _keyboard_texts(admin_materials_keyboard())
    assert rows == [
        [ADMIN_MATERIALS_LIST],
        [ADMIN_MATERIALS_CREATE, ADMIN_MATERIALS_UPDATE],
        [ADMIN_MATERIALS_DELETE],
        [ADMIN_MATERIALS_GRANT, ADMIN_MATERIALS_REVOKE],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_materials_categories_keyboard_appends_navigation():
    rows = _keyboard_texts(
        admin_materials_categories_keyboard(["podcasts", "archive.week1"])
    )
    assert rows[:-1] == [["podcasts"], ["archive.week1"]]
    assert rows[-1] == [BACK_TO_ADMIN, BACK_TO_MAIN]


def test_admin_behavior_keyboard_contains_payments_button():
    rows = _keyboard_texts(admin_behavior_keyboard())
    assert rows == [
        [ADMIN_BEHAVIOR_START],
        [ADMIN_BEHAVIOR_REGISTRATION],
        [ADMIN_BEHAVIOR_ONBOARDING],
        [ADMIN_PAYMENTS_BUTTON],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_payments_keyboard_back_navigation():
    rows_open = _keyboard_texts(admin_payments_keyboard(payments_open=True))
    assert rows_open[0] == [ADMIN_PAYMENTS_CLOSE_WINDOW]
    assert rows_open[1] == [ADMIN_PAYMENTS_SHOW_LATEST]
    assert rows_open[2] == [ADMIN_PAYMENTS_CONFIRM_ACCESS, ADMIN_PAYMENTS_REVOKE_ACCESS]
    assert rows_open[3] == [ADMIN_PAYMENTS_MARK_PAID, ADMIN_PAYMENTS_MARK_FAILED]
    assert rows_open[4] == [BACK_TO_BEHAVIOR, BACK_TO_ADMIN]
    assert rows_open[5] == [BACK_TO_MAIN]

    rows_closed = _keyboard_texts(admin_payments_keyboard(payments_open=False))
    assert rows_closed[0] == [ADMIN_PAYMENTS_OPEN_WINDOW]
    assert rows_closed[4] == [BACK_TO_BEHAVIOR, BACK_TO_ADMIN]
    assert rows_closed[5] == [BACK_TO_MAIN]


def test_admin_broadcast_segments_keyboard_layout():
    rows = _keyboard_texts(admin_broadcast_segments_keyboard())
    assert rows == [
        [BROADCAST_ALL_BUTTON, BROADCAST_LEADS_BUTTON],
        [BROADCAST_MEMBERS_BUTTON, BROADCAST_EXPIRED_BUTTON],
        [BROADCAST_KEYS_BUTTON],
        [BACK_TO_BROADCAST, BACK_TO_ADMIN],
        [BACK_TO_MAIN],
    ]


def test_materials_menu_keyboard_all_sections_available():
    rows = _keyboard_texts(
        materials_menu_keyboard(weekly_enabled=True, schedule_enabled=True)
    )
    assert rows == [
        ["Материалы недели", MATERIALS_CATALOG_BUTTON],
        ["Расписание"],
        [BACK_TO_MAIN],
    ]


def test_materials_menu_keyboard_root_shows_lock_icons():
    rows = _keyboard_texts(
        materials_menu_keyboard(weekly_enabled=False, schedule_enabled=False)
    )
    assert rows[0] == ["Материалы недели 🔒", MATERIALS_CATALOG_BUTTON]
    assert rows[1] == ["Расписание 🔒"]
    assert rows[2] == [BACK_TO_MAIN]


def test_materials_menu_keyboard_catalog_submenu_marks_state():
    submenu_items = [
        {"title": "Подкасты", "locked": False, "has_children": False},
        {"title": "Архив недель", "locked": True, "has_children": True},
    ]
    rows = _keyboard_texts(
        materials_menu_keyboard(
            weekly_enabled=True,
            schedule_enabled=True,
            submenu="catalog",
            submenu_items=submenu_items,
        )
    )
    assert rows[0] == ["Подкасты"]
    assert rows[1] == ["Архив недель 🔒"]
    assert rows[2] == [BACK_TO_MATERIALS]
    assert rows[3] == [BACK_TO_MAIN]


def test_admin_settings_keyboard_no_content_shortcuts():
    flags = {
        "payments_open": True,
        "payments_manual_review": False,
        "show_weekly_materials": True,
        "show_schedule": False,
        "notify_registration": True,
        "notify_form_analysis": False,
        "notify_form_test": True,
    }
    labels = {
        "payments_open": "Окно оплаты",
        "payments_manual_review": "Ручная проверка оплат",
        "show_weekly_materials": "Материалы недели",
        "show_schedule": "Расписание",
        "notify_registration": "Уведомления о регистрациях",
        "notify_form_analysis": "Уведомления о разборе",
        "notify_form_test": "Уведомления о тесте",
    }

    rows = _keyboard_texts(admin_settings_keyboard(flags, labels))

    assert rows[-1] == [BACK_TO_ADMIN, BACK_TO_MAIN]

    flattened = [text for row in rows for text in row]
    assert ADMIN_CONTENT_MENU not in flattened
    assert ADMIN_TEXTS_ENTRY not in flattened

    expected = [
        "✅ Окно оплаты",
        "❌ Ручная проверка оплат",
        "✅ Материалы недели",
        "❌ Расписание",
        "✅ Уведомления о регистрациях",
        "❌ Уведомления о разборе",
        "✅ Уведомления о тесте",
    ]
    assert flattened[: len(expected)] == expected


def test_profile_menu_keyboard_adds_progress_button():
    rows = _keyboard_texts(
        profile_menu_keyboard(has_pay=True, payments_open=True)
    )
    assert rows[0] == ["Мой профиль", LEARNING_PROGRESS_BUTTON]


def test_admin_user_card_keyboard_contains_progress_control():
    rows = _keyboard_texts(admin_user_card_keyboard())
    assert ADMIN_USERS_EDIT_PROGRESS in rows[1]


def test_admin_user_card_keyboard_contains_delete_button():
    rows = _keyboard_texts(admin_user_card_keyboard())
    flattened = [text for row in rows for text in row]
    assert ADMIN_USERS_DELETE_USER in flattened
    assert [ADMIN_USERS_BACK_TO_LIST, ADMIN_USERS_BACK_TO_SEGMENTS] in rows


def test_admin_user_delete_confirm_keyboard_layout():
    rows = _keyboard_texts(admin_user_delete_confirm_keyboard())
    assert rows[0] == [ADMIN_USERS_CONFIRM_DELETE]
    assert rows[1] == [ADMIN_USERS_BACK_TO_LIST, ADMIN_USERS_BACK_TO_SEGMENTS]
    assert rows[2] == [BACK_TO_ADMIN, BACK_TO_MAIN]


def test_cancel_keyboard_contains_cancel_button():
    rows = _keyboard_texts(cancel_keyboard())
    assert any(CANCEL_TEXT in row for row in rows)


def test_cancel_keyboard_allows_custom_text():
    custom = "Пропустить"
    rows = _keyboard_texts(cancel_keyboard(cancel_text=custom))
    assert any(custom in row for row in rows)


def test_analysis_confirm_keyboard_contains_cancel_button():
    rows = _keyboard_texts(analysis_confirm_keyboard())
    assert any(CANCEL_TEXT in row for row in rows)
