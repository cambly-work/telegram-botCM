# app.py
import hmac
import hashlib
import json
import logging
import os
import re
from typing import Optional, Any, Dict, List
from contextlib import asynccontextmanager
from pprint import pformat
from datetime import datetime, timedelta, timezone
from throttling_mw import ThrottleMiddleware
from fastapi import FastAPI, Request, HTTPException, Header, Body, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ──────────────────────────────────────────────────────────────────────────────
# Конфиг/окружение
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://example.com").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_me")

DB_DSN = os.getenv("DB_DSN", "postgresql://magnet:magnet_pwd@localhost:5432/magnetism")

BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Europe/Moscow")
TIME_SEND_LESSONS = os.getenv("TIME_SEND_LESSONS", "10:00")

AT_WEBHOOK_SHARED_SECRET = os.getenv("AT_WEBHOOK_SHARED_SECRET", "")
TELEGRAM_WEBHOOK_PATH = "/telegram/webhook"

# Клуб/ссылки
WELCOME_POST_URL = os.getenv("WELCOME_POST_URL", "https://t.me/")
CLUB_CHAT_ID = os.getenv("CLUB_CHAT_ID", "")  # должен быть числовой chat_id, бот — админ
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@codemagnetic")

# Настройки повторных попыток
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "0.5"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в окружении (.env).")


def _admin_ids() -> set[int]:
    ids = os.getenv("ADMIN_IDS", "")
    try:
        return {int(x.strip()) for x in ids.split(",") if x.strip()}
    except Exception:
        return set()


ADMIN_IDS = _admin_ids()

# ──────────────────────────────────────────────────────────────────────────────
# Логирование
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("code-magnetism")

# ──────────────────────────────────────────────────────────────────────────────
# Локальные модули
# ──────────────────────────────────────────────────────────────────────────────
from db import init_db, close_db, fetchrow, fetch, execute, is_db_connected  # базовые хелперы БД
from handlers import router as bot_router
from scheduler import setup_scheduler, shutdown_scheduler, get_scheduler_status

# ──────────────────────────────────────────────────────────────────────────────
# Инициализация бота/диспетчера
# ──────────────────────────────────────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(bot_router)  # важно: без условий
logger.info("Routers attached: %s", [r.name for r in dp.sub_routers])

# ──────────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────────
def compute_hmac_sha256(secret: str, body_bytes: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256)
    return mac.hexdigest()


async def notify_admins(text: str, max_retries: int = MAX_RETRIES) -> None:
    """Отправка уведомления всем администраторам с повторными попытками"""
    if not ADMIN_IDS:
        logger.warning("No admin IDs configured")
        return
    
    for admin_id in ADMIN_IDS:
        for attempt in range(max_retries):
            try:
                await bot.send_message(admin_id, f"⚠️ <b>Alert</b>\n{text}")
                logger.info("Notification sent to admin %s", admin_id)
                break
            except Exception as e:
                logger.warning("Attempt %d failed to send notification to %s: %s", 
                              attempt + 1, admin_id, e)
                if attempt == max_retries - 1:
                    logger.error("Failed to send notification to admin %s after %d attempts", 
                                admin_id, max_retries)
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _club_chat_id_as_int() -> Optional[int]:
    if not CLUB_CHAT_ID:
        return None
    try:
        return int(CLUB_CHAT_ID)
    except Exception:
        return None


async def gen_invite_link(max_retries: int = MAX_RETRIES) -> str:
    """Создать одноразовый инвайт в клуб с повторными попытками"""
    chat_id_int = _club_chat_id_as_int()
    if not chat_id_int:
        return "Инвайт выдаст администратор (CLUB_CHAT_ID не задан)."
    
    for attempt in range(max_retries):
        try:
            expire = int((now_utc() + timedelta(hours=24)).timestamp())
            link = await bot.create_chat_invite_link(
                chat_id=chat_id_int,
                expire_date=expire,
                member_limit=1,
                creates_join_request=False,
            )
            logger.info("Invite link generated successfully")
            return link.invite_link
        except Exception as e:
            logger.warning("Attempt %d failed to create invite: %s", attempt + 1, e)
            if attempt == max_retries - 1:
                logger.error("Failed to create invite after %d attempts", max_retries)
                return "Инвайт выдаст администратор (не удалось создать ссылку)."
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))


