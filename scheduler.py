# scheduler.py
import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from aiogram import Bot, exceptions as tg_exc

RetryAfterTypes = tuple(
    exc
    for exc in (
        getattr(tg_exc, "TelegramRetryAfter", None),
        getattr(tg_exc, "RetryAfter", None),
    )
    if exc is not None
) or (Exception,)

from db import fetch, fetchrow, execute
from keyboards import lesson_keyboard
# переиспользуем минимум логики из handlers, чтобы не дублировать
from handlers import _load_yaml_content, upsert_funnel_delivery, FORM_LABELS, get_content

logger = logging.getLogger("scheduler")

scheduler: Optional[AsyncIOScheduler] = None

# ──────────────────────────────────────────────────────────────────────────────
# ENV
# ──────────────────────────────────────────────────────────────────────────────
AT_PRODUCT_ID_CLUB = os.getenv("AT_PRODUCT_ID_CLUB", "")
WELCOME_POST_URL = os.getenv("WELCOME_POST_URL", "https://t.me/")
CLUB_CHAT_ID = os.getenv("CLUB_CHAT_ID", "")  # если захочешь автогенерацию инвайтов из планировщика


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def get_scheduler_status() -> dict:
    """
    Возвращает статус планировщика
    """
    # Если у вас есть глобальная переменная для планировщика, например, scheduler
    # вы можете проверить его статус
    try:
        if 'scheduler' in globals() and scheduler and scheduler.running:
            return {"status": "running", "jobs": len(scheduler.get_jobs())}
        else:
            return {"status": "stopped", "jobs": 0}
    except Exception:
        return {"status": "unknown", "jobs": 0}

def _msk_str(dt: datetime) -> str:
    return dt.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M MSK")


async def _send_with_retries(bot: Bot, chat_id: int, text: str, reply_markup=None, max_attempts: int = 3) -> bool:
    """
    Безопасная отправка сообщения с экспоненциальной задержкой между попытками.
    Возвращает True при успехе.
    """
    delay = 0.8
    attempt = 1
    while True:
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except RetryAfterTypes as e:
            # Telegram просит подождать (Flood control)
            wait_for = getattr(e, "timeout", delay)
            logger.warning("Flood control: waiting %.2fs (attempt %s/%s)", wait_for, attempt, max_attempts)
            await asyncio.sleep(float(wait_for))
        except tg_exc.TelegramBadRequest as e:
            # Часто: chat not found / bot blocked / can't initiate conversation
            logger.warning("BadRequest when sending to %s: %s", chat_id, e)
            return False
        except Exception as e:
            logger.warning("Send attempt %s failed for %s: %s", attempt, chat_id, e)
            if attempt >= max_attempts:
                return False
            await asyncio.sleep(delay)
        attempt += 1
        delay *= 2


async def next_lesson_to_deliver(user_id: int) -> int:
    """
    Возвращает номер следующего невыданного урока (1..4). Если всё выдано — 5.
    """
    rows = await fetch(
        "SELECT lesson_num FROM funnel_progress WHERE user_id=$1 ORDER BY lesson_num",
        user_id
    )
    delivered = {r["lesson_num"] for r in rows} if rows else set()
    for i in range(1, 5):
        if i not in delivered:
            return i
    return 5


async def send_lesson(bot: Bot, tg_user_id: int, user_row: dict, lesson_num: int) -> bool:
    """
    Отправляет карточку урока lesson_num пользователю и фиксирует выдачу.
    (упрощённая версия deliver_lesson из handlers, без typing-эффекта)
    """
    y = _load_yaml_content() or {}
    fun = (y.get("funnel") or {})
    lesson_urls = (fun.get("lesson_urls") or {})
    hw_questions = (fun.get("hw_questions") or {})

    url = (lesson_urls.get(lesson_num) if isinstance(lesson_urls, dict) else "") or ""
    hw_q = hw_questions.get(lesson_num, "Короткое ДЗ: ответь одной фразой.")

    await upsert_funnel_delivery(user_row["id"], lesson_num)

    text = f"<b>Урок {lesson_num}/4</b>\n"
    if url:
        text += f"Смотри на платформе: {url}\n\n"
    text += f"{hw_q}"

    ok = await _send_with_retries(bot, tg_user_id, text, reply_markup=lesson_keyboard(lesson_num))
    return ok


