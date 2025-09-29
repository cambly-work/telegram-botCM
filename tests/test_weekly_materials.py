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
