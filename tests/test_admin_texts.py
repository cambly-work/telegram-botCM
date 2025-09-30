import asyncio
import sys
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
    def __init__(self, user_id: int = 1) -> None:
        self.id = user_id
        self.username = "admin"
        self.full_name = "Admin User"
        self.first_name = "Admin"


class DummyMessage:
    def __init__(self, text: str, from_user: DummyFromUser, events: list[tuple[str, str, dict]]):
        self.text = text
        self.from_user = from_user
        self._events = events

    async def answer(self, text: str, **kwargs):
        self._events.append(("bot", text, kwargs))
        return None


def test_admin_text_preview_shows_fresh_content(monkeypatch):
    async def run_flow():
        events: list[tuple[str, str, dict]] = []
        state = DummyState()
        admin_user = DummyFromUser(user_id=42)

        monkeypatch.setattr(handlers, "is_admin_id", lambda user_id: True)

        reset_calls: list[bool] = []

        async def fake_reset_state(target_state):
            reset_calls.append(True)
            return False

        monkeypatch.setattr(handlers, "_reset_state_if_needed", fake_reset_state)

        selected_label = "Окно «Пройти тест»"
        expected_key = "menu.test"
        current_value = "Здравствуйте, {name}! Это текущее значение."

        async def fake_get_content(key: str, default: str = "") -> str:
            assert key == expected_key
            return current_value

        monkeypatch.setattr(handlers, "get_content", fake_get_content)

        def fake_cancel_keyboard(*, extra_buttons=None):
            return {"buttons": tuple(extra_buttons or [])}

        monkeypatch.setattr(handlers, "cancel_keyboard", fake_cancel_keyboard)

        edit_message = DummyMessage(selected_label, admin_user, events)
        await handlers.admin_texts_edit_prompt(edit_message, state)

        assert reset_calls, "сброс состояния должен выполняться"
        assert await state.get_state() == handlers.AdminContentStates.waiting_value.state

        state_data = await state.get_data()
        assert state_data["content_key"] == expected_key
        assert state_data["content_label"] == selected_label
        assert state_data["content_preview_text"] == current_value

        assert events, "должно быть отправлено сообщение с инструкциями"
        first_response = events[0]
        assert handlers.ADMIN_TEXTS_PREVIEW_BUTTON in first_response[2]["reply_markup"]["buttons"]

        preview_message = DummyMessage(handlers.ADMIN_TEXTS_PREVIEW_BUTTON, admin_user, events)
        await handlers.admin_texts_preview(preview_message, state)

        preview_response = events[-1]
        assert "Предпросмотр" in preview_response[1]
        assert "Здравствуйте, Алиса! Это текущее значение." in preview_response[1]
        assert preview_response[2]["reply_markup"]["buttons"] == ()

    asyncio.run(run_flow())
