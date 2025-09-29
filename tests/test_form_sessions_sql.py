import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import handlers  # noqa: E402


def test_mark_form_started_uses_form_slug(monkeypatch):
    calls: list[tuple[str, tuple]] = []

    async def fake_execute(sql: str, *params):  # type: ignore[override]
        calls.append((sql, params))

    monkeypatch.setattr(handlers, "execute", fake_execute)

    asyncio.run(handlers.mark_form_started(123, "analysis"))

    assert calls, "mark_form_started should call execute"
    sql, params = calls[0]
    assert "form_slug" in sql
    assert "ON CONFLICT (user_id, form_slug)" in sql
    assert params == (123, handlers.FORM_SLUG_ANALYSIS)


def test_mark_form_completed_uses_form_slug(monkeypatch):
    calls: list[tuple[str, str, tuple]] = []
    responses = [None, {"id": 1, "user_id": 123, "form_slug": handlers.FORM_SLUG_TEST}]

    async def fake_fetchrow(sql: str, *params):  # type: ignore[override]
        calls.append(("fetchrow", sql, params))
        return responses.pop(0) if responses else None

    async def fake_execute(sql: str, *params):  # type: ignore[override]
        calls.append(("execute", sql, params))
        return None

    monkeypatch.setattr(handlers, "fetchrow", fake_fetchrow)
    monkeypatch.setattr(handlers, "execute", fake_execute)

    row, created = asyncio.run(handlers.mark_form_completed(123, "test"))

    assert created is True
    assert row == {"id": 1, "user_id": 123, "form_slug": handlers.FORM_SLUG_TEST}

    assert calls[0][0] == "fetchrow"
    assert "form_slug" in calls[0][1]
    assert calls[0][2] == (123, handlers.FORM_SLUG_TEST)

    assert calls[1][0] == "fetchrow"
    assert "INSERT INTO form_sessions (user_id, form_slug" in calls[1][1]
