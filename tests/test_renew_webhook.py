import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock

from aiogram import Router
import types
from starlette.requests import Request

# Ensure environment flags before importing app
os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("SKIP_DB_INIT", "1")
os.environ.setdefault("SKIP_SCHEDULER", "1")
os.environ.setdefault("SKIP_WEBHOOK", "1")
os.environ.setdefault("SKIP_ADMIN_NOTIFICATIONS", "1")
os.environ.setdefault("AT_WEBHOOK_SHARED_SECRET", "")

sys.path.append(str(Path(__file__).resolve().parents[1]))

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


def test_renew_webhook_updates_payments_and_stats(monkeypatch):
    asyncio.run(_run_test(monkeypatch))


async def _run_test(monkeypatch):
    payments: Dict[str, Dict[str, Any]] = {}
    users: Dict[int, Dict[str, Any]] = {
        1: {
            "id": 1,
            "tg_user_id": 555,
            "status": "member_expired",
            "email": "user@example.com",
            "phone": "+79998887766",
            "at_user_id": "at-1",
            "access_until": None,
        }
    }

    async def fake_fetchrow(query: str, *args: Any):
        query = query.strip().lower()
        if "from users where lower(email)" in query:
            email = args[0].lower()
            for user in users.values():
                if user["email"].lower() == email:
                    return user
            return None
        if "from users where phone=$1" in query:
            phone = args[0]
            for user in users.values():
                if user["phone"] == phone:
                    return user
            return None
        if "select count(*) as c from users where status='lead_funnel'" in query:
            return {"c": sum(1 for u in users.values() if u["status"] == "lead_funnel")}
        if "select count(*) as c from users where status='member_active'" in query:
            return {"c": sum(1 for u in users.values() if u["status"] == "member_active")}
        if "select count(*) as c from users where status='member_expired'" in query:
            return {"c": sum(1 for u in users.values() if u["status"] == "member_expired")}
        if "select count(*) as c from users" in query:
            return {"c": len(users)}
        if "select count(distinct user_id) as c" in query:
            return {"c": 0}
        return None

    async def fake_fetch(query: str, *args: Any):
        query = query.strip().lower()
        if "from funnel_progress" in query:
            return []
        if "from payments" in query:
            stats = {}
            for payment in payments.values():
                status = payment["status"]
                stats.setdefault(status, []).append(payment["created_at"])
            result = []
            for status, created_values in stats.items():
                result.append(
                    {
                        "status": status,
                        "count": len(created_values),
                        "last_payment": max(created_values) if created_values else None,
                    }
                )
            return result
        return []

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
            return "UPDATE 1"
        if "set status='member_expired'" in lowered:
            user_id = args[0]
            users[user_id]["status"] = "member_expired"
            return "UPDATE 1"
        return "OK"

    monkeypatch.setattr(app_module, "fetchrow", fake_fetchrow)
    monkeypatch.setattr(app_module, "fetch", fake_fetch)
    monkeypatch.setattr(app_module, "execute", fake_execute)
    monkeypatch.setattr(app_module, "notify_admins", AsyncMock())
    monkeypatch.setattr(app_module, "gen_invite_link", AsyncMock(return_value="https://invite"))
    monkeypatch.setattr(app_module.bot, "send_message", AsyncMock(return_value=None))

    payload = {
        "event": "renew",
        "data": {
            "email": "user@example.com",
            "phone": "+7 (999) 888-77-66",
            "product_id": "course",
            "order_id": "ord-123",
            "status": "renew",
            "access_days": 30,
        },
    }

    body_bytes = json.dumps(payload).encode("utf-8")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/webhooks/antitraining",
        "headers": [(b"content-type", b"application/json")],
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    request = Request(scope, receive)

    response = await app_module.antitraining_webhook(request=request, x_signature=None)
    assert response["ok"] is True
    assert response["handled_event"] == "renew"
    assert response["user_found"] is True

    stored_payment = payments.get("ord-123")
    assert stored_payment is not None
    assert stored_payment["status"] == "renew"

    stats = await app_module.admin_stats(secret=app_module.WEBHOOK_SECRET)
    payment_stats = stats.get("payments", [])
    renew_entry = next((item for item in payment_stats if item["status"] == "renew"), None)
    assert renew_entry is not None
    assert renew_entry["count"] == 1
