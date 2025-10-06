import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import handlers  # noqa: E402
from handlers.states import HWStates  # noqa: E402


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DummyState:
    def __init__(self) -> None:
        self._state = None
        self._data: dict = {}

    async def set_state(self, value):
        self._state = getattr(value, "state", value)

    async def get_state(self):
        return self._state

    async def update_data(self, **kwargs):
        self._data.update(kwargs)
        return dict(self._data)

    async def get_data(self):
        return dict(self._data)

    async def clear(self):
        self._state = None
        self._data = {}


class DummyFromUser:
    def __init__(self, user_id: int = 101, username: str = "student") -> None:
        self.id = user_id
        self.username = username
        self.full_name = "Test Student"
        self.first_name = "Test"


class DummyMessage:
    def __init__(self, text: str, from_user: DummyFromUser, events: list[tuple[str, str]]) -> None:
        self.text = text
        self.from_user = from_user
        self._events = events

    async def answer(self, text: str, **kwargs):
        self._events.append(("user", text))
        return None


def test_build_lesson_progress_bar_helpers():
    bar, completed = handlers._build_lesson_progress_bar({1: "submitted", 2: "pending", 3: "skipped"})
    assert bar == "▰▱▱▱"
    assert completed == 1
    assert "урок 2" in handlers._build_lesson_cta(2)
    assert "Все уроки" in handlers._build_lesson_cta(5)


async def test_lesson_done_sets_pending_state(monkeypatch):
    events: list[tuple[str, str]] = []
    test_user = DummyFromUser()
    message = DummyMessage(handlers.LESSON_DONE, test_user, events)
    state = DummyState()
    await state.update_data(active_lesson=1)

    user_row = {"id": 42, "full_name": test_user.full_name}

    async def fake_get_user(_: int):
        return user_row

    monkeypatch.setattr(handlers, "get_user_with_id", fake_get_user)

    pending_calls: list[tuple[int, int]] = []

    async def fake_mark_in_progress(user_id: int, lesson_num: int):
        pending_calls.append((user_id, lesson_num))

    monkeypatch.setattr(handlers, "mark_lesson_in_progress", fake_mark_in_progress)
    monkeypatch.setattr(handlers, "cancel_keyboard", lambda: "CANCEL")

    await handlers.lesson_mark_done(message, state)

    assert await state.get_state() == HWStates.waiting_answer.state
    assert pending_calls == [(42, 1)]
    assert any("ответ" in text.lower() for _, text in events)


async def test_question_flow_notifies_admins(monkeypatch):
    events: list[tuple[str, str]] = []
    test_user = DummyFromUser()
    ask_message = DummyMessage(handlers.LESSON_QUESTION, test_user, events)
    state = DummyState()
    await state.update_data(active_lesson=3)

    user_row = {"id": 84, "full_name": "Student"}

    async def fake_get_user(_: int):
        return user_row

    monkeypatch.setattr(handlers, "get_user_with_id", fake_get_user)
    async def fake_mark_in_progress(*args, **kwargs):
        return None

    monkeypatch.setattr(handlers, "mark_lesson_in_progress", fake_mark_in_progress)
    monkeypatch.setattr(handlers, "cancel_keyboard", lambda: "CANCEL")
    monkeypatch.setattr(handlers, "lesson_actions_keyboard", lambda: "ACTIONS")

    await handlers.lesson_question(ask_message, state)

    assert await state.get_state() == HWStates.waiting_question.state
    assert any("Задай вопрос" in text for _, text in events)

    notifications: list[str] = []

    async def fake_notify_admins(text: str):
        notifications.append(text)

    monkeypatch.setattr(handlers, "_get_notify_admins", lambda: fake_notify_admins)
    monkeypatch.setattr(handlers, "_notify_admins_cached", None, raising=False)

    question_message = DummyMessage("Как сделать задание?", test_user, events)
    await state.update_data(lesson_num=3)

    await handlers.lesson_receive_question(question_message, state)

    assert await state.get_state() is None
    assert notifications and "уроку 3" in notifications[0]
    assert any("Ответ придёт" in text for _, text in events)


def test_membership_summary_uses_russian_labels():
    summary = handlers._membership_summary(
        {
            "status": "member_active",
            "access_until": datetime(2024, 1, 31, tzinfo=timezone.utc),
        }
    )

    assert summary["status_label"] == "Активный доступ"
    assert summary["status_line"] == "Статус участия: Активный доступ"
    assert "Активный доступ" in summary["summary"]


async def test_send_profile_overview_formats_status_without_duplicates(monkeypatch):
    events: list[tuple[str, str]] = []
    test_user = DummyFromUser()
    message = DummyMessage("/profile", test_user, events)
    user_row = {
        "id": 1,
        "status": "member_active",
        "email": "user@example.com",
        "phone": "+7 900 000-00-00",
        "name": "Тест",
        "full_name": "Тестовая Пользовательница",
        "access_until": datetime(2024, 1, 31, tzinfo=timezone.utc),
    }

    async def fake_keyboard(**kwargs):
        return "KEYBOARD"

    async def fake_weekly_keys(user_id):
        assert user_id == user_row["id"]
        return []

    monkeypatch.setattr(handlers, "build_menu_keyboard", fake_keyboard)
    monkeypatch.setattr(handlers, "list_weekly_keys_for_user", fake_weekly_keys)

    await handlers.send_profile_overview(message, user_row, False)

    assert events, "profile overview should send a message"
    profile_text = events[-1][1]
    assert "Статус: Активный доступ" in profile_text
    assert "Активный доступ (" not in profile_text
