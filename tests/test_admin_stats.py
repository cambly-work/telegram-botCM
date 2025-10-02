import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import handlers  # noqa: E402


def _build_base_timestamp() -> datetime:
    return datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


def _default_stats() -> dict:
    base_ts = _build_base_timestamp()
    later_ts = base_ts + timedelta(hours=2)

    return {
        "forms": {
            "sessions": [
                {
                    "form_slug": handlers.FORM_SLUG_ANALYSIS,
                    "total": 2,
                    "completed": 1,
                    "in_progress": 1,
                    "last_started": base_ts.isoformat(),
                    "last_completed": later_ts.isoformat(),
                }
            ],
            "sessions_details": [
                {
                    "id": 11,
                    "form_slug": handlers.FORM_SLUG_ANALYSIS,
                    "started_at": later_ts,
                    "completed_at": None,
                    "user_id": 7,
                    "full_name": "Пётр Петров",
                    "name": "",
                    "username": "petr_petrov",
                    "tg_user_id": 123456,
                }
            ],
            "test_requests": {
                "statuses": [
                    {
                        "status": "waiting",
                        "count": 1,
                        "last_updated": later_ts,
                    }
                ],
                "summary": {
                    "total": 1,
                    "active": 1,
                },
                "entries": [
                    {
                        "id": 5,
                        "status": "waiting",
                        "updated_at": later_ts,
                        "created_at": base_ts,
                        "preferred_name": "Иван Иванов",
                        "username": "ivan_test",
                        "tg_user_id": 987654,
                    }
                ],
            },
        },
        "timestamp": later_ts,
    }


def test_admin_stats_forms_includes_applicants_names_and_usernames():
    stats = _default_stats()
    text = handlers._format_admin_stats_forms(stats)

    assert "<b>Список заявителей</b>" in text
    assert "Иван Иванов" in text
    assert "@ivan_test" in text
    assert "Пётр Петров" in text
    assert "@petr_petrov" in text


def test_admin_stats_forms_handles_missing_usernames():
    stats = _default_stats()
    stats["forms"]["sessions_details"][0]["username"] = ""
    stats["forms"]["sessions_details"][0]["tg_user_id"] = 112233

    text = handlers._format_admin_stats_forms(stats)

    assert "112233" in text
