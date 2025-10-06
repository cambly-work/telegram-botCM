"""Progress data helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db import fetch, transaction

__all__ = [
    "LESSON_PROGRESS_TOTAL",
    "PROGRESS_STATUS_ICONS",
    "PROGRESS_STATUS_LABELS",
    "get_user_progress",
    "sync_user_progress",
]

PROGRESS_STATUS_LABELS: dict[str, str] = {
    "submitted": "завершён",
    "pending": "в работе",
    "skipped": "пропущен",
}

PROGRESS_STATUS_ICONS: dict[str, str] = {
    "submitted": "✅",
    "pending": "⏳",
    "skipped": "⏭️",
}

LESSON_PROGRESS_TOTAL = 4


def _coerce_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _collect_progress_details(
    user_ids: list[int],
) -> dict[int, dict[int, dict[str, Any]]]:
    if not user_ids:
        return {}

    rows = await fetch(
        """
        SELECT user_id, lesson_num, delivered_at, opened_at, hw_status, hw_answer
        FROM funnel_progress
        WHERE user_id = ANY($1::int[])
        ORDER BY user_id, lesson_num
        """,
        user_ids,
    )

    details: dict[int, dict[int, dict[str, Any]]] = {}
    for row in rows or []:
        entry = details.setdefault(row["user_id"], {}).setdefault(
            row["lesson_num"],
            {
                "lesson_num": row["lesson_num"],
                "hw_status": row.get("hw_status") or None,
                "delivered_at": row.get("delivered_at"),
                "opened_at": row.get("opened_at"),
                "hw_answer": row.get("hw_answer"),
                "feedback_count": 0,
                "feedback_types": [],
                "delivered": True,
            },
        )
        # ensure hw_status preserved even if None
        entry["hw_status"] = row.get("hw_status") or entry.get("hw_status")

    feedback_rows = await fetch(
        """
        SELECT user_id, lesson_num, COUNT(*) AS feedback_count,
               array_agg(feedback_type ORDER BY created_at DESC) AS feedback_types
        FROM lesson_feedback
        WHERE user_id = ANY($1::int[])
        GROUP BY user_id, lesson_num
        """,
        user_ids,
    )

    for row in feedback_rows or []:
        entry = details.setdefault(row["user_id"], {}).setdefault(
            row["lesson_num"],
            {
                "lesson_num": row["lesson_num"],
                "hw_status": None,
                "delivered_at": None,
                "opened_at": None,
                "hw_answer": None,
                "feedback_count": 0,
                "feedback_types": [],
                "delivered": False,
            },
        )
        count = int(row.get("feedback_count") or 0)
        entry["feedback_count"] = count
        types = row.get("feedback_types") or []
        if isinstance(types, tuple):
            types = list(types)
        entry["feedback_types"] = list(types)
        if count > 0:
            entry["delivered"] = True
            if entry.get("hw_status") is None:
                entry["hw_status"] = "submitted"

    return details


async def get_user_progress(user_id: int) -> dict[int, dict[str, Any]]:
    details = await _collect_progress_details([user_id])
    return details.get(user_id, {})


def _serialize_progress_update(entry: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in entry.items():
        if value is None:
            continue
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


async def sync_user_progress(
    user_id: int,
    updates: list[dict[str, Any]],
    *,
    actor_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    if user_id is None:
        raise ValueError("user_id is required for progress sync")

    normalized_updates: list[dict[str, Any]] = []

    if updates:
        async with transaction() as conn:
            for raw in updates:
                if not isinstance(raw, dict):
                    continue
                lesson_raw = raw.get("lesson")
                if lesson_raw is None:
                    raise ValueError("progress entry missing lesson")
                try:
                    lesson_num = int(lesson_raw)
                except (ValueError, TypeError):
                    raise ValueError(f"lesson must be integer, got {lesson_raw!r}") from None
                if lesson_num not in (1, 2, 3, 4):
                    raise ValueError(f"lesson must be 1..4, got {lesson_num}")

                reset = bool(raw.get("reset"))
                status = raw.get("status")
                if status:
                    status = str(status).strip().lower()
                    if status not in PROGRESS_STATUS_LABELS:
                        raise ValueError(
                            f"invalid status '{status}' for lesson {lesson_num}"
                        )
                delivered_at = raw.get("delivered_at") or raw.get("delivered")
                opened_at = raw.get("opened_at") or raw.get("opened")
                hw_answer = raw.get("hw_answer") if "hw_answer" in raw else raw.get("answer")
                feedback = raw.get("feedback")

                delivered_dt = delivered_at
                if isinstance(delivered_dt, str):
                    delivered_dt = _coerce_datetime(delivered_dt)
                    if delivered_dt is None:
                        raise ValueError(
                            f"invalid delivered_at value for lesson {lesson_num}"
                        )
                opened_dt = opened_at
                if isinstance(opened_dt, str):
                    opened_dt = _coerce_datetime(opened_dt)
                    if opened_dt is None:
                        raise ValueError(
                            f"invalid opened_at value for lesson {lesson_num}"
                        )

                if feedback is None:
                    feedback_list: list[str] | None = None
                else:
                    if isinstance(feedback, str):
                        feedback_list = [
                            chunk.strip()
                            for chunk in feedback.split(",")
                            if chunk.strip()
                        ]
                    else:
                        feedback_list = [
                            str(chunk).strip()
                            for chunk in feedback
                            if str(chunk).strip()
                        ]

                normalized_entry: dict[str, Any] = {
                    "lesson": lesson_num,
                    "status": status,
                    "delivered_at": delivered_dt,
                    "opened_at": opened_dt,
                    "hw_answer": hw_answer,
                    "feedback": feedback_list,
                    "reset": reset,
                }
                normalized_updates.append(normalized_entry)

                if reset:
                    await conn.execute(
                        "DELETE FROM funnel_progress WHERE user_id=$1 AND lesson_num=$2",
                        user_id,
                        lesson_num,
                    )
                    await conn.execute(
                        "DELETE FROM lesson_feedback WHERE user_id=$1 AND lesson_num=$2",
                        user_id,
                        lesson_num,
                    )
                    continue

                existing = await conn.fetchrow(
                    "SELECT id FROM funnel_progress WHERE user_id=$1 AND lesson_num=$2",
                    user_id,
                    lesson_num,
                )

                if existing:
                    updates_sql: list[str] = []
                    params: list[Any] = [user_id, lesson_num]
                    idx = 3
                    if status:
                        updates_sql.append(f"hw_status=${idx}")
                        params.append(status)
                        idx += 1
                    if delivered_dt is not None:
                        updates_sql.append(f"delivered_at=${idx}")
                        params.append(delivered_dt)
                        idx += 1
                    if opened_dt is not None:
                        updates_sql.append(f"opened_at=${idx}")
                        params.append(opened_dt)
                        idx += 1
                    if hw_answer is not None:
                        updates_sql.append(f"hw_answer=${idx}")
                        params.append(hw_answer)
                        idx += 1
                    if updates_sql:
                        await conn.execute(
                            f"UPDATE funnel_progress SET {', '.join(updates_sql)} WHERE user_id=$1 AND lesson_num=$2",
                            *params,
                        )
                else:
                    await conn.execute(
                        """
                        INSERT INTO funnel_progress (user_id, lesson_num, delivered_at, opened_at, hw_answer, hw_status)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        user_id,
                        lesson_num,
                        delivered_dt or datetime.now(timezone.utc),
                        opened_dt,
                        hw_answer,
                        status or "pending",
                    )

                if feedback_list is not None:
                    await conn.execute(
                        "DELETE FROM lesson_feedback WHERE user_id=$1 AND lesson_num=$2",
                        user_id,
                        lesson_num,
                    )
                    for code in feedback_list:
                        await conn.execute(
                            """
                            INSERT INTO lesson_feedback (user_id, lesson_num, feedback_type, created_at)
                            VALUES ($1, $2, $3, NOW())
                            """,
                            user_id,
                            lesson_num,
                            code,
                        )

    if actor_id and normalized_updates:
        from . import log_admin_action  # avoid circular import

        payload = {
            "user_id": user_id,
            "lessons": [_serialize_progress_update(entry) for entry in normalized_updates],
        }
        await log_admin_action(actor_id, "progress_sync", payload)

    details = await _collect_progress_details([user_id])
    return details.get(user_id, {})
