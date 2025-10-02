import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import date

import pytest
from aiogram import types as aiogram_types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import handlers  # noqa: E402


pytestmark = pytest.mark.anyio


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
    def __init__(self, text: str, from_user: DummyFromUser, events: list[tuple[str, dict]]):
        self.text = text
        self.from_user = from_user
        self.chat = SimpleNamespace(id=999)
        self.bot = SimpleNamespace()
        self._events = events

    async def answer(self, text: str, **kwargs):
        self._events.append((text, kwargs))
        return None


class DummyChatActionSender:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @classmethod
    def typing(cls, *args, **kwargs):
        return cls()


@pytest.fixture(autouse=True)
def patch_common(monkeypatch):
    monkeypatch.setattr(handlers, "cancel_keyboard", lambda: "CANCEL", raising=False)
    monkeypatch.setattr(handlers, "lesson_actions_keyboard", lambda: "LESSON_ACTIONS", raising=False)
    monkeypatch.setattr(handlers, "feedback_keyboard", lambda: "FEEDBACK", raising=False)
    monkeypatch.setattr(handlers, "after_lesson_keyboard", lambda: "AFTER_LESSON", raising=False)
    monkeypatch.setattr(handlers, "admin_broadcast_confirm_keyboard", lambda **_: "CONFIRM_KB", raising=False)
    monkeypatch.setattr(handlers, "ChatActionSender", DummyChatActionSender, raising=False)

    async def fake_build_menu_keyboard(*args, **kwargs):
        return "MENU_KB"

    async def fake_send_admin_broadcast_segment_prompt(*args, **kwargs):
        return None

    async def fake_send_admin_broadcast_menu(*args, **kwargs):
        return None

    async def fake_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(handlers.asyncio, "sleep", fake_sleep, raising=False)
    monkeypatch.setattr(handlers, "build_menu_keyboard", fake_build_menu_keyboard, raising=False)
    monkeypatch.setattr(
        handlers,
        "send_admin_broadcast_segment_prompt",
        fake_send_admin_broadcast_segment_prompt,
        raising=False,
    )
    monkeypatch.setattr(
        handlers,
        "send_admin_broadcast_menu",
        fake_send_admin_broadcast_menu,
        raising=False,
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_registration_smoke_flow(monkeypatch):
    events: list[tuple[str, dict]] = []
    user = DummyFromUser()
    message = DummyMessage("Анна", user, events)
    state = DummyState()

    execute_calls: list[tuple] = []

    async def fake_execute(*args, **kwargs):
        execute_calls.append((args, kwargs))

    monkeypatch.setattr(handlers, "execute", fake_execute, raising=False)

    async def fake_get_user(_):
        return {"id": 1, "name": "Анна", "email": "user@example.com", "phone": "+79991234567"}

    monkeypatch.setattr(handlers, "get_user_with_id", fake_get_user, raising=False)
    monkeypatch.setattr(handlers, "is_admin_id", lambda _: False, raising=False)

    async def fake_build_menu_keyboard(*_, **__):
        return "MENU_KB"

    monkeypatch.setattr(handlers, "build_menu_keyboard", fake_build_menu_keyboard, raising=False)

    async def fake_get_content(key, fallback):
        return fallback

    monkeypatch.setattr(handlers, "get_content", fake_get_content, raising=False)

    def fake_render_content(template: str, **kwargs):
        return template.format(**{k: v for k, v in kwargs.items() if isinstance(v, str)})

    monkeypatch.setattr(handlers, "render_content", fake_render_content, raising=False)

    await handlers.registration_receive_name(message, state)
    assert await state.get_state() == handlers.RegistrationStates.waiting_email.state
    assert any("Укажи email" in text for text, _ in events)

    message.text = "непочта"
    await handlers.registration_receive_email(message, state)
    assert await state.get_state() == handlers.RegistrationStates.waiting_email.state
    assert any("Формат неверный" in text for text, _ in events)

    message.text = "user@example.com"
    await handlers.registration_receive_email(message, state)
    assert await state.get_state() == handlers.RegistrationStates.waiting_phone.state

    message.text = "12345"
    await handlers.registration_receive_phone(message, state)
    assert await state.get_state() == handlers.RegistrationStates.waiting_phone.state
    assert any("Пример: +79991234567" in text for text, _ in events)

    message.text = "+7 (999) 123-45-67"
    await handlers.registration_receive_phone(message, state)
    assert await state.get_state() is None
    assert any("Регистрация завершена" in text for text, _ in events)
    assert execute_calls


async def test_hw_answer_to_feedback_transition(monkeypatch):
    events: list[tuple[str, dict]] = []
    user = DummyFromUser()
    message = DummyMessage("Ответ по уроку", user, events)
    state = DummyState()
    await state.set_state(handlers.HWStates.waiting_answer)
    await state.update_data(lesson_num=1)

    async def fake_get_user(_):
        return {"id": 24, "full_name": "Student"}

    async def fake_mark_done(*args, **kwargs):
        return None

    monkeypatch.setattr(handlers, "get_user_with_id", fake_get_user, raising=False)
    monkeypatch.setattr(handlers, "mark_lesson_done", fake_mark_done, raising=False)

    await handlers.hw_receive_answer(message, state)
    assert await state.get_state() == handlers.HWStates.waiting_feedback.state
    assert any("Твой ответ" in text for text, _ in events)


async def test_hw_feedback_custom_text(monkeypatch):
    events: list[tuple[str, dict]] = []
    user = DummyFromUser()
    message = DummyMessage("Очень полезно", user, events)
    state = DummyState()
    await state.set_state(handlers.HWStates.waiting_feedback)
    await state.update_data(lesson_num=2)

    async def fake_get_user(_):
        return {"id": 24, "full_name": "Student"}

    async def fake_save_feedback(*args, **kwargs):
        return None

    monkeypatch.setattr(handlers, "get_user_with_id", fake_get_user, raising=False)
    monkeypatch.setattr(handlers, "save_lesson_feedback", fake_save_feedback, raising=False)

    await handlers.feedback_receive_text(message, state)
    assert await state.get_state() is None
    assert any("Спасибо за отзыв" in text for text, _ in events)


async def test_notify_admins_on_test_request(monkeypatch):
    events: list[tuple[str, dict]] = []
    user = DummyFromUser(user_id=202, username="applicant")
    message = DummyMessage("Аня", user, events)
    state = DummyState()
    await state.set_state(handlers.TestStates.waiting_name)
    await state.update_data(test_birthdate=date(1990, 5, 1).isoformat(), test_form_slug="test", test_user_id=42)

    async def fake_get_user_and_admin(_):
        return {"id": 42, "name": ""}, False

    async def fake_mark_form_started(*args, **kwargs):
        return None

    async def fake_upsert_request(*args, **kwargs):
        return None

    async def fake_build_menu_keyboard(*args, **kwargs):
        return "MENU_KB"

    async def fake_get_content(key, fallback):
        return fallback

    def fake_render_content(template: str, **kwargs):
        return template.format(**{k: v for k, v in kwargs.items() if isinstance(v, str)})

    notifications: list[str] = []

    async def fake_notify(text: str):
        notifications.append(text)

    monkeypatch.setattr(handlers, "_get_user_and_admin", fake_get_user_and_admin, raising=False)
    monkeypatch.setattr(handlers, "mark_form_started", fake_mark_form_started, raising=False)
    monkeypatch.setattr(handlers, "upsert_test_request", fake_upsert_request, raising=False)
    monkeypatch.setattr(handlers, "build_menu_keyboard", fake_build_menu_keyboard, raising=False)
    monkeypatch.setattr(handlers, "get_content", fake_get_content, raising=False)
    monkeypatch.setattr(handlers, "render_content", fake_render_content, raising=False)
    monkeypatch.setattr(handlers, "_get_notify_admins", lambda: fake_notify, raising=False)
    monkeypatch.setattr(handlers, "_notify_admins_cached", fake_notify, raising=False)

    await handlers.test_collect_name(message, state)
    assert await state.get_state() is None
    assert any("Спасибо" in text for text, _ in events)
    assert notifications and "Новая запись" in notifications[0]


async def test_notify_admins_on_test_cancel(monkeypatch):
    events: list[tuple[str, dict]] = []
    user = DummyFromUser(user_id=303)
    message = DummyMessage("Отмена", user, events)
    state = DummyState()
    await state.set_state(handlers.TestStates.waiting_birthdate)
    await state.update_data(test_birthdate=date(1995, 1, 20).isoformat(), test_user_id=777)

    async def fake_get_user_and_admin(_):
        return {"id": 777, "name": ""}, False

    notifications: list[str] = []

    async def fake_notify(text: str):
        notifications.append(text)

    monkeypatch.setattr(handlers, "_get_user_and_admin", fake_get_user_and_admin, raising=False)
    monkeypatch.setattr(handlers, "_get_notify_admins", lambda: fake_notify, raising=False)
    monkeypatch.setattr(handlers, "_notify_admins_cached", fake_notify, raising=False)

    await handlers.cancel_handler(message, state)
    assert notifications and "Заявка на тест отменена" in notifications[0]


async def test_support_cancel_removes_keyboard(monkeypatch):
    events: list[tuple[str, dict]] = []
    user = DummyFromUser(user_id=505)
    message = DummyMessage(handlers.CANCEL_TEXT, user, events)
    state = DummyState()
    await state.set_state(handlers.SupportStates.waiting_question)

    async def fake_get_user_and_admin(_):
        return {"id": user.id}, False

    support_calls: list[tuple] = []

    async def fake_send_support_section(*args, **kwargs):
        support_calls.append((args, kwargs))

    monkeypatch.setattr(handlers, "_get_user_and_admin", fake_get_user_and_admin, raising=False)
    monkeypatch.setattr(handlers, "send_support_section", fake_send_support_section, raising=False)

    await handlers.cancel_handler(message, state)

    assert events, "cancel_handler should send a message before redirecting"
    text, kwargs = events[0]
    assert "Вопрос не отправлен" in text
    reply_markup = kwargs.get("reply_markup")
    assert isinstance(reply_markup, aiogram_types.ReplyKeyboardRemove)
    assert reply_markup.remove_keyboard is True
    assert support_calls, "cancel_handler should forward to support section"


async def test_notify_admins_error_path_keeps_flow(monkeypatch):
    events: list[tuple[str, dict]] = []
    user = DummyFromUser(user_id=404, username="student")
    message = DummyMessage("Вопрос по уроку", user, events)
    state = DummyState()
    await state.set_state(handlers.HWStates.waiting_question)
    await state.update_data(lesson_num=3)

    async def fake_get_user(_):
        return {"id": 404, "full_name": "Test Student"}

    async def fake_notify(_: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(handlers, "get_user_with_id", fake_get_user, raising=False)
    monkeypatch.setattr(handlers, "_get_notify_admins", lambda: fake_notify, raising=False)
    monkeypatch.setattr(handlers, "_notify_admins_cached", fake_notify, raising=False)

    await handlers.lesson_receive_question(message, state)
    assert await state.get_state() is None
    assert any("Ответ придёт" in text for text, _ in events)


async def test_admin_broadcast_edit_transition(monkeypatch):
    events: list[tuple[str, dict]] = []
    admin = DummyFromUser(user_id=1, username="admin")
    message = DummyMessage(handlers.EDIT_BROADCAST_BUTTON, admin, events)
    state = DummyState()
    await state.set_state(handlers.BroadcastStates.waiting_confirm)
    await state.update_data(segment="lead_funnel")

    monkeypatch.setattr(handlers, "is_admin_id", lambda user_id: True, raising=False)

    await handlers.admin_broadcast_edit(message, state)
    assert await state.get_state() == handlers.BroadcastStates.waiting_body.state
    data = await state.get_data()
    assert data.get("interactive") is True
    assert any("Пришли новый текст" in text for text, _ in events)


async def test_admin_broadcast_change_segment_transition(monkeypatch):
    events: list[tuple[str, dict]] = []
    admin = DummyFromUser(user_id=1, username="admin")
    message = DummyMessage(handlers.CHANGE_BROADCAST_SEGMENT_BUTTON, admin, events)
    state = DummyState()
    await state.set_state(handlers.BroadcastStates.waiting_confirm)

    monkeypatch.setattr(handlers, "is_admin_id", lambda user_id: True, raising=False)

    await handlers.admin_broadcast_change_segment(message, state)
    assert await state.get_state() == handlers.BroadcastStates.waiting_segment.state
    data = await state.get_data()
    assert data.get("change_segment") is True


async def test_admin_broadcast_save_template_transition(monkeypatch):
    events: list[tuple[str, dict]] = []
    admin = DummyFromUser(user_id=1, username="admin")
    message = DummyMessage("Черновик рассылки", admin, events)
    state = DummyState()
    await state.set_state(handlers.BroadcastStates.waiting_template_title)
    await state.update_data(segment="all", body="Текст", placeholders={}, cta_description=None, cta_buttons=None)

    monkeypatch.setattr(handlers, "is_admin_id", lambda user_id: True, raising=False)

    async def fake_upsert(title, segment, body, **kwargs):
        return {"title": title, "segment": segment, **kwargs}

    async def fake_log(*args, **kwargs):
        return None

    monkeypatch.setattr(handlers, "upsert_broadcast_template", fake_upsert, raising=False)
    monkeypatch.setattr(handlers, "log_admin_action", fake_log, raising=False)

    await handlers.admin_broadcast_save_template(message, state)
    assert await state.get_state() == handlers.BroadcastStates.waiting_confirm.state
    data = await state.get_data()
    assert data.get("template_title") == "Черновик рассылки"
    assert any("Шаблон сохранён" in text for text, _ in events)
