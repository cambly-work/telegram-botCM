import asyncio
from types import SimpleNamespace

import handlers
from keyboards import ADMIN_PAYMENTS_BUTTON


def test_send_weekly_materials_without_access(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_fetchrow(*args, **kwargs):
        return None

    async def fake_answer(message, user_row, is_admin, text, **kwargs):
        captured["text"] = text
        captured["section"] = kwargs.get("section")

    handlers._CONTENT_DB_CACHE.clear()

    monkeypatch.setattr(handlers, "fetchrow", fake_fetchrow)
    monkeypatch.setattr(handlers, "answer_with_main_menu", fake_answer)

    user = {"status": "lead"}
    message = SimpleNamespace()

    async def run_test():
        await handlers.send_weekly_materials_section(message, user, is_admin=False)

    asyncio.run(run_test())

    expected_fragment = (
        f"Оформи доступ в разделе «{ADMIN_PAYMENTS_BUTTON}», и бот пришлёт ссылки автоматически."
    )

    assert expected_fragment in captured.get("text", "")
    assert captured.get("section") == "materials"


def test_is_member_with_permanent_access(monkeypatch):
    calls = []

    async def fake_execute(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(handlers, "execute", fake_execute)

    user = {"id": 1, "status": "member_active", "access_until": None}

    async def run_test():
        return await handlers.is_member(user)

    result = asyncio.run(run_test())

    assert result is True
    assert calls == []


def test_send_weekly_materials_with_permanent_access(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_get_bool_setting(*args, **kwargs):
        return True

    async def fake_get_content(key, default):
        return {
            "weekly_materials": "weekly content",
            "menu.weekly.locked": default,
            "menu.weekly.disabled": default,
        }.get(key, default)

    async def fake_answer(message, user_row, is_admin, text, **kwargs):
        captured["text"] = text
        captured["section"] = kwargs.get("section")

    handlers._CONTENT_DB_CACHE.clear()

    monkeypatch.setattr(handlers, "get_bool_setting", fake_get_bool_setting)
    monkeypatch.setattr(handlers, "get_content", fake_get_content)
    monkeypatch.setattr(handlers, "answer_with_main_menu", fake_answer)

    user = {"id": 1, "status": "member_active", "access_until": None}
    message = SimpleNamespace()

    async def run_test():
        await handlers.send_weekly_materials_section(message, user, is_admin=False)

    asyncio.run(run_test())

    assert captured.get("text") == "weekly content"
    assert captured.get("section") == "materials"