async def set_webhook(max_retries: int = MAX_RETRIES) -> bool:
    """Установка вебхука с повторными попытками"""
    url = f"{PUBLIC_BASE_URL}{TELEGRAM_WEBHOOK_PATH}?secret={WEBHOOK_SECRET}"
    logger.info("Setting Telegram webhook to: %s", url)

    for attempt in range(max_retries):
        try:
            # Сначала удаляем старый вебхук
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Old webhook deleted")
            
            # Устанавливаем новый
            ok = await bot.set_webhook(
                url=url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "my_chat_member"],
            )
            
            if ok:
                logger.info("Telegram webhook установлен: %s", url)
                return True
            else:
                logger.warning("Attempt %d: Telegram не принял webhook", attempt + 1)
                
        except Exception as e:
            logger.warning("Attempt %d failed to set webhook: %s", attempt + 1, e)
        
        if attempt < max_retries - 1:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
    
    logger.error("Failed to set webhook after %d attempts", max_retries)
    await notify_admins(f"❌ Не удалось установить вебхук после {max_retries} попыток")
    return False


def normalize_phone(phone: str) -> str:
    """Нормализация телефонного номера для сравнения"""
    if not phone:
        return ""
    
    # Убираем все нецифровые символы, кроме +
    phone = re.sub(r"[^\d+]", "", phone)
    
    # Нормализация российских номеров
    if phone.startswith("8") and len(phone) == 11:
        phone = "+7" + phone[1:]
    elif phone.startswith("7") and len(phone) == 11:
        phone = "+" + phone
    elif len(phone) == 10:
        phone = "+7" + phone
    
    return phone

# ──────────────────────────────────────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: инициализация БД/планировщика/вебхука...")
    
    try:
        await init_db(DB_DSN)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        await notify_admins(f"❌ Ошибка инициализации БД: {e}")
        raise
    
    try:
        await setup_scheduler(bot=bot, timezone_name=BOT_TIMEZONE, time_send_lessons=TIME_SEND_LESSONS)
        logger.info("Scheduler initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize scheduler: %s", e)
        await notify_admins(f"❌ Ошибка инициализации планировщика: {e}")
    
    try:
        webhook_ok = await set_webhook()
        if not webhook_ok:
            logger.warning("Webhook setup had issues, but continuing startup")
    except Exception as e:
        logger.error("Failed to set webhook: %s", e)
        await notify_admins(f"❌ Ошибка установки вебхука: {e}")
    
    logger.info("Startup завершён.")
    try:
        yield
    finally:
        logger.info("Shutdown: останавливаем планировщик/закрываем БД...")
        try:
            await shutdown_scheduler()
            logger.info("Scheduler stopped successfully")
        except Exception as e:
            logger.error("Error stopping scheduler: %s", e)
        
        try:
            await close_db()
            logger.info("Database closed successfully")
        except Exception as e:
            logger.error("Error closing database: %s", e)
        
        logger.info("Shutdown завершён.")

# ──────────────────────────────────────────────────────────────────────────────
# Приложение
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="CODE: Magnetism — Bot API", version="1.2.0", lifespan=lifespan)

# ──────────────────────────────────────────────────────────────────────────────
# Диагностика / Ops / Admin (через секрет в query)
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict:
    """Проверка здоровья приложения с проверкой БД"""
    db_status = await is_db_connected()
    scheduler_status = get_scheduler_status()
    
    status_code = status.HTTP_200_OK if db_status else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        content={
            "status": "ok" if db_status else "error",
            "service": "code-magnetism-bot",
            "version": app.version,
            "database": "connected" if db_status else "disconnected",
            "scheduler": scheduler_status,
            "timestamp": now_utc().isoformat()
        },
        status_code=status_code
    )


@app.get("/set-webhook")
async def http_set_webhook(secret: Optional[str] = None) -> dict:
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    
    success = await set_webhook()
    return {"ok": success, "message": "webhook set" if success else "webhook setup failed"}


@app.get("/debug/webhookinfo")
async def debug_webhookinfo(secret: Optional[str] = None) -> dict:
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    
    try:
        info = await bot.get_webhook_info()
        return json.loads(info.model_dump_json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting webhook info: {e}")


@app.get("/debug/config")
async def debug_config(secret: Optional[str] = None) -> dict:
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    
    return {
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "BOT_TIMEZONE": BOT_TIMEZONE,
        "TIME_SEND_LESSONS": TIME_SEND_LESSONS,
        "CLUB_CHAT_ID_present": bool(_club_chat_id_as_int()),
        "ADMIN_IDS": list(ADMIN_IDS),
        "MAX_RETRIES": MAX_RETRIES,
        "RETRY_DELAY": RETRY_DELAY,
    }


# Админ: тестовая отправка
@app.post("/admin/test-message")
async def admin_test_message(
    secret: str = Query(...),
    chat_id: int = Query(...),
    text: str = Body(..., embed=True),
):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")
    
    for attempt in range(MAX_RETRIES):
        try:
            await bot.send_message(chat_id, text)
            return {"ok": True, "attempt": attempt + 1}
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise HTTPException(status_code=400, detail=f"send failed after {MAX_RETRIES} attempts: {e}")
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))


