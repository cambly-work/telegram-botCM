import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock

import types

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("SKIP_DB_INIT", "1")
os.environ.setdefault("SKIP_SCHEDULER", "1")
os.environ.setdefault("SKIP_WEBHOOK", "1")
os.environ.setdefault("SKIP_ADMIN_NOTIFICATIONS", "1")

sys.path.append(str(Path(__file__).resolve().parents[1]))

if "handlers" not in sys.modules:
    handlers_stub = types.ModuleType("handlers")
    handlers_stub.__path__ = []  # type: ignore[attr-defined]
    handlers_stub.router = types.SimpleNamespace()
    handlers_stub.tz_aware_msk = lambda dt: dt.isoformat() if dt else ""
    handlers_stub.upsert_funnel_delivery = AsyncMock()
    handlers_stub.FORM_LABELS = {}
    handlers_content_stub = types.ModuleType("handlers.content")
    handlers_content_stub._load_yaml_content = lambda: {}
    handlers_content_stub.get_content = lambda *_args, **_kwargs: ""

    handlers_stub._load_yaml_content = handlers_content_stub._load_yaml_content
    handlers_stub.get_content = handlers_content_stub.get_content

    sys.modules.setdefault("handlers", handlers_stub)
    sys.modules.setdefault("handlers.content", handlers_content_stub)

import app as app_module  # noqa: E402  pylint: disable=wrong-import-position


def test_homework_export(monkeypatch):
    asyncio.run(_run_export(monkeypatch))


async def _run_export(monkeypatch):
    now_dt = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    async def fake_fetch(query: str, *args: Any):
        lowered = query.strip().lower()
        if lowered.startswith("select id, tg_user_id"):
            return [
                {
                    "id": 1,
                    "tg_user_id": 555,
                    "email": "user@example.com",
                    "phone": "+79998887766",
                    "status": "member_active",
                    "access_until": now_dt,
                    "funnel_complete": True,
                }
            ]
        if "from funnel_progress" in lowered:
            assert args[0] == [1]
            return [
                {
                    "user_id": 1,
                    "lesson_num": 1,
                    "delivered_at": now_dt,
                    "opened_at": None,
                    "hw_status": "submitted",
                    "hw_answer": "Ответ",
                }
            ]
        raise AssertionError(f"unexpected fetch: {query}")

    monkeypatch.setattr(app_module, "fetch", fake_fetch)

    response = await app_module.admin_homework_export(secret=app_module.WEBHOOK_SECRET)
    assert response.media_type == "text/csv"
    assert "homework-export" in response.headers.get("Content-Disposition", "")

    content = response.body.decode("utf-8")
    lines = [line for line in content.strip().splitlines() if line.strip()]
    assert lines[0].startswith("user_id,tg_user_id")
    # 4 строки по числу уроков
    assert len(lines) == 5


def test_homework_import(monkeypatch):
    asyncio.run(_run_import(monkeypatch))


async def _run_import(monkeypatch):
    sync_calls: list[tuple[int, list[dict[str, Any]], int | None]] = []

    async def fake_sync(user_id: int, updates: list[dict[str, Any]], *, actor_id: int | None = None):
        sync_calls.append((user_id, updates, actor_id))

    monkeypatch.setattr(app_module, "sync_user_progress", fake_sync)
    monkeypatch.setattr(app_module, "notify_admins", AsyncMock())

    csv_payload = """user_id,tg_user_id,email,phone,status,access_until,funnel_complete,lesson,hw_status,delivered_at,opened_at,hw_answer
1,555,user@example.com,+79998887766,member_active,2024-01-01T12:00:00+00:00,1,1,submitted,2024-01-02T10:00:00+00:00,,Ответ
1,555,user@example.com,+79998887766,member_active,2024-01-01T12:00:00+00:00,1,2,pending,,, 
"""

    body = app_module.HomeworkImportBody(csv=csv_payload, actor_id=42)
    result = await app_module.admin_homework_import(body=body, secret=app_module.WEBHOOK_SECRET)

    assert result["ok"] is True
    assert result["affected_users"] == 1
    assert result["processed_rows"] == 2
    assert result["applied_users"] == [1]

    assert len(sync_calls) == 1
    user_id, updates, actor_id = sync_calls[0]
    assert user_id == 1
    assert actor_id == 42
    assert len(updates) == 2
    assert updates[0]["lesson"] == 1
    assert updates[0]["status"] == "submitted"
    assert isinstance(updates[0]["delivered_at"], datetime)
    assert updates[1]["lesson"] == 2
    assert updates[1]["status"] == "pending"
