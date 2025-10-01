import sys
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings  # noqa: E402
from throttling_mw import ThrottleMiddleware  # noqa: E402


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DummyMessage:
    def __init__(self, user_id: int):
        self.from_user = SimpleNamespace(id=user_id)
        self._answers: list[tuple[str, dict]] = []

    async def answer(self, text: str, **kwargs):
        self._answers.append((text, kwargs))
        return None


async def _call_middleware(middleware, handler, event, times=1):
    for _ in range(times):
        await middleware(handler, event, {})


async def test_regular_user_receives_warning(monkeypatch, caplog):
    monkeypatch.setattr(settings, "ADMIN_IDS", set())
    middleware = ThrottleMiddleware(limit=3, window=5)
    user_id = 123
    event = DummyMessage(user_id)
    handler_calls = 0

    async def handler(*args, **kwargs):
        nonlocal handler_calls
        handler_calls += 1

    await _call_middleware(middleware, handler, event, times=3)
    assert handler_calls == 3
    assert len(middleware.bucket[user_id]) == 3

    with caplog.at_level(logging.INFO):
        await middleware(handler, event, {})

    assert handler_calls == 3
    assert event._answers
    warning_text, _ = event._answers[-1]
    assert "не так быстро" in warning_text
    assert f"{user_id}" in caplog.text
    assert len(middleware.bucket[user_id]) == 3


async def test_admin_is_not_throttled(monkeypatch):
    admin_id = 999
    monkeypatch.setattr(settings, "ADMIN_IDS", {admin_id})
    middleware = ThrottleMiddleware(limit=3, window=5)
    event = DummyMessage(admin_id)
    handler_calls = 0

    async def handler(*args, **kwargs):
        nonlocal handler_calls
        handler_calls += 1

    await _call_middleware(middleware, handler, event, times=4)

    assert handler_calls == 4
    assert len(middleware.bucket[admin_id]) == 4
    assert not event._answers