# Админ: рассылка по сегментам
class BroadcastBody(BaseModel):
    segment: str = Field(..., description="all | lead_funnel | member_active | member_expired")
    text: str
    
    @validator('segment')
    def validate_segment(cls, v):
        if v not in {"all", "lead_funnel", "member_active", "member_expired"}:
            raise ValueError("invalid segment")
        return v


@app.post("/admin/broadcast")
async def admin_broadcast(
    body: BroadcastBody,
    secret: str = Query(...),
):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    segment = body.segment.strip().lower()
    
    if segment == "all":
        rows = await fetch("SELECT tg_user_id FROM users WHERE tg_user_id IS NOT NULL")
    else:
        rows = await fetch("SELECT tg_user_id FROM users WHERE status=$1 AND tg_user_id IS NOT NULL", segment)

    sent, errors = 0, 0
    tg_ids = [r["tg_user_id"] for r in rows if r.get("tg_user_id")]
    
    for tg_id in tg_ids:
        for attempt in range(MAX_RETRIES):
            try:
                await bot.send_message(tg_id, body.text)
                sent += 1
                break
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    logger.error("Failed to send to %s after %d attempts: %s", tg_id, MAX_RETRIES, e)
                    errors += 1
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return {"ok": True, "segment": segment, "sent": sent, "errors": errors, "total": len(tg_ids)}


# Админ: краткая статистика
@app.get("/admin/stats")
async def admin_stats(secret: str = Query(...)):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        # Базовая статистика пользователей
        total = await fetchrow("SELECT COUNT(*) AS c FROM users")
        lead = await fetchrow("SELECT COUNT(*) AS c FROM users WHERE status='lead_funnel'")
        active = await fetchrow("SELECT COUNT(*) AS c FROM users WHERE status='member_active'")
        expired = await fetchrow("SELECT COUNT(*) AS c FROM users WHERE status='member_expired'")

        # Статистика по урокам
        lesson_stats = await fetch("""
            SELECT lesson_num, hw_status, COUNT(*) as count 
            FROM funnel_progress 
            GROUP BY lesson_num, hw_status 
            ORDER BY lesson_num, hw_status
        """)

        # Пользователи, завершившие все 4 урока
        done4 = await fetchrow("""
            SELECT COUNT(DISTINCT user_id) AS c
            FROM funnel_progress
            WHERE hw_status='submitted'
            GROUP BY user_id
            HAVING COUNT(CASE WHEN lesson_num IN (1,2,3,4) AND hw_status='submitted' THEN 1 END) = 4
        """)

        # Статистика платежей
        payment_stats = await fetch("""
            SELECT status, COUNT(*) as count, MAX(created_at) as last_payment
            FROM payments 
            GROUP BY status
        """)

        return {
            "users": {
                "total": (total or {}).get("c", 0),
                "lead_funnel": (lead or {}).get("c", 0),
                "member_active": (active or {}).get("c", 0),
                "member_expired": (expired or {}).get("c", 0),
            },
            "funnel": {
                "completed_4of4": (done4 or {}).get("c", 0),
                "lesson_stats": lesson_stats or [],
            },
            "payments": payment_stats or [],
            "timestamp": now_utc().isoformat()
        }
    except Exception as e:
        logger.error("Error getting stats: %s", e)
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# Telegram webhook
# ──────────────────────────────────────────────────────────────────────────────
@app.post(TELEGRAM_WEBHOOK_PATH)
async def telegram_webhook(request: Request, secret: Optional[str] = None):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        data: Dict[str, Any] = await request.json()
    except Exception as e:
        logger.error("Invalid JSON in webhook: %s", e)
        raise HTTPException(status_code=400, detail="invalid json")

    # Логирование входящего обновления
    update_id = data.get("update_id", "unknown")
    logger.info("Incoming update %s", update_id)

    try:
        if "message" in data:
            m = data["message"]
            logger.info(
                "Message from %s (@%s): %s",
                m.get("from", {}).get("id"),
                m.get("from", {}).get("username"),
                (m.get("text") or m.get("caption") or "<non-text>")[:100]
            )
        elif "callback_query" in data:
            cq = data["callback_query"]
            logger.info(
                "Callback from %s (@%s): %s",
                cq.get("from", {}).get("id"),
                cq.get("from", {}).get("username"),
                cq.get("data")
            )
        elif "my_chat_member" in data:
            mc = data["my_chat_member"]
            logger.info(
                "Chat member update for %s (@%s): %s -> %s",
                mc.get("from", {}).get("id"),
                mc.get("from", {}).get("username"),
                mc.get("old_chat_member", {}).get("status"),
                mc.get("new_chat_member", {}).get("status"),
            )
    except Exception as e:
        logger.warning("Не удалось залогировать апдейт подробно: %s", e)

    # Обработка апдейта
    try:
        update = types.Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        logger.info("Update %s processed successfully", update_id)
    except Exception as e:
        logger.exception("Ошибка обработки Telegram update %s: %s", update_id, e)
        await notify_admins(
            f"Исключение при обработке апдейта {update_id}: "
            f"<code>{type(e).__name__}</code>\n{str(e)[:500]}"
        )
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)

    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# Antitraining: вебхуки оплаты
