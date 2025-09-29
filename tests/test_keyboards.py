from keyboards import (
    ADMIN_BEHAVIOR_BUTTON,
    ADMIN_BEHAVIOR_ONBOARDING,
    ADMIN_BEHAVIOR_REGISTRATION,
    ADMIN_BEHAVIOR_START,
    ADMIN_BROADCAST_BUTTON,
    ADMIN_CONTENT_MENU,
    ADMIN_DEBUG_BUTTON,
    ADMIN_PAYMENTS_BUTTON,
    ADMIN_PAYMENTS_CLOSE_WINDOW,
    ADMIN_PAYMENTS_CONFIRM_ACCESS,
    ADMIN_PAYMENTS_MARK_FAILED,
    ADMIN_PAYMENTS_MARK_PAID,
    ADMIN_PAYMENTS_OPEN_WINDOW,
    ADMIN_PAYMENTS_REVOKE_ACCESS,
    ADMIN_PAYMENTS_SHOW_LATEST,
    ADMIN_SETTINGS_BUTTON,
    ADMIN_STATS_BUTTON,
    ADMIN_USERS_BUTTON,
    BACK_TO_ADMIN,
    BACK_TO_BEHAVIOR,
    BACK_TO_MAIN,
    admin_behavior_keyboard,
    admin_main_keyboard,
    admin_payments_keyboard,
)


def _keyboard_texts(markup):
    return [[button.text for button in row] for row in markup.keyboard]


def test_admin_main_keyboard_layout():
    rows = _keyboard_texts(admin_main_keyboard())
    assert rows == [
        [ADMIN_USERS_BUTTON],
        [ADMIN_BROADCAST_BUTTON, ADMIN_CONTENT_MENU],
        [ADMIN_BEHAVIOR_BUTTON, ADMIN_SETTINGS_BUTTON],
        [ADMIN_STATS_BUTTON, ADMIN_DEBUG_BUTTON],
        [BACK_TO_MAIN],
    ]
    flattened = [text for row in rows for text in row]
    assert ADMIN_PAYMENTS_BUTTON not in flattened


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
