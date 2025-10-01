import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock

from starlette.requests import Request
from aiogram import Router
import types

# Ensure environment variables before importing app
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("SKIP_DB_INIT", "1")
os.environ.setdefault("SKIP_SCHEDULER", "1")
os.environ.setdefault("SKIP_WEBHOOK", "1")
os.environ.setdefault("SKIP_ADMIN_NOTIFICATIONS", "1")
os.environ.setdefault("YOOMONEY_WEBHOOK_SECRET", "")

sys.path.append(str(Path(__file__).resolve().parents[1]))

if "handlers" not in sys.modules:
    handlers_stub = types.ModuleType("handlers")
    handlers_stub.router = Router(name="test-router")

    def _tz_aware_msk(dt):
        return dt.isoformat() if dt else ""

    async def _noop_async(*_args, **_kwargs):
        return None

    def _load_yaml_content_stub():
        return {}

    handlers_stub.tz_aware_msk = _tz_aware_msk
    handlers_stub.upsert_funnel_delivery = _noop_async
    handlers_stub._load_yaml_content = _load_yaml_content_stub
    handlers_stub.FORM_LABELS = {}

    sys.modules.setdefault("handlers", handlers_stub)

import app as app_module  # noqa: E402  pylint: disable=wrong-import-position


def test_yoomoney_webhook_flow(monkeypatch):
    asyncio.run(_run_test(monkeypatch))


async def _run_test(monkeypatch):
    payments: Dict[str, Dict[str, Any]] = {}
    users: Dict[int, Dict[str, Any]] = {
        1: {
            "id": 1,
            "tg_user_id": 777,
            "status": "member_expired",
            "email": "user@example.com",
            "phone": "+79998887766",
            "at_user_id": "at-42",
            "access_until": None,
            "funnel_complete": False,
        }
    }

    async def fake_fetchrow(query: str, *args: Any):
        lowered = query.strip().lower()
        if lowered.startswith("select * from users where lower(email)=lower($1)"):
            email = args[0].lower()
            for user in users.values():
                if user["email"].lower() == email:
                    return user
            return None
        if lowered.startswith("select * from users where phone=$1"):
            phone = args[0]
            for user in users.values():
                if user["phone"] == phone:
                    return user
            return None
        if lowered.startswith("select * from users where id=$1"):
            user_id = int(args[0])
            return users.get(user_id)
        if lowered.startswith("select * from users where tg_user_id=$1"):
            tg_user_id = int(args[0])
            for user in users.values():
                if user["tg_user_id"] == tg_user_id:
                    return user
            return None
        return None

    async def fake_execute(query: str, *args: Any):
        lowered = query.strip().lower()
        if lowered.startswith("insert into payments"):
            order_id = args[0]
            payments[order_id] = {
                "order_id": order_id,
                "at_user_id": args[1],
                "email": args[2],
                "phone": args[3],
                "product_id": args[4],
                "status": args[5],
                "access_until": args[6],
                "raw_payload": json.loads(args[7]) if isinstance(args[7], str) else args[7],
                "created_at": datetime.now(timezone.utc),
            }
            return "INSERT 0 1"
        if "set status='member_active'" in lowered:
            user_id = args[0]
            users[user_id]["status"] = "member_active"
            users[user_id]["access_until"] = args[1]
            users[user_id]["funnel_complete"] = True
            return "UPDATE 1"
        if "set status='member_expired'" in lowered:
            user_id = args[0]
            users[user_id]["status"] = "member_expired"
            users[user_id]["funnel_complete"] = False
            return "UPDATE 1"
        if "update users set funnel_complete=true" in lowered:
            user_id = args[0]
            users[user_id]["funnel_complete"] = True
            return "UPDATE 1"
        if "update users set funnel_complete=false" in lowered:
            user_id = args[0]
            users[user_id]["funnel_complete"] = False
            return "UPDATE 1"
        if "insert into funnel_progress" in lowered:
            return "INSERT 0 4"
        return "OK"

    async def fake_fetch(query: str, *args: Any):
        return []

    monkeypatch.setattr(app_module, "fetchrow", fake_fetchrow)
    monkeypatch.setattr(app_module, "fetch", fake_fetch)
    monkeypatch.setattr(app_module, "execute", fake_execute)
    notify_mock = AsyncMock()
    monkeypatch.setattr(app_module, "notify_admins", notify_mock)
    monkeypatch.setattr(app_module, "gen_invite_link", AsyncMock(return_value="https://invite"))
    send_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(app_module.bot, "send_message", send_mock)

    # Success webhook
    success_payload = {
        "event": "payment.succeeded",
        "object": {
            "id": "pay-1",
            "status": "succeeded",
            "amount": {"value": "2690.00", "currency": "RUB"},
            "metadata": {
                "email": "user@example.com",
                "phone": "+7 (999) 888-77-66",
                "access_days": 30,
            },
        },
    }
    success_bytes = json.dumps(success_payload).encode("utf-8")

    success_scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhooks/yoomoney",
        "headers": [(b"content-type", b"application/json")],
    }

    async def success_receive():
        return {"type": "http.request", "body": success_bytes, "more_body": False}

    success_request = Request(success_scope, success_receive)
    success_response = await app_module.yoomoney_webhook(success_request, x_signature=None)

    assert success_response["ok"] is True
    assert success_response["status"] == "succeeded" or success_response["status"] == "paid"
    assert success_response.get("invite_link") == "https://invite"
    assert success_response.get("member_status") == "member_active"
    assert users[1]["status"] == "member_active"
    assert users[1]["access_until"] is not None
    assert users[1]["funnel_complete"] is True
    assert "pay-1" in payments
    assert payments["pay-1"]["status"] == "paid"

    # Failure webhook
    failure_payload = {
        "event": "payment.canceled",
        "object": {
            "id": "pay-1",
            "status": "canceled",
            "metadata": {
                "email": "user@example.com",
                "phone": "+7 (999) 888-77-66",
            },
        },
    }
    failure_bytes = json.dumps(failure_payload).encode("utf-8")

    failure_scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhooks/yoomoney",
        "headers": [(b"content-type", b"application/json")],
    }

    async def failure_receive():
        return {"type": "http.request", "body": failure_bytes, "more_body": False}

    failure_request = Request(failure_scope, failure_receive)
    failure_response = await app_module.yoomoney_webhook(failure_request, x_signature=None)

    assert failure_response["ok"] is True
    assert failure_response["status"] in {"failed", "canceled"}
    assert failure_response.get("member_status") == "member_expired"
    assert users[1]["status"] == "member_expired"
    assert users[1]["funnel_complete"] is False
    assert payments["pay-1"]["status"] == "failed"

    # Notifications & messaging
    assert notify_mock.await_count == 2
    assert send_mock.await_count == 2
