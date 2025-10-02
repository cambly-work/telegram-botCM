import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import handlers


def test_admin_debug_includes_extended_metrics(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_menu_flags() -> dict[str, bool]:
        return {"main_menu": True, "materials": False}

    async def fake_get_broadcast_flags() -> dict[str, bool]:
        return {"broadcast_all": True, "broadcast_leads": True}

    def fake_collect_scheduler_status() -> dict[str, object]:
        return {"status": "running", "jobs": 3, "running": True}

    async def fake_fetchrow(query: str, *args):
        if "FROM content_versions" in query:
            return {"last_version": datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)}
        if "FROM content" in query:
            return {
                "total": 12,
                "last_updated": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            }
        if "FROM users" in query:
            return {
                "total": 42,
                "active": 30,
                "leads": 8,
                "expired": 4,
            }
        return {}

    async def fake_answer(text: str, **kwargs):
        captured["text"] = text
        captured["kwargs"] = kwargs

    monkeypatch.setattr(handlers, "ADMIN_IDS", {12345})
    monkeypatch.setattr(handlers, "get_menu_flags", fake_get_menu_flags)
    monkeypatch.setattr(handlers, "get_broadcast_flags", fake_get_broadcast_flags)
    monkeypatch.setattr(handlers, "_collect_scheduler_status", fake_collect_scheduler_status)
    monkeypatch.setattr(handlers, "fetchrow", fake_fetchrow)
    monkeypatch.setattr(handlers, "admin_main_keyboard", lambda: "keyboard")

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=12345, username="chief"),
        text=handlers.ADMIN_DEBUG_BUTTON,
        answer=fake_answer,
    )

    asyncio.run(handlers.admin_debug(message))

    text = captured.get("text", "")
    assert "🛠️ Диагностика" in text
    assert "📋 Флаги меню" in text
    assert "<code>main_menu</code>" in text
    assert "📣 Рассылки" in text
    assert "⏱ Планировщик" in text
    assert "Задачи: 3" in text
    assert "👩‍💻 Администраторы" in text
    assert "Ключей: 12" in text
    assert "Последнее обновление" in text
    assert "👥 Пользователи" in text
    assert captured.get("kwargs", {}).get("disable_web_page_preview") is True