# ──────────────────────────────────────────────────────────────────────────────
# jobs
# ──────────────────────────────────────────────────────────────────────────────
async def job_daily_lessons(bot: Bot):
    """
    Ежедневная выдача уроков D1–D3 по пользователям в статусе lead_funnel.
    Правило: воронка стартует вручную (D0/Урок1). Планировщик даёт следующий
    урок раз в сутки в одно и то же время.
    """
    leads = await fetch("SELECT id, tg_user_id FROM users WHERE status='lead_funnel'")
    if not leads:
        logger.info("[job_daily_lessons] leads=0 — никому рассылать")
        return

    sent, skipped, errors = 0, 0, 0

    for u in leads:
        user_id = u["id"]
        tg_uid = u["tg_user_id"]
        try:
            nxt = await next_lesson_to_deliver(user_id)

            # планировщик шлёт только Урок 2–4; Урок 1 выдаётся вручную при нажатии в меню
            if nxt in (2, 3, 4):
                prev = nxt - 1
                prev_row = await fetchrow(
                    "SELECT delivered_at FROM funnel_progress WHERE user_id=$1 AND lesson_num=$2",
                    user_id, prev
                )
                if not prev_row:
                    # предыдущий ещё не выдавали — пропускаем до следующего дня
                    skipped += 1
                    continue

                user_row = await fetchrow("SELECT * FROM users WHERE id=$1", user_id)
                ok = await send_lesson(bot, tg_uid, user_row, nxt)
                if ok:
                    sent += 1
                else:
                    errors += 1
            else:
                skipped += 1
        except Exception as e:
            logger.exception("[job_daily_lessons] user_id=%s tg=%s failed: %s", user_id, tg_uid, e)
            errors += 1

    logger.info("[job_daily_lessons] sent=%s skipped=%s errors=%s", sent, skipped, errors)


async def job_soft_reminders(bot: Bot):
    """
    Мягкое напоминание: если урок не открыт 24 часа, отправляем 1 напоминание.
    Логика: ищем записи funnel_progress с delivered_at <= now-24h, opened_at is null,
    hw_status='pending'. После напоминания не меняем статус, но ограничиваем коридором [24h, 48h],
    чтобы не спамить.
    """
    rows = await fetch(
        """
        SELECT fp.id, fp.user_id, u.tg_user_id, fp.lesson_num, fp.delivered_at
        FROM funnel_progress fp
        JOIN users u ON u.id = fp.user_id
        WHERE fp.opened_at IS NULL
          AND fp.hw_status = 'pending'
          AND fp.delivered_at <= (NOW() - INTERVAL '24 hours')
          AND fp.delivered_at >= (NOW() - INTERVAL '48 hours')
        """
    )
    if not rows:
        logger.info("[job_soft_reminders] nothing to remind")
        return

    sent, errors = 0, 0
    for r in rows:
        try:
            ok = await _send_with_retries(
                bot,
                r["tg_user_id"],
                f"Небольшое напоминание 💛\nУрок {r['lesson_num']} ждёт тебя. Продолжим?"
            )
            if ok:
                sent += 1
            else:
                errors += 1
        except Exception as e:
            logger.warning("[job_soft_reminders] send failed for user_id=%s: %s", r["user_id"], e)
            errors += 1

    logger.info("[job_soft_reminders] sent=%s errors=%s", sent, errors)


async def job_form_reminders(bot: Bot):
    """Раз в час напоминаем о незавершённых анкетах."""
    rows = await fetch(
        """
        SELECT fs.id, fs.user_id, u.tg_user_id, fs.form_slug, fs.started_at, fs.last_reminder_at, fs.reminder_count
        FROM form_sessions fs
        JOIN users u ON u.id = fs.user_id
        WHERE fs.completed_at IS NULL
          AND fs.started_at <= (NOW() - INTERVAL '1 hour')
          AND (fs.last_reminder_at IS NULL OR fs.last_reminder_at <= (NOW() - INTERVAL '1 hour'))
        """
    )

    if not rows:
        logger.info("[job_form_reminders] nothing to remind")
        return

    template = await get_content(
        "forms.reminder_template",
        (
            "Напоминание: анкета «{form_label}» ждёт завершения.\n"
            "Если уже отправила форму, просто игнорируй это сообщение."
        ),
    )

    sent, errors = 0, 0
    for r in rows:
        try:
            label = FORM_LABELS.get(r["form_slug"], r["form_slug"])
            reminder_text = template.format(form_label=label)
            ok = await _send_with_retries(bot, r["tg_user_id"], reminder_text)
            if ok:
                await execute(
                    """
                    UPDATE form_sessions
                    SET last_reminder_at = NOW(),
                        reminder_count = COALESCE(reminder_count, 0) + 1
                    WHERE id = $1
                    """,
                    r["id"],
                )
                sent += 1
            else:
                errors += 1
        except Exception as e:
            logger.warning("[job_form_reminders] send failed for user_id=%s: %s", r["user_id"], e)
            errors += 1

    logger.info("[job_form_reminders] sent=%s errors=%s", sent, errors)