# ──────────────────────────────────────────────────────────────────────────────
class ATWebhookEnvelope(BaseModel):
    event: str
    data: dict


def _normalize_at_payload(data: dict) -> dict:
    """
    Нормализуем полезную нагрузку из АТ в унифицированный словарь.
    Ожидаемые поля (гибко): email, phone, product_id, order_id, status, access_days|access_until_ts.
    """
    d = data or {}
    email = (d.get("email") or d.get("customer_email") or "").strip().lower()
    phone = normalize_phone(d.get("phone") or d.get("customer_phone") or "")
    product_id = str(d.get("product_id") or d.get("tariff_id") or "")
    order_id = str(d.get("order_id") or d.get("id") or "")
    status = (d.get("status") or "").lower()  # paid/renew/refund/failed

    access_until: Optional[datetime] = None
    if "access_until_ts" in d:
        try:
            access_until = datetime.fromtimestamp(int(d["access_until_ts"]), tz=timezone.utc)
        except Exception:
            access_until = None
    elif "access_days" in d:
        try:
            access_until = now_utc() + timedelta(days=int(d["access_days"]))
        except Exception:
            access_until = None

    return {
        "email": email,
        "phone": phone,
        "product_id": product_id,
        "order_id": order_id,
        "status": status,  # может дублировать event
        "access_until": access_until,
        "raw": d,
    }


async def _find_user_by_contacts(email: str, phone: str) -> Optional[dict]:
    """Поиск пользователя по email или телефону с нормализацией"""
    # Поиск по email (точное совпадение)
    if email:
        row = await fetchrow("SELECT * FROM users WHERE LOWER(email)=LOWER($1)", email)
        if row:
            return row
    
    # Поиск по телефону (нормализованное сравнение)
    if phone:
        # Ищем точное совпадение
        row = await fetchrow("SELECT * FROM users WHERE phone=$1", phone)
        if row:
            return row
        
        # Ищем совпадение без + (для старых записей)
        if phone.startswith("+"):
            phone_without_plus = phone[1:]
            row = await fetchrow("SELECT * FROM users WHERE phone=$1", phone_without_plus)
            if row:
                return row
    
    return None


async def _upsert_payment(payload: dict, event: str, at_user_id: Optional[str] = None, access_until: Optional[datetime] = None):
    """Создание или обновление записи о платеже"""
    try:
        await execute(
            """INSERT INTO payments(order_id, at_user_id, email, phone, product_id, status, paid_at, access_until, raw_payload, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,NOW(),$7,$8,NOW())
               ON CONFLICT (order_id) DO UPDATE
               SET status=EXCLUDED.status, access_until=EXCLUDED.access_until, raw_payload=EXCLUDED.raw_payload, updated_at=NOW()""",
            payload.get("order_id") or "",
            at_user_id,
            payload.get("email"),
            payload.get("phone"),
            payload.get("product_id"),
            event,
            access_until,
            json.dumps(payload.get("raw") or {}, ensure_ascii=False),
        )
        logger.info("Payment record upserted for order %s", payload.get("order_id"))
    except Exception as e:
        logger.error("Не удалось записать payment (%s): %s", event, e)
        await notify_admins(f"❌ Ошибка записи платежа {payload.get('order_id')}: {e}")


async def _set_member_active(user_id: int, access_until: Optional[datetime]) -> None:
    """Активация статуса участника"""
    await execute(
        """UPDATE users
           SET status='member_active',
               access_until=$2,
               joined_club_at=COALESCE(joined_club_at, NOW()),
               updated_at=NOW()
           WHERE id=$1""",
        user_id, access_until
    )
    logger.info("User %s set as active member until %s", user_id, access_until)


