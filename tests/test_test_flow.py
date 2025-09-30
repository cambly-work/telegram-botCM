import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import handlers  # noqa: E402


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
    def __init__(self, user_id: int = 555) -> None:
        self.id = user_id
        self.username = "tester"
        self.full_name = "Test User"
        self.first_name = "Test"


class DummyMessage:
    def __init__(self, text: str, from_user: DummyFromUser, events: list[tuple[str, str]]) -> None:
        self.text = text
        self.from_user = from_user
        self._events = events

    async def answer(self, text: str, **kwargs):
        self._events.append(("user", text))
        return None


def test_test_flow_sequence(monkeypatch):
    async def run_flow():
        events: list[tuple[str, str]] = []
        test_user = DummyFromUser()
        user_row = {"id": 42, "tg_user_id": test_user.id, "full_name": test_user.full_name}

        saved_requests: list[tuple[int, int | None, date, str]] = []
        started_calls: list[tuple[int, str]] = []
        notifications: list[str] = []

        async def fake_get_user_and_admin(message):
            return user_row, False

        async def fake_build_menu_keyboard(**kwargs):
            return "KB"

        async def fake_mark_form_started(user_id: int, slug: str | None):
            if user_id and slug:
                started_calls.append((user_id, slug))

        async def fake_upsert_test_request(
            *, tg_user_id: int, user_id: int | None, birthdate: date, preferred_name: str | None
        ):
            saved_requests.append((tg_user_id, user_id, birthdate, preferred_name or ""))
            return {
                "tg_user_id": tg_user_id,
                "user_id": user_id,
                "birthdate": birthdate,
                "preferred_name": preferred_name,
            }

        async def fake_notify_admins(text: str):
            notifications.append(text)
            events.append(("admin", text))

        content_map = {
            "menu.test": "Intro base",
            "menu.test_intro": "Intro override",
            "menu.test_birthdate_prompt": "Birth prompt",
            "menu.test_birthdate_invalid": "Invalid {RAW}",
            "menu.test_name_prompt": "Name prompt",
            "menu.test_name_invalid": "Bad name",
            "menu.test_thanks": "Thanks, {name}! Birth: {birthdate}",
        }

        async def fake_get_content(key: str, default: str = ""):
            return content_map.get(key, default)

        monkeypatch.setattr(handlers, "_get_user_and_admin", fake_get_user_and_admin)
        monkeypatch.setattr(handlers, "build_menu_keyboard", fake_build_menu_keyboard)
        monkeypatch.setattr(handlers, "mark_form_started", fake_mark_form_started)
        monkeypatch.setattr(handlers, "upsert_test_request", fake_upsert_test_request)
        monkeypatch.setattr(handlers, "get_content", fake_get_content)
        monkeypatch.setattr(handlers, "cancel_keyboard", lambda: "CANCEL")
        monkeypatch.setattr(handlers, "_notify_admins_cached", fake_notify_admins, raising=False)

        state = DummyState()
        start_message = DummyMessage("Пройти тест", test_user, events)

        await handlers.menu_test(start_message, state)

        assert await state.get_state() == handlers.TestStates.waiting_birthdate.state
        assert events[0][0] == "user"
        assert "Intro override" in events[0][1]
        assert "Birth prompt" in events[0][1]

        birth_message = DummyMessage("24.08.1992", test_user, events)
        await handlers.test_collect_birthdate(birth_message, state)

        assert await state.get_state() == handlers.TestStates.waiting_name.state
        assert events[1] == ("user", "Name prompt")

        name_message = DummyMessage("Аня", test_user, events)
        await handlers.test_collect_name(name_message, state)

        assert await state.get_state() is None
        assert len(saved_requests) == 1
        tg_user_id, stored_user_id, birthdate_value, preferred_name = saved_requests[0]
        assert tg_user_id == test_user.id
        assert stored_user_id == user_row["id"]
        assert birthdate_value == date(1992, 8, 24)
        assert preferred_name == "Аня"

        assert events[2][0] == "user"
        assert events[2][1].startswith("Thanks, ")
        assert events[3][0] == "admin"
        assert notifications and notifications[0].startswith("🧪")

        assert started_calls  # form marked as started at least once

    asyncio.run(run_flow())


def test_test_flow_cancel(monkeypatch):
    async def run_flow():
        events: list[tuple[str, str]] = []
        test_user = DummyFromUser()
        user_row = {"id": 42, "tg_user_id": test_user.id, "full_name": test_user.full_name}

        async def fake_get_user_and_admin(message):
            return user_row, False

        async def fake_build_menu_keyboard(**kwargs):
            return "KB"

        content_map = {
            "menu.test": "Intro base",
            "menu.test_intro": "Intro override",
            "menu.test_birthdate_prompt": "Birth prompt",
        }

        async def fake_get_content(key: str, default: str = ""):
            return content_map.get(key, default)

        monkeypatch.setattr(handlers, "_get_user_and_admin", fake_get_user_and_admin)
        monkeypatch.setattr(handlers, "build_menu_keyboard", fake_build_menu_keyboard)
        monkeypatch.setattr(handlers, "get_content", fake_get_content)
        monkeypatch.setattr(handlers, "cancel_keyboard", lambda: "CANCEL")

        state = DummyState()
        start_message = DummyMessage("Пройти тест", test_user, events)

        await handlers.menu_test(start_message, state)

        assert await state.get_state() == handlers.TestStates.waiting_birthdate.state

        cancel_message = DummyMessage("Отмена", test_user, events)
        await handlers.test_collect_birthdate(cancel_message, state)

        assert await state.get_state() is None
        assert events[-1] == ("user", "Действие отменено. Возвращаюсь в главное меню...")

    asyncio.run(run_flow())


def test_test_flow_cancel_on_name(monkeypatch):
    async def run_flow():
        events: list[tuple[str, str]] = []
        test_user = DummyFromUser()
        user_row = {"id": 42, "tg_user_id": test_user.id, "full_name": test_user.full_name}

        async def fake_get_user_and_admin(message):
            return user_row, False

        async def fake_build_menu_keyboard(**kwargs):
            return "KB"

        content_map = {
            "menu.test": "Intro base {test_url}",
            "menu.test_intro": "Intro override {TEST_FORM_URL}",
            "menu.test_birthdate_prompt": "Birth prompt",
            "menu.test_name_prompt": "Name prompt",
        }

        async def fake_get_content(key: str, default: str = ""):
            return content_map.get(key, default)

        monkeypatch.setattr(handlers, "_get_user_and_admin", fake_get_user_and_admin)
        monkeypatch.setattr(handlers, "build_menu_keyboard", fake_build_menu_keyboard)
        monkeypatch.setattr(handlers, "get_content", fake_get_content)
        monkeypatch.setattr(handlers, "cancel_keyboard", lambda: "CANCEL")

        state = DummyState()
        start_message = DummyMessage("Пройти тест", test_user, events)

        await handlers.menu_test(start_message, state)

        birth_message = DummyMessage("24.08.1992", test_user, events)
        await handlers.test_collect_birthdate(birth_message, state)

        assert await state.get_state() == handlers.TestStates.waiting_name.state

        cancel_message = DummyMessage(handlers.CANCEL_TEXT, test_user, events)
        await handlers.test_collect_name(cancel_message, state)

        assert await state.get_state() is None
        assert await state.get_data() == {}
        assert events[-1] == ("user", "Действие отменено. Возвращаюсь в главное меню...")

    asyncio.run(run_flow())
