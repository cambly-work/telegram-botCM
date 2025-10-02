import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace


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
            "analysis_requests": {
                "statuses": [
                    {
                        "status": "new",
                        "count": 1,
                        "last_updated": later_ts,
                    }
                ],
                "entries": [
                    {
                        "id": 101,
                        "status": "new",
                        "created_at": base_ts,
                        "updated_at": later_ts,
                        "preferred_format": "Zoom",
                        "preferred_time": "вечером",
                        "contact": "@consultant",
                        "tg_user_id": 555111,
                        "user_id": 42,
                        "full_name": "Мария Консультация",
                        "name": "",
                        "username": "maria_consult",
                    }
                ],
            },
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
                        "birthdate": base_ts.date(),
                        "username": "ivan_test",
                        "tg_user_id": 987654,
                    }
                ],
            },
        },
        "timestamp": later_ts,
    }


def test_admin_stats_forms_default_summary_without_applicant_table():
    stats = _default_stats()
    text = handlers._format_admin_stats_forms(stats)

    assert "<b>Список заявителей</b>" not in text
    assert "Иван Иванов" not in text
    assert "@ivan_test" not in text
    assert "Пётр Петров" not in text
    assert "@petr_petrov" not in text
    assert "Мария Консультация" in text
    assert "@consultant" in text
    assert "Zoom" in text


def test_admin_stats_forms_handles_missing_usernames():
    stats = _default_stats()
    stats["forms"]["test_requests"]["entries"][0]["username"] = ""
    stats["forms"]["test_requests"]["entries"][0]["tg_user_id"] = 112233

    text = handlers._format_admin_stats_forms(stats, status_filter="waiting")

    assert "112233" in text


def test_format_admin_test_request_entry_prefers_name_and_escapes():
    base_ts = _build_base_timestamp()
    entry = {
        "id": 42,
        "status": "waiting",
        "preferred_name": "Анна <Смирнова>",
        "birthdate": base_ts.date(),
        "username": "anna&co",
        "tg_user_id": 987654321,
        "created_at": base_ts,
        "updated_at": base_ts + timedelta(hours=1),
    }

    text = handlers._format_admin_test_request_entry(entry)

    assert "#42" in text
    assert handlers.TEST_REQUEST_STATUS_LABELS["waiting"] in text
    assert "@anna&amp;co" in text
    assert "Дата рождения: 01.01.2024" in text


def test_format_admin_analysis_request_entry_includes_contacts():
    base_ts = _build_base_timestamp()
    entry = {
        "id": 7,
        "status": "archived",
        "contact": "mail@example.com",
        "preferred_format": "Очная",
        "preferred_time": "утром",
        "username": "analysis_user",
        "tg_user_id": 123456,
        "user_id": 789,
        "created_at": base_ts,
        "updated_at": base_ts + timedelta(hours=3),
        "full_name": "Марина Аналитик",
    }

    text = handlers._format_admin_analysis_request_entry(entry)

    assert "Заявка #7" in text
    assert "Марина Аналитик" in text
    assert "mail@example.com" in text
    assert "Очная" in text
    assert "утром" in text
    assert "@analysis_user" in text
    assert "id=789" in text


def test_admin_stats_forms_waiting_filter_shows_applicants():
    stats = _default_stats()

    text = handlers._format_admin_stats_forms(stats, status_filter="waiting")

    assert "<b>Список заявителей</b>" in text
    assert "Иван Иванов" in text
    assert "@ivan_test" in text
    assert "Пётр Петров" not in text
    assert "Мария Консультация" in text


def test_admin_stats_forms_filter_limits_entries():
    stats = _default_stats()
    base_ts = _build_base_timestamp()
    later_ts = base_ts + timedelta(hours=2)

    stats["forms"]["test_requests"]["entries"].append(
        {
            "id": 6,
            "status": "archived",
            "updated_at": later_ts,
            "created_at": base_ts,
            "preferred_name": "Сергей Сергеев",
            "birthdate": base_ts.date(),
            "username": "sergey_done",
            "tg_user_id": 192837,
        }
    )
    stats["forms"]["sessions_details"].append(
        {
            "id": 12,
            "form_slug": handlers.FORM_SLUG_ANALYSIS,
            "started_at": base_ts,
            "completed_at": later_ts,
            "user_id": 8,
            "full_name": "Анна Завершённая",
            "username": "anna_completed",
            "tg_user_id": 246810,
        }
    )

    text = handlers._format_admin_stats_forms(stats, status_filter="archived")

    assert "Текущий фильтр: <b>Архив</b>" in text
    assert "Сергей Сергеев" in text
    assert "Анна Завершённая" not in text
    assert "Иван Иванов" not in text
    assert "Пётр Петров" not in text
    assert "Всего заявок: <b>1</b>" in text
    assert "Активных (ожидают действий): <b>0</b>" in text
    assert "Мария Консультация" in text


def test_admin_stats_forms_filter_empty_message():
    stats = _default_stats()

    text = handlers._format_admin_stats_forms(stats, status_filter="archived")

    assert "Текущий фильтр: <b>Архив</b>" in text
    assert "По выбранному фильтру заявки не найдены." in text


def test_admin_stats_forms_apply_filter_reports_empty_entries(monkeypatch):
    breakdown_calls: list[str | None] = []

    async def fake_send_breakdown(message, *, status_filter):
        breakdown_calls.append(status_filter)

    async def fake_collect_admin_stats_data():
        return {
            "forms": {
                "test_requests": {
                    "entries": [
                        {
                            "id": 101,
                            "status": "waiting",
                            "updated_at": None,
                            "created_at": None,
                        }
                    ]
                }
            }
        }

    status_holder = {"value": None}

    def fake_set_filter(admin_id, status):
        status_holder["value"] = status

    def fake_get_filter(admin_id):
        return status_holder["value"]

    class DummyMessage:
        def __init__(self):
            self.from_user = SimpleNamespace(id=999)
            self.text = "dummy"
            self.answers: list[dict[str, object]] = []

        async def answer(self, text, **kwargs):
            self.answers.append({"text": text, "kwargs": kwargs})

    message = DummyMessage()

    monkeypatch.setattr(handlers, "is_admin_id", lambda user_id: True)
    monkeypatch.setattr(handlers, "admin_forms_filter_status_from_text", lambda text: (True, "archived"))
    monkeypatch.setattr(handlers, "_set_admin_forms_filter", fake_set_filter)
    monkeypatch.setattr(handlers, "_get_admin_forms_filter", fake_get_filter)
    monkeypatch.setattr(handlers, "_send_admin_forms_breakdown", fake_send_breakdown)
    monkeypatch.setattr(handlers, "_collect_admin_stats_data", fake_collect_admin_stats_data)

    asyncio.run(handlers.admin_stats_forms_apply_filter(message, state=None))

    assert breakdown_calls == ["archived"]
    assert any(
        "По выбранному фильтру заявки не найдены." in str(call.get("text", ""))
        for call in message.answers
    )