async def job_access_expiry_reminders(bot: Bot):
    """
    Напоминания об окончании доступа: -7 / -3 / 0 дней.
    Если клуб бесплатный (нет product_id) — только мягкое напоминание в день окончания (если дата задана).
    """
    if not AT_PRODUCT_ID_CLUB:
        rows = await fetch(
            """
            SELECT id, tg_user_id, access_until FROM users
            WHERE status='member_active'
              AND access_until IS NOT NULL
              AND DATE(access_until AT TIME ZONE 'UTC') = DATE(NOW() AT TIME ZONE 'UTC')
            """
        )
        if not rows:
            logger.info("[job_access_expiry_reminders] free club: nothing today")
            return

        sent, errors = 0, 0
        for u in rows:
            try:
                ok = await _send_with_retries(
                    bot,
                    u["tg_user_id"],
                    "Напоминание: сегодня истекает доступ к материалам клуба.\n"
                    "Доступ сейчас бесплатный — просто напиши нам в поддержку при необходимости продления."
                )
                if ok:
                    sent += 1
                else:
                    errors += 1
            except Exception as e:
                logger.warning("[job_access_expiry_reminders] send failed (free) user_id=%s: %s", u["id"], e)
                errors += 1
        logger.info("[job_access_expiry_reminders] free club: sent=%s errors=%s", sent, errors)
        return

    checkout_url = f"https://antitraining.example/checkout/{AT_PRODUCT_ID_CLUB}"

    async def _notify(rows, label: str, template: str):
        if not rows:
            logger.info("[job_access_expiry_reminders] %s: none", label)
            return
        sent, errors = 0, 0
        for u in rows:
            try:
                ok = await _send_with_retries(
                    bot,
                    u["tg_user_id"],
                    template.format(date=_msk_str(u["access_until"]), url=checkout_url)
                )
                if ok:
                    sent += 1
                else:
                    errors += 1
            except Exception as e:
                logger.warning("[job_access_expiry_reminders] %s failed user_id=%s: %s", label, u["id"], e)
                errors += 1
        logger.info("[job_access_expiry_reminders] %s: sent=%s errors=%s", label, sent, errors)

    # -7 дней
    rows7 = await fetch(
        """
        SELECT id, tg_user_id, access_until FROM users
        WHERE status='member_active'
          AND access_until IS NOT NULL
          AND DATE(access_until AT TIME ZONE 'UTC') = DATE((NOW() AT TIME ZONE 'UTC') + INTERVAL '7 days')
        """
    )
    await _notify(rows7, "D-7", "Доступ истекает {date}. Продлить: {url}")

    # -3 дня
    rows3 = await fetch(
        """
        SELECT id, tg_user_id, access_until FROM users
        WHERE status='member_active'
          AND access_until IS NOT NULL
          AND DATE(access_until AT TIME ZONE 'UTC') = DATE((NOW() AT TIME ZONE 'UTC') + INTERVAL '3 days')
        """
    )
    await _notify(rows3, "D-3", "Напоминание: осталось 3 дня до окончания доступа ({date}). Продлить: {url}")

    # 0 дней (сегодня)
    rows0 = await fetch(
        """
        SELECT id, tg_user_id, access_until FROM users
        WHERE status='member_active'
          AND access_until IS NOT NULL
          AND DATE(access_until AT TIME ZONE 'UTC') = DATE(NOW() AT TIME ZONE 'UTC')
        """
    )
    await _notify(rows0, "D-0", "Сегодня истекает доступ ({date}). Продлить: {url}")


# ──────────────────────────────────────────────────────────────────────────────
# public api
# ──────────────────────────────────────────────────────────────────────────────
async def setup_scheduler(bot: Bot, timezone_name: str, time_send_lessons: str):
    """
    Инициализирует и запускает планировщик.
    time_send_lessons — строка "HH:MM" по указанной таймзоне (например, Europe/Moscow).
    """
    global scheduler
    if scheduler:
        return scheduler

    # Разбираем время
    try:
        hh, mm = map(int, time_send_lessons.split(":"))
    except Exception:
        hh, mm = 10, 0  # дефолт 10:00

    scheduler = AsyncIOScheduler(timezone=timezone_name)

    # Ежедневная выдача уроков
    scheduler.add_job(
        job_daily_lessons,
        trigger=CronTrigger(hour=hh, minute=mm),
        kwargs={"bot": bot},
        id="daily_lessons",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 10,
    )

    # Мягкие напоминания по урокам — раз в день, через 1 час после уроков
    scheduler.add_job(
        job_soft_reminders,
        trigger=CronTrigger(hour=(hh + 1) % 24, minute=mm),
        kwargs={"bot": bot},
        id="soft_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 10,
    )

    # Напоминания о незавершённых анкетах — каждый час
    scheduler.add_job(
        job_form_reminders,
        trigger=CronTrigger(minute=mm),
        kwargs={"bot": bot},
        id="form_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 5,
    )

    # Напоминания об окончании доступа — каждый день в 11:00 по таймзоне
    scheduler.add_job(
        job_access_expiry_reminders,
        trigger=CronTrigger(hour=11, minute=0),
        kwargs={"bot": bot},
        id="access_expiry",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 10,
    )

    scheduler.start()
    logger.info("APScheduler started with timezone=%s; lessons at %02d:%02d", timezone_name, hh, mm)
    return scheduler


async def shutdown_scheduler():
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down")
    scheduler = None

