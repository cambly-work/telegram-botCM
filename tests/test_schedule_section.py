import asyncio
from datetime import datetime, timezone, date
from types import SimpleNamespace

import handlers


def test_send_schedule_section_dynamic(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_bool_setting(key, default):
        return True

    async def fake_is_member(user_row):
        return True

    async def fake_get_content(key, default):
        if key == "schedule":
            return "intro text"
        return default

    async def fake_list_schedule_events(*, from_dt=None, include_archived=False, limit=None):
        return [
            {
                "id": 5,
                "scheduled_at": datetime(2024, 9, 24, 16, 0, tzinfo=timezone.utc),
                "event_type": "Практика",
                "description": "Разбор главы 2",
                "link": "https://example.com",
                "week_number": 2,
                "week_title": "Мысли",
            }
        ]

    async def fake_get_current_week():
        return {
            "week_number": 2,
            "title": "Мысли",
            "start_date": date(2024, 9, 23),
            "end_date": date(2024, 9, 29),
        }

    async def fake_list_schedule_weeks(include_archived=False):
        return [
            {
                "week_number": 1,
                "title": "Внимание",
                "start_date": date(2024, 9, 16),
                "end_date": date(2024, 9, 22),
            },
            {
                "week_number": 2,
                "title": "Мысли",
                "start_date": date(2024, 9, 23),
                "end_date": date(2024, 9, 29),
            },
        ]

    async def fake_answer(message, user_row, is_admin, text, **kwargs):
        captured["text"] = text
        captured["kwargs"] = kwargs

    monkeypatch.setattr(handlers, "get_bool_setting", fake_get_bool_setting)
    monkeypatch.setattr(handlers, "is_member", fake_is_member)
    monkeypatch.setattr(handlers, "get_content", fake_get_content)
    monkeypatch.setattr(handlers, "list_schedule_events", fake_list_schedule_events)
    monkeypatch.setattr(handlers, "get_current_schedule_week", fake_get_current_week)
    monkeypatch.setattr(handlers, "list_schedule_weeks", fake_list_schedule_weeks)
    monkeypatch.setattr(handlers, "answer_with_main_menu", fake_answer)

    message = SimpleNamespace(from_user=SimpleNamespace(id=42))
    user = {"id": 1, "status": "member_active"}

    async def run():
        await handlers.send_schedule_section(message, user, is_admin=False)

    asyncio.run(run())

    text = captured.get("text", "")
    kwargs = captured.get("kwargs", {})

    assert "Ближайшие события" in text
    assert "/remind_5" in text
    assert "Практика" in text
    assert "Мысли" in text
    assert "https://example.com" in text
    assert kwargs.get("disable_web_page_preview") is True
    assert kwargs.get("section") == "materials"
