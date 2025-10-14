import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import scheduler


class DummyBot:
    pass


def test_event_reminders_skip_stale(monkeypatch):
    now = datetime(2024, 10, 1, 12, 0, tzinfo=timezone.utc)
    reminders = [
        {
            "id": 1,
            "user_id": 101,
            "tg_user_id": 555,
            "remind_at": now - timedelta(hours=4),
            "event_id": 42,
            "scheduled_at": now - timedelta(hours=3),
            "event_type": "Лекция",
            "description": "",
            "link": "",
        }
    ]

    executed = []

    async def fake_fetch(_query):
        return reminders

    async def fake_execute(_query, reminder_id):
        executed.append(reminder_id)

    async def fake_send(*_args, **_kwargs):  # pragma: no cover - should not be called
        pytest.fail("send should not be called for stale reminders")

    monkeypatch.setattr(scheduler, "fetch", fake_fetch)
    monkeypatch.setattr(scheduler, "execute", fake_execute)
    monkeypatch.setattr(scheduler, "_send_with_retries", fake_send)
    monkeypatch.setattr(scheduler, "now_utc", lambda: now)
    monkeypatch.setattr(scheduler, "EVENT_REMINDER_MAX_DELAY", timedelta(hours=1))

    async def run():
        await scheduler._job_schedule_event_reminders_once(DummyBot())

    asyncio.run(run())

    assert executed, "stale reminders should be marked as processed"
    assert executed[0] == reminders[0]["id"]


def test_event_reminders_send_recent(monkeypatch):
    now = datetime(2024, 10, 1, 12, 0, tzinfo=timezone.utc)
    reminders = [
        {
            "id": 2,
            "user_id": 202,
            "tg_user_id": 777,
            "remind_at": now - timedelta(minutes=5),
            "event_id": 99,
            "scheduled_at": now - timedelta(minutes=30),
            "event_type": "Практика",
            "description": "Разбор",
            "link": "https://example.com",
        }
    ]

    send_calls: list[tuple] = []
    executed = []

    async def fake_fetch(_query):
        return reminders

    async def fake_execute(_query, reminder_id):
        executed.append(reminder_id)

    async def fake_send(*args, **kwargs):
        send_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(scheduler, "fetch", fake_fetch)
    monkeypatch.setattr(scheduler, "execute", fake_execute)
    monkeypatch.setattr(scheduler, "_send_with_retries", fake_send)
    monkeypatch.setattr(scheduler, "now_utc", lambda: now)
    monkeypatch.setattr(scheduler, "EVENT_REMINDER_MAX_DELAY", timedelta(hours=1))

    async def run():
        await scheduler._job_schedule_event_reminders_once(DummyBot())

    asyncio.run(run())

    assert send_calls, "recent reminder should trigger sending"
    # one execute for marking as sent
    assert executed[-1] == reminders[0]["id"]

