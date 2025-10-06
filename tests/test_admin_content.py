import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import handlers  # noqa: E402
from handlers.states import AdminContentStates  # noqa: E402


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
    def __init__(self, user_id: int, *, is_bot: bool = False) -> None:
        self.id = user_id
        self.is_bot = is_bot
        self.first_name = "Bot" if is_bot else "Admin"
        self.full_name = self.first_name


class DummyBot:
    def __init__(self, bot_id: int) -> None:
        self.id = bot_id


class DummyReplyMessage:
    def __init__(self, *, key: str, bot_id: int) -> None:
        self.html_text = f"<b>Ключ:</b> <code>{key}</code>"
        self.text = f"Ключ: {key}"
        self.caption = None
        self.from_user = DummyFromUser(bot_id, is_bot=True)


class DummyIncomingMessage:
    def __init__(
        self,
        *,
        text: str,
        from_user: DummyFromUser,
        reply: DummyReplyMessage,
        bot_id: int,
        events: list,
    ) -> None:
        self.text = text
        self.caption = None
        self.reply_to_message = reply
        self.from_user = from_user
        self.bot = DummyBot(bot_id)
        self._events = events

    async def answer(self, text: str, **kwargs):
        self._events.append((text, kwargs))


def test_admin_content_quick_reply_updates_value(monkeypatch):
    async def run():
        state = DummyState()
        await state.set_state(AdminContentStates.waiting_view_key)

        bot_id = 999
        key = "menu.registration_complete"
        admin_user = DummyFromUser(123)
        reply_message = DummyReplyMessage(key=key, bot_id=bot_id)
        events: list[tuple[str, dict]] = []
        message = DummyIncomingMessage(
            text="   Новый текст регистрации!   ",
            from_user=admin_user,
            reply=reply_message,
            bot_id=bot_id,
            events=events,
        )

        store: dict[str, str] = {}
        set_calls: list[tuple[str, str, int | None]] = []

        async def fake_set_content_value(key_arg: str, value: str, *, updated_by: int | None = None):
            store[key_arg] = value
            set_calls.append((key_arg, value, updated_by))

        async def fake_get_content(key_arg: str, default: str = "") -> str:
            return store.get(key_arg, default)

        async def fake_log_admin_action(*args, **kwargs):
            return None

        monkeypatch.setattr(handlers, "is_admin_id", lambda user_id: True)
        monkeypatch.setattr(handlers, "set_content_value", fake_set_content_value)
        monkeypatch.setattr(handlers, "get_content", fake_get_content)
        monkeypatch.setattr(handlers, "log_admin_action", fake_log_admin_action)
        monkeypatch.setattr(handlers, "admin_content_keyboard", lambda: "KB")

        await handlers.admin_content_quick_reply_update(message, state)

        assert set_calls, "set_content_value was not called"
        saved_key, saved_value, saved_admin = set_calls[0]
        assert saved_key == key
        assert saved_admin == admin_user.id
        assert saved_value == "Новый текст регистрации!"

        stored_value = await handlers.get_content(key)
        assert stored_value == "Новый текст регистрации!"

        assert await state.get_state() == AdminContentStates.waiting_view_key.state
        assert events, "No response message was sent"
        assert "обновлён" in events[0][0]

    asyncio.run(run())