async def _set_member_expired(user_id: int) -> None:
    """Деактивация статуса участника"""
    await execute(
        "UPDATE users SET status='member_expired', updated_at=NOW() WHERE id=$1",
        user_id
    )
    logger.info("User %s set as expired member", user_id)


@app.post("/webhooks/antitraining")
async def antitraining_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
):
    """
    Обработка событий от АТ: paid/renew/refund/failed.
    """
    body = await request.body()

    # Проверка подписи
    if AT_WEBHOOK_SHARED_SECRET:
        if not x_signature:
            logger.warning("Missing signature for AT webhook")
            raise HTTPException(status_code=401, detail="signature required")
        
        expected = compute_hmac_sha256(AT_WEBHOOK_SHARED_SECRET, body)
        if not hmac.compare_digest(expected, x_signature.lower()):
            logger.warning("Invalid signature for AT webhook")
            raise HTTPException(status_code=401, detail="invalid signature")

    # Парсинг JSON
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        logger.error("Invalid JSON in AT webhook: %s", e)
        raise HTTPException(status_code=400, detail="invalid json")

    # Обработка оболочки события
    try:
        env = ATWebhookEnvelope(**payload)
    except Exception as e:
        logger.warning("АТ вебхук с нестандартной структурой: %s", payload)
        return {"ok": True, "error": "invalid envelope"}

    event = env.event.lower().strip()
    norm = _normalize_at_payload(env.data)
    order_id = norm.get("order_id", "unknown")
    
    logger.info("АТ webhook event=%s order=%s", event, order_id)

    # Запись платежа
    user_row = await _find_user_by_contacts(norm["email"], norm["phone"])
    await _upsert_payment(
        norm, 
        event, 
        at_user_id=(user_row or {}).get("at_user_id"), 
        access_until=norm["access_until"]
    )

    # Если пользователь не найден
    if not user_row:
        logger.warning("User not found for AT event %s, order %s", event, order_id)
        await notify_admins(
            f"АТ: событие <b>{event}</b>, но пользователь не найден по email/phone.\n"
            f"email={norm['email'] or '—'}, phone={norm['phone'] or '—'}\n"
            f"order_id={order_id}"
        )
        return {"ok": True, "handled_event": event, "user_found": False}

    user_id = user_row["id"]
    tg_user_id = user_row["tg_user_id"]
    
    logger.info("Processing AT event %s for user %s (TG: %s)", event, user_id, tg_user_id)

    # Обработка различных событий
    if event in ("paid", "renew"):
        try:
            await _set_member_active(user_id, norm["access_until"])
            
            # Отправка инвайта и приветствия
            invite = await gen_invite_link()
            welcome = (
                f"🎉 Поздравляем! Тебе открыт доступ в клуб до {tz_aware_msk(norm['access_until'])}.\n\n"
                f"Твой инвайт (активен 24ч): {invite}\n\n"
                f"Начни отсюда: {WELCOME_POST_URL}"
            )
            
            for attempt in range(MAX_RETRIES):
                try:
                    await bot.send_message(tg_user_id, welcome)
                    logger.info("Welcome message sent to user %s", tg_user_id)
                    break
                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                        logger.error("Failed to send welcome to %s: %s", tg_user_id, e)
                        await notify_admins(
                            f"❌ Не удалось отправить приветствие пользователю {tg_user_id}: {e}"
                        )
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    
        except Exception as e:
            logger.error("Error processing paid event for user %s: %s", user_id, e)
            await notify_admins(
                f"❌ Ошибка обработки оплаты для пользователя {user_id}: {e}"
            )
            
        return {"ok": True, "handled_event": event, "user_found": True}

    elif event in ("refund", "failed"):
        try:
            await _set_member_expired(user_id)
            
            # Уведомление пользователя
            for attempt in range(MAX_RETRIES):
                try:
                    await bot.send_message(
                        tg_user_id,
                        "❌ Оплата не прошла или оформлён возврат. Доступ приостановлен.\n"
                        f"Поддержка: {SUPPORT_CONTACT}"
                    )
                    break
                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                        logger.error("Failed to send refund notification to %s: %s", tg_user_id, e)
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    
        except Exception as e:
            logger.error("Error processing refund event for user %s: %s", user_id, e)
            await notify_admins(
                f"❌ Ошибка обработки возврата для пользователя {user_id}: {e}"
            )
            
        return {"ok": True, "handled_event": event, "user_found": True}

    # Прочие события
    logger.info("Unhandled AT event: %s for order %s", event, order_id)
    return {"ok": True, "handled_event": event, "user_found": True}

# ──────────────────────────────────────────────────────────────────────────────
# Локальный запуск
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None)