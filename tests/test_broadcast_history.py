import asyncio
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

import logging

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import handlers  # noqa: E402


class DummyMessage:
    def __init__(self, events):
        self.from_user = type("User", (), {"id": 1})()
        self._events = events

    async def answer(self, text: str, **kwargs):
        self._events.append((text, kwargs))


def test_send_admin_broadcast_menu_handles_legacy_admin_log(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="handlers")

    async def run():
        events: list[tuple[str, dict]] = []
        message = DummyMessage(events)

        async def fake_get_content(key: str, default: str = "") -> str:
            return default

        monkeypatch.setattr(handlers, "get_content", fake_get_content)

        async def fake_get_broadcast_flags() -> dict[str, bool]:
            return {key: True for key in handlers._ADMIN_BROADCAST_SETTINGS_DEFAULTS}

        monkeypatch.setattr(handlers, "get_broadcast_flags", fake_get_broadcast_flags)

        monkeypatch.setattr(handlers, "admin_broadcast_keyboard", lambda labels: labels)

        queries: list[str] = []

        async def fake_fetch(query: str, *args):
            queries.append(query)
            if "admin_id" in query and "user_id AS admin_id" not in query:
                raise handlers.UndefinedColumnError("admin_id")
            return [
                {
                    "id": 1,
                    "admin_id": None,
                    "payload": json.dumps({"segment": "all", "ok": 1}),
                    "created_at": datetime.now(timezone.utc),
                }
            ]

        monkeypatch.setattr(handlers, "fetch", fake_fetch)

        await handlers.send_admin_broadcast_menu(message)

        assert events, "handler should respond despite legacy schema"
        response_text, response_kwargs = events[0]
        assert "Последняя рассылка" in response_text
        assert "reply_markup" in response_kwargs

        assert len(queries) == 2, "fallback query should execute after UndefinedColumnError"
        assert any("user_id" in q and "event" in q for q in queries[1:])
        assert any(
            "admin_log schema is outdated" in record.message for record in caplog.records
        )

    asyncio.run(run())
