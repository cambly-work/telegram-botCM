# throttling_mw.py
import time
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram import types

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
                # тихо игнорим; можно отправить мягкое сообщение
                return
            q.append(now)
            self.bucket[uid] = q
        return await handler(event, data)