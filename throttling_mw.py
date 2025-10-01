# throttling_mw.py
import logging
import time
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram import types

import settings


logger = logging.getLogger(__name__)


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, limit=3, window=5.0):
        super().__init__()
        self.limit = limit
        self.window = window
        self.bucket = {}  # uid -> [timestamps]

    async def __call__(self, handler, event: types.TelegramObject, data):
        uid = None
        if hasattr(event, "from_user") and event.from_user:
            uid = event.from_user.id
        if uid:
            now = time.monotonic()
            q = self.bucket.get(uid, [])
            q = [t for t in q if now - t <= self.window]
            if len(q) >= self.limit:
                is_admin = (
                    hasattr(event, "from_user")
                    and event.from_user
                    and event.from_user.id in settings.ADMIN_IDS
                )
                if not is_admin:
                    warning_text = (
                        "Пожалуйста, не так быстро. Попробуйте ещё раз через несколько секунд."
                    )
                    if isinstance(event, types.CallbackQuery):
                        await event.answer(warning_text)
                    elif isinstance(event, types.Message):
                        await event.answer(warning_text)
                    elif hasattr(event, "answer"):
                        await event.answer(warning_text)
                    logger.info(
                        "Throttle limit reached for user %s (limit=%s, window=%s)",
                        uid,
                        self.limit,
                        self.window,
                    )
                    return
            q.append(now)
            self.bucket[uid] = q
        return await handler(event, data)
