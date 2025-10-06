# app.py
import asyncio
import csv
import hmac
import hashlib
import io
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional, Any, Dict, List, Literal
from contextlib import asynccontextmanager
from pprint import pformat
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

from throttling_mw import ThrottleMiddleware
from fastapi import FastAPI, Request, HTTPException, Header, Body, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from settings import ADMIN_IDS, STAFF_ADMIN_IDS, YOOMONEY_WEBHOOK_SECRET
from utils import normalize_phone

# ──────────────────────────────────────────────────────────────────────────────
# Конфиг/окружение
# ──────────────────────────────────────────────────────────────────────────────


def _env_flag(name: str, default: str = "0") -> bool:
    value = os.getenv(name, default)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
NGROK_AUTOFETCH = _env_flag("NGROK_AUTOFETCH")
NGROK_API_URL = os.getenv("NGROK_API_URL", "").strip()
NGROK_API_TOKEN = os.getenv("NGROK_API_TOKEN", "").strip()
NGROK_TUNNEL_NAME = os.getenv("NGROK_TUNNEL_NAME", "").strip()


def _fetch_ngrok_public_url(api_url: str, api_token: str, tunnel_name: str) -> Optional[str]:
    """Получить публичный URL активного туннеля ngrok"""
    logger_ngrok = logging.getLogger("code-magnetism")

    api_url = (api_url or "").strip()
    if not api_url:
        logger_ngrok.warning("Ngrok autofetch enabled but NGROK_API_URL is not set")
        return None

    endpoint = api_url.rstrip("/")

    try:
        request = urllib.request.Request(endpoint)
        request.add_header("User-Agent", "code-magnetism-bot/1.0")

        if api_token:
            request.add_header("Authorization", f"Bearer {api_token}")
            request.add_header("Ngrok-Version", "2")

        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger_ngrok.warning("Failed to fetch ngrok data from %s: %s", endpoint, exc)
        return None
    except Exception as exc:  # noqa: BLE001 — хотим логировать любую ошибку
        logger_ngrok.warning("Unexpected error fetching ngrok data from %s: %s", endpoint, exc)
        return None

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — чтобы не падать из-за формата ответа
        logger_ngrok.warning("Failed to decode ngrok response from %s: %s", endpoint, exc)
        return None

    entries: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        tunnels = payload.get("tunnels")
        endpoints = payload.get("endpoints")

        if isinstance(tunnels, list):
            entries = [t for t in tunnels if isinstance(t, dict)]
        elif isinstance(endpoints, list):
            entries = [e for e in endpoints if isinstance(e, dict)]

    if not entries:
        logger_ngrok.warning("Ngrok response from %s did not include tunnels/endpoints", endpoint)
        return None

    candidates: List[str] = []
    for entry in entries:
        url = entry.get("public_url")

        if not url:
            proto = entry.get("proto") or entry.get("scheme")
            hostport = entry.get("hostport")
            if proto and hostport:
                url = f"{proto}://{hostport}"

        if not url:
            continue

        if tunnel_name:
            identifiers = [
                entry.get("name"),
                entry.get("id"),
                entry.get("domain"),
                entry.get("forwards_to"),
            ]

            match = tunnel_name in url
            if not match:
                for ident in identifiers:
                    if ident and tunnel_name in str(ident):
                        match = True
                        break

            if not match:
                continue

        candidates.append(url)

    if not candidates:
        if tunnel_name:
            logger_ngrok.warning("Ngrok public URL not found for tunnel '%s'", tunnel_name)
        else:
            logger_ngrok.warning("Ngrok response did not contain usable public URLs")
        return None

    candidates.sort(key=lambda value: (0 if value.startswith("https://") else 1, value))
    return candidates[0]


def _resolve_public_base_url(
    env_value: str,
    autofetch: bool,
    api_url: str,
    api_token: str,
    tunnel_name: str,
) -> tuple[str, str, bool]:
    """Выбрать PUBLIC_BASE_URL с учётом автоподстановки ngrok"""

    env_value = (env_value or "").strip()

    fallback_url = "https://example.com"
    fallback_source = "default"
    if env_value and env_value.lower() not in {"auto", "ngrok"}:
        fallback_url = env_value
        fallback_source = "env"

    prefer_ngrok = autofetch or env_value.lower() in {"", "auto", "ngrok"}
    if prefer_ngrok:
        ngrok_url = _fetch_ngrok_public_url(api_url, api_token, tunnel_name)
        if ngrok_url:
            return ngrok_url.rstrip("/"), "ngrok", True

    return fallback_url.rstrip("/"), fallback_source, prefer_ngrok


PUBLIC_BASE_URL, PUBLIC_BASE_URL_SOURCE, NGROK_FETCH_ATTEMPTED = _resolve_public_base_url(
    os.getenv("PUBLIC_BASE_URL", ""),
    NGROK_AUTOFETCH,
    NGROK_API_URL,
    NGROK_API_TOKEN,
    NGROK_TUNNEL_NAME,
)
NGROK_FETCH_SUCCEEDED = PUBLIC_BASE_URL_SOURCE == "ngrok"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_me")

DB_DSN = os.getenv("DB_DSN", "postgresql://magnet:magnet_pwd@localhost:5432/magnetism")

BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Europe/Moscow")
TIME_SEND_LESSONS = os.getenv("TIME_SEND_LESSONS", "10:00")

AT_WEBHOOK_SHARED_SECRET = os.getenv("AT_WEBHOOK_SHARED_SECRET", "")
TELEGRAM_WEBHOOK_PATH = "/telegram/webhook"

SKIP_DB_INIT = _env_flag("SKIP_DB_INIT")
SKIP_SCHEDULER = _env_flag("SKIP_SCHEDULER")
SKIP_WEBHOOK_SETUP = _env_flag("SKIP_WEBHOOK")
SKIP_ADMIN_NOTIFICATIONS = _env_flag("SKIP_ADMIN_NOTIFICATIONS")

# Клуб/ссылки
WELCOME_POST_URL = os.getenv("WELCOME_POST_URL", "https://t.me/")
CLUB_CHAT_ID = os.getenv("CLUB_CHAT_ID", "")  # должен быть числовой chat_id, бот — админ
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@codemagnetic")

# Настройки повторных попыток
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "0.5"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в окружении (.env).")

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

logger.info("PUBLIC_BASE_URL resolved (%s): %s", PUBLIC_BASE_URL_SOURCE, PUBLIC_BASE_URL)
if NGROK_FETCH_ATTEMPTED and not NGROK_FETCH_SUCCEEDED:
    logger.warning(
        "Ngrok autofetch requested but failed; using %s URL instead",
        PUBLIC_BASE_URL_SOURCE,
    )

# ──────────────────────────────────────────────────────────────────────────────
# Локальные модули
# ──────────────────────────────────────────────────────────────────────────────
from db import (
    init_db,
    close_db,
    fetchrow,
    fetch,
    execute,
    is_db_connected,
)  # базовые хелперы БД
from handlers import (
    router as bot_router,
    tz_aware_msk,
    get_user_progress,
    sync_user_progress,
)
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
    if SKIP_ADMIN_NOTIFICATIONS:
        logger.info("Skipping admin notification (disabled): %s", text)
        return

    recipients = list(ADMIN_IDS)
    recipients.extend(staff_id for staff_id in STAFF_ADMIN_IDS if staff_id not in ADMIN_IDS)

    if not recipients:
        logger.warning("No admin or staff IDs configured")
        return

    for admin_id in recipients:
        for attempt in range(max_retries):
            try:
                await bot.send_message(admin_id, f"⚠️ <b>Alert</b>\n{text}")
                logger.info("Notification sent to admin/staff %s", admin_id)
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
    if SKIP_WEBHOOK_SETUP:
        logger.info("Skipping Telegram webhook setup (disabled via SKIP_WEBHOOK)")
        return True

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
# ──────────────────────────────────────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: инициализация БД/планировщика/вебхука...")

    if SKIP_DB_INIT:
        logger.info("Startup: SKIP_DB_INIT=1 — пропускаем инициализацию БД")
    else:
        try:
            await init_db(DB_DSN)
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize database: %s", e)
            await notify_admins(f"❌ Ошибка инициализации БД: {e}")
            raise

    if SKIP_SCHEDULER:
        logger.info("Startup: SKIP_SCHEDULER=1 — пропускаем запуск планировщика")
    else:
        try:
            await setup_scheduler(bot=bot, timezone_name=BOT_TIMEZONE, time_send_lessons=TIME_SEND_LESSONS)
            logger.info("Scheduler initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize scheduler: %s", e)
            await notify_admins(f"❌ Ошибка инициализации планировщика: {e}")

    if SKIP_WEBHOOK_SETUP:
        logger.info("Startup: SKIP_WEBHOOK=1 — пропускаем установку вебхука")
    else:
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
            if not SKIP_SCHEDULER:
                await shutdown_scheduler()
                logger.info("Scheduler stopped successfully")
        except Exception as e:
            logger.error("Error stopping scheduler: %s", e)

        try:
            if not SKIP_DB_INIT:
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
    db_status = True if SKIP_DB_INIT else await is_db_connected()
    scheduler_status = {"status": "disabled", "jobs": 0} if SKIP_SCHEDULER else get_scheduler_status()

    status_code = status.HTTP_200_OK if db_status else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        content={
            "status": "ok" if db_status else "error",
            "service": "code-magnetism-bot",
            "version": app.version,
            "database": "skipped" if SKIP_DB_INIT else ("connected" if db_status else "disconnected"),
            "scheduler": scheduler_status,
            "flags": {
                "skip_db_init": SKIP_DB_INIT,
                "skip_scheduler": SKIP_SCHEDULER,
                "skip_webhook": SKIP_WEBHOOK_SETUP,
                "skip_admin_notifications": SKIP_ADMIN_NOTIFICATIONS,
            },
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
        "PUBLIC_BASE_URL_source": PUBLIC_BASE_URL_SOURCE,
        "BOT_TIMEZONE": BOT_TIMEZONE,
        "TIME_SEND_LESSONS": TIME_SEND_LESSONS,
        "CLUB_CHAT_ID_present": bool(_club_chat_id_as_int()),
        "ADMIN_IDS": list(ADMIN_IDS),
        "MAX_RETRIES": MAX_RETRIES,
        "RETRY_DELAY": RETRY_DELAY,
        "NGROK": {
            "autofetch": NGROK_AUTOFETCH,
            "fetch_attempted": NGROK_FETCH_ATTEMPTED,
            "fetch_succeeded": NGROK_FETCH_SUCCEEDED,
            "api_url_present": bool(NGROK_API_URL),
            "tunnel_name": NGROK_TUNNEL_NAME,
        },
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

    @field_validator('segment')
    def validate_segment(cls, v):
        if v not in {"all", "lead_funnel", "member_active", "member_expired"}:
            raise ValueError("invalid segment")
        return v


class ProgressLessonUpdate(BaseModel):
    lesson: int = Field(..., ge=1, le=4)
    status: Optional[str] = Field(
        default=None,
        description="submitted | pending | skipped",
    )
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    hw_answer: Optional[str] = None
    feedback: Optional[List[str]] = None
    reset: bool = False

    @field_validator("status")
    def validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"submitted", "pending", "skipped"}:
            raise ValueError("invalid status")
        return normalized


class ProgressSyncBody(BaseModel):
    user_id: Optional[int] = Field(default=None, description="internal user id")
    tg_user_id: Optional[int] = Field(default=None, description="telegram user id")
    lessons: List[ProgressLessonUpdate] = Field(default_factory=list)
    actor_id: Optional[int] = Field(default=None, description="admin id for logging")


class HomeworkImportBody(BaseModel):
    csv: str = Field(..., description="CSV payload exported from /admin/homework/export")
    delimiter: Optional[str] = Field(default=None, description="Custom CSV delimiter")
    actor_id: Optional[int] = Field(default=None, description="Admin performing the import")
    dry_run: bool = Field(default=False, description="Skip applying changes, only validate")

    @field_validator("delimiter")
    def validate_delimiter(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        if len(value) != 1:
            raise ValueError("delimiter must be a single character")
        return value


async def _resolve_progress_user(
    user_id: Optional[int],
    tg_user_id: Optional[int],
) -> tuple[int, Dict[str, Any]]:
    if user_id:
        user_row = await fetchrow(
            "SELECT id, status, access_until FROM users WHERE id=$1",
            user_id,
        )
        if not user_row:
            raise HTTPException(status_code=404, detail="user not found")
        if tg_user_id:
            tg_row = await fetchrow(
                "SELECT id FROM users WHERE tg_user_id=$1",
                tg_user_id,
            )
            if not tg_row or tg_row["id"] != user_row["id"]:
                raise HTTPException(
                    status_code=400,
                    detail="user_id and tg_user_id refer to different users",
                )
        return user_row["id"], dict(user_row)

    if tg_user_id:
        user_row = await fetchrow(
            "SELECT id, status, access_until FROM users WHERE tg_user_id=$1",
            tg_user_id,
        )
        if not user_row:
            raise HTTPException(status_code=404, detail="user not found")
        return user_row["id"], dict(user_row)

    raise HTTPException(status_code=400, detail="user_id or tg_user_id required")


def _progress_to_payload(progress: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    lessons: List[Dict[str, Any]] = []
    for lesson_num in sorted(progress.keys()):
        info = progress.get(lesson_num) or {}
        lessons.append(
            {
                "lesson": lesson_num,
                "hw_status": info.get("hw_status"),
                "delivered": bool(info.get("delivered")),
                "delivered_at": info.get("delivered_at"),
                "opened_at": info.get("opened_at"),
                "hw_answer": info.get("hw_answer"),
                "feedback_count": info.get("feedback_count"),
                "feedback_types": info.get("feedback_types"),
            }
        )
    return lessons


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
        done4_row = await fetchrow("""
            SELECT COUNT(*) AS c
            FROM (
                SELECT user_id
                FROM funnel_progress
                WHERE hw_status = 'submitted'
                GROUP BY user_id
                HAVING COUNT(DISTINCT CASE
                    WHEN lesson_num BETWEEN 1 AND 4 THEN lesson_num
                END) = 4
            ) AS completed
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
                "completed_4of4": (done4_row or {}).get("c", 0),
                "lesson_stats": lesson_stats or [],
            },
            "payments": payment_stats or [],
            "timestamp": now_utc().isoformat()
        }
    except Exception as e:
        logger.error("Error getting stats: %s", e)
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {e}")


@app.get("/admin/homework/export")
async def admin_homework_export(
    secret: str = Query(...),
    segment: Optional[str] = Query(default="all"),
) -> PlainTextResponse:
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    raw_segment = segment if isinstance(segment, str) else "all"
    segment_normalized = (raw_segment or "all").strip().lower()
    allowed_segments = {"all", "lead_funnel", "member_active", "member_expired"}
    if segment_normalized not in allowed_segments:
        raise HTTPException(status_code=400, detail="invalid segment")

    params: List[Any] = []
    query = (
        "SELECT id, tg_user_id, email, phone, status, access_until, funnel_complete "
        "FROM users"
    )
    if segment_normalized != "all":
        query += " WHERE status=$1"
        params.append(segment_normalized)
    query += " ORDER BY id"

    users_rows = await fetch(query, *params)
    user_ids = [row["id"] for row in users_rows or []]

    progress_rows: List[Dict[str, Any]] = []
    if user_ids:
        progress_rows = await fetch(
            """
            SELECT user_id, lesson_num, delivered_at, opened_at, hw_status, hw_answer
            FROM funnel_progress
            WHERE user_id = ANY($1::int[])
            """,
            user_ids,
        )

    progress_map: Dict[tuple[int, int], Dict[str, Any]] = {}
    for row in progress_rows or []:
        key = (row["user_id"], row["lesson_num"])
        progress_map[key] = row

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "user_id",
            "tg_user_id",
            "email",
            "phone",
            "status",
            "access_until",
            "funnel_complete",
            "lesson",
            "hw_status",
            "delivered_at",
            "opened_at",
            "hw_answer",
        ]
    )

    for user in users_rows or []:
        for lesson in range(1, 5):
            progress = progress_map.get((user["id"], lesson)) or {}
            writer.writerow(
                [
                    user["id"],
                    user.get("tg_user_id") or "",
                    (user.get("email") or "").strip(),
                    (user.get("phone") or "").strip(),
                    user.get("status") or "",
                    user.get("access_until").isoformat() if user.get("access_until") else "",
                    "1" if user.get("funnel_complete") else "0",
                    lesson,
                    progress.get("hw_status") or "",
                    progress.get("delivered_at").isoformat() if progress.get("delivered_at") else "",
                    progress.get("opened_at").isoformat() if progress.get("opened_at") else "",
                    (progress.get("hw_answer") or "").replace("\n", " "),
                ]
            )

    content = buffer.getvalue()
    headers = {
        "Content-Disposition": "attachment; filename=homework-export.csv",
    }
    return PlainTextResponse(content, media_type="text/csv", headers=headers)


@app.post("/admin/homework/import")
async def admin_homework_import(
    body: HomeworkImportBody,
    secret: str = Query(...),
):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    csv_text = (body.csv or "").strip()
    if not csv_text:
        raise HTTPException(status_code=400, detail="csv payload is empty")

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=body.delimiter or ",")
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="csv header is empty")

    errors: List[str] = []
    updates_by_user: Dict[int, List[Dict[str, Any]]] = {}
    resolved_cache: Dict[str, int] = {}

    async def _resolve_user_id(row: Dict[str, Any], line_no: int) -> Optional[int]:
        user_id_raw = str(row.get("user_id") or row.get("id") or "").strip()
        if user_id_raw:
            try:
                return int(user_id_raw)
            except ValueError:
                errors.append(f"line {line_no}: invalid user_id '{user_id_raw}'")
                return None

        tg_raw = str(row.get("tg_user_id") or row.get("telegram_id") or "").strip()
        if tg_raw:
            cache_key = f"tg:{tg_raw}"
            if cache_key in resolved_cache:
                return resolved_cache[cache_key]
            try:
                tg_id = int(tg_raw)
            except ValueError:
                errors.append(f"line {line_no}: invalid tg_user_id '{tg_raw}'")
                return None
            user_row = await fetchrow("SELECT id FROM users WHERE tg_user_id=$1", tg_id)
            if not user_row:
                errors.append(f"line {line_no}: user with tg_user_id={tg_id} not found")
                return None
            resolved_cache[cache_key] = user_row["id"]
            return user_row["id"]

        email = str(row.get("email") or "").strip().lower()
        phone = str(row.get("phone") or "").strip()
        if email or phone:
            cache_key = f"contact:{email}:{phone}"
            if cache_key in resolved_cache:
                return resolved_cache[cache_key]
            user_row = await _find_user_by_contacts(email, phone)
            if not user_row:
                errors.append(
                    f"line {line_no}: user not found by contacts email={email or '—'}, phone={phone or '—'}"
                )
                return None
            resolved_cache[cache_key] = user_row["id"]
            return user_row["id"]

        errors.append(f"line {line_no}: missing user reference (user_id, tg_user_id or contacts)")
        return None

    for idx, row in enumerate(reader, start=2):
        user_id = await _resolve_user_id(row, idx)
        if not user_id:
            continue

        lesson_raw = str(row.get("lesson") or row.get("lesson_num") or "").strip()
        if not lesson_raw:
            errors.append(f"line {idx}: lesson is required")
            continue
        try:
            lesson = int(lesson_raw)
        except ValueError:
            errors.append(f"line {idx}: invalid lesson '{lesson_raw}'")
            continue
        if lesson not in (1, 2, 3, 4):
            errors.append(f"line {idx}: lesson must be between 1 and 4")
            continue

        status_raw = str(row.get("hw_status") or row.get("status") or "").strip().lower()
        status_value = status_raw or None
        if status_value and status_value not in {"submitted", "pending", "skipped"}:
            errors.append(f"line {idx}: invalid hw_status '{status_value}'")
            continue

        delivered_raw = row.get("delivered_at") or row.get("delivered")
        opened_raw = row.get("opened_at") or row.get("opened")
        delivered_dt = _parse_datetime(delivered_raw) if delivered_raw else None
        opened_dt = _parse_datetime(opened_raw) if opened_raw else None
        if delivered_raw and delivered_dt is None:
            errors.append(f"line {idx}: invalid delivered_at '{delivered_raw}'")
            continue
        if opened_raw and opened_dt is None:
            errors.append(f"line {idx}: invalid opened_at '{opened_raw}'")
            continue

        answer = row.get("hw_answer") or row.get("answer")
        if isinstance(answer, str):
            answer_value = answer.strip()
        else:
            answer_value = answer

        reset_raw = str(row.get("reset") or row.get("clear") or "").strip().lower()
        reset_flag = reset_raw in {"1", "true", "yes", "y"}

        updates_by_user.setdefault(user_id, []).append(
            {
                "lesson": lesson,
                "status": status_value,
                "delivered_at": delivered_dt,
                "opened_at": opened_dt,
                "hw_answer": answer_value,
                "reset": reset_flag,
            }
        )

    if errors:
        raise HTTPException(status_code=400, detail={"message": "import has errors", "errors": errors})

    applied_users: List[int] = []
    if not body.dry_run:
        for user_id, updates in updates_by_user.items():
            try:
                await sync_user_progress(user_id, updates, actor_id=body.actor_id)
                applied_users.append(user_id)
            except ValueError as exc:
                logger.error("Homework import validation failed for user %s: %s", user_id, exc)
                await notify_admins(
                    f"❌ Импорт ДЗ: ошибка валидации для пользователя {user_id}: {exc}"
                )
                errors.append(f"user {user_id}: {exc}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Homework import failed for user %s: %s", user_id, exc)
                await notify_admins(
                    f"❌ Импорт ДЗ: неожиданная ошибка для пользователя {user_id}: {exc}"
                )
                errors.append(f"user {user_id}: unexpected error {exc}")

    if errors:
        raise HTTPException(status_code=500, detail={"message": "failed to apply homework", "errors": errors})

    total_rows = sum(len(rows) for rows in updates_by_user.values())
    return {
        "ok": True,
        "dry_run": body.dry_run,
        "processed_rows": total_rows,
        "affected_users": len(updates_by_user),
        "applied_users": applied_users,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Telegram webhook
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/admin/progress")
async def admin_progress_get(
    secret: str = Query(...),
    user_id: Optional[int] = Query(None),
    tg_user_id: Optional[int] = Query(None),
):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    resolved_id, user_row = await _resolve_progress_user(user_id, tg_user_id)
    progress = await get_user_progress(resolved_id)

    return {
        "user_id": resolved_id,
        "status": user_row.get("status"),
        "access_until": user_row.get("access_until"),
        "progress": _progress_to_payload(progress),
    }


@app.post("/admin/progress/sync")
async def admin_progress_sync(
    body: ProgressSyncBody,
    secret: str = Query(...),
):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    resolved_id, user_row = await _resolve_progress_user(body.user_id, body.tg_user_id)
    if not body.lessons:
        raise HTTPException(status_code=400, detail="lessons payload is empty")

    updates: List[Dict[str, Any]] = []
    for lesson in body.lessons:
        updates.append(
            {
                "lesson": lesson.lesson,
                "status": lesson.status,
                "delivered_at": lesson.delivered_at,
                "opened_at": lesson.opened_at,
                "hw_answer": lesson.hw_answer,
                "feedback": lesson.feedback,
                "reset": lesson.reset,
            }
        )

    try:
        await sync_user_progress(resolved_id, updates, actor_id=body.actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    progress = await get_user_progress(resolved_id)
    return {
        "user_id": resolved_id,
        "status": user_row.get("status"),
        "access_until": user_row.get("access_until"),
        "progress": _progress_to_payload(progress),
    }


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
        message = (
            f"Исключение при обработке апдейта {update_id}: "
            f"<code>{type(e).__name__}</code>\n{str(e)[:500]}"
        )
        await notify_admins(message)
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


PAYMENT_STATUS_ALIASES = {
    "paid": "paid",
    "succeeded": "paid",
    "success": "paid",
    "renew": "renew",
    "refund": "refund",
    "failed": "failed",
}


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse ISO string, timestamp or datetime into an aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        raw = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return None


def _normalize_yoomoney_payload(payload: dict) -> tuple[str, dict, dict, dict]:
    """Normalize YooMoney payload into unified structure for persistence."""
    data = payload or {}
    obj = data.get("object") or {}
    metadata = obj.get("metadata") or {}

    event_raw = (
        data.get("event")
        or data.get("notification_type")
        or obj.get("status")
        or data.get("status")
        or ""
    ).strip().lower()
    if "." in event_raw:
        event_raw = event_raw.split(".")[-1]

    status_raw = (obj.get("status") or data.get("status") or event_raw).strip().lower()
    if "." in status_raw:
        status_raw = status_raw.split(".")[-1]

    email = (metadata.get("email") or obj.get("email") or data.get("email") or "").strip().lower()
    phone = normalize_phone(metadata.get("phone") or obj.get("phone") or data.get("phone") or "")
    product_id = str(metadata.get("product_id") or obj.get("description") or data.get("product_id") or "")
    order_id = str(
        metadata.get("order_id")
        or obj.get("id")
        or obj.get("payment_id")
        or data.get("id")
        or ""
    )

    access_until = (
        _parse_datetime(metadata.get("access_until"))
        or _parse_datetime(metadata.get("access_until_ts"))
        or _parse_datetime(obj.get("access_until"))
        or _parse_datetime(obj.get("expires_at"))
        or _parse_datetime(data.get("access_until"))
    )

    if access_until is None:
        access_days = metadata.get("access_days") or obj.get("access_days")
        if access_days not in (None, ""):
            try:
                access_until = now_utc() + timedelta(days=int(access_days))
            except Exception:
                access_until = None

    amount_info = obj.get("amount") or {}
    amount_value = str(amount_info.get("value") or "").strip()
    currency = str(amount_info.get("currency") or "").strip()

    normalized = {
        "email": email,
        "phone": phone,
        "product_id": product_id,
        "order_id": order_id,
        "status": status_raw or event_raw,
        "access_until": access_until,
        "raw": data,
        "amount_value": amount_value,
        "currency": currency,
    }

    return status_raw or event_raw or "unknown", normalized, metadata, obj


async def _find_user_for_yoomoney(metadata: dict, email: str, phone: str) -> Optional[dict]:
    """Find user using metadata hints or fallback to contacts."""
    metadata = metadata or {}

    for key in ("user_id", "userId", "uid"):
        value = metadata.get(key)
        if value in (None, ""):
            continue
        try:
            user = await fetchrow("SELECT * FROM users WHERE id=$1", int(value))
        except Exception:
            user = None
        if user:
            return user

    for key in ("tg_user_id", "telegram_id", "telegram_user_id"):
        value = metadata.get(key)
        if value in (None, ""):
            continue
        try:
            user = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", int(value))
        except Exception:
            user = None
        if user:
            return user

    return await _find_user_by_contacts(email, phone)


def _resolve_payment_status(*candidates: Optional[str]) -> str:
    """Возвращает допустимый статус платежа на основе списка кандидатов."""
    for raw in candidates:
        normalized = (raw or "").strip().lower()
        if normalized in PAYMENT_STATUS_ALIASES:
            return PAYMENT_STATUS_ALIASES[normalized]
    return "failed"


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
    status = _resolve_payment_status(event, payload.get("status"))
    if status == "failed" and (event or payload.get("status")):
        logger.warning(
            "Нераспознанный статус платежа %s/%s для заказа %s — сохраняем как 'failed'",
            event,
            payload.get("status"),
            payload.get("order_id") or "",
        )
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
            status,
            access_until,
            json.dumps(payload.get("raw") or {}, ensure_ascii=False),
        )
        logger.info("Payment record upserted for order %s", payload.get("order_id"))
    except Exception as e:
        logger.error("Не удалось записать payment (%s): %s", status, e)
        await notify_admins(f"❌ Ошибка записи платежа {payload.get('order_id')}: {e}")


async def _set_member_active(user_id: int, access_until: Optional[datetime]) -> None:
    """Активация статуса участника"""
    await execute(
        """UPDATE users
           SET status='member_active',
               access_until=$2,
               joined_club_at=COALESCE(joined_club_at, NOW()),
               funnel_complete=TRUE,
               updated_at=NOW()
           WHERE id=$1""",
        user_id, access_until
    )
    logger.info("User %s set as active member until %s", user_id, access_until)


async def _set_member_expired(user_id: int) -> None:
    """Деактивация статуса участника"""
    await execute(
        "UPDATE users SET status='member_expired', funnel_complete=FALSE, updated_at=NOW() WHERE id=$1",
        user_id
    )
    logger.info("User %s set as expired member", user_id)


async def _mark_funnel_complete(user_id: int) -> None:
    """Отметить, что пользователь завершил бесплатную воронку."""
    try:
        await execute(
            """
            INSERT INTO funnel_progress (user_id, lesson_num, delivered_at, opened_at, hw_status)
            SELECT $1, lesson_num, NOW(), NOW(), 'submitted'
            FROM generate_series(1, 4) AS lesson_num
            ON CONFLICT (user_id, lesson_num) DO UPDATE
                SET hw_status='submitted',
                    delivered_at=COALESCE(funnel_progress.delivered_at, EXCLUDED.delivered_at),
                    opened_at=COALESCE(funnel_progress.opened_at, EXCLUDED.opened_at)
            """,
            user_id,
        )
        await execute(
            "UPDATE users SET funnel_complete=TRUE, updated_at=NOW() WHERE id=$1",
            user_id,
        )
        logger.info("Funnel marked complete for user %s", user_id)
    except Exception as exc:  # noqa: BLE001 — логируем любые ошибки
        logger.exception("Failed to mark funnel complete for user %s: %s", user_id, exc)
        await notify_admins(
            f"⚠️ Не удалось отметить завершение воронки для пользователя {user_id}: {exc}"
        )


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
        message = (
            f"АТ: событие <b>{event}</b>, но пользователь не найден по email/phone.\n"
            f"email={norm['email'] or '—'}, phone={norm['phone'] or '—'}\n"
            f"order_id={order_id}"
        )
        await notify_admins(message)
        return {"ok": True, "handled_event": event, "user_found": False}

    user_id = user_row["id"]
    tg_user_id = user_row["tg_user_id"]
    
    logger.info("Processing AT event %s for user %s (TG: %s)", event, user_id, tg_user_id)

    # Обработка различных событий
    response_payload: Dict[str, Any] = {"ok": True, "handled_event": event, "user_found": True}

    if event in ("paid", "renew"):
        try:
            await _set_member_active(user_id, norm["access_until"])
            await _mark_funnel_complete(user_id)

            # Отправка инвайта и приветствия
            invite = await gen_invite_link()
            access_label = tz_aware_msk(norm["access_until"]) if norm.get("access_until") else "—"
            welcome = (
                f"🎉 Поздравляем! Тебе открыт доступ в клуб до {access_label}.\n\n"
                f"Твой инвайт (активен 24ч): {invite}\n\n"
                f"Начни отсюда: {WELCOME_POST_URL}"
            )

            response_payload["invite_link"] = invite
            if norm.get("access_until"):
                response_payload["access_until"] = tz_aware_msk(norm["access_until"])
            response_payload["member_status"] = "member_active"

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

        return response_payload

    elif event in ("refund", "failed"):
        try:
            await _set_member_expired(user_id)
            response_payload["member_status"] = "member_expired"

            # Уведомление пользователя
            for attempt in range(MAX_RETRIES):
                try:
                    await bot.send_message(
                        tg_user_id,
                        f"❌ Оплата не прошла или оформлён возврат. Доступ приостановлен.\nПоддержка: {SUPPORT_CONTACT}"
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

        return response_payload

    # Прочие события
    logger.info("Unhandled AT event: %s for order %s", event, order_id)
    return response_payload


@app.post("/webhooks/yoomoney")
async def yoomoney_webhook(
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-YooMoney-Signature"),
):
    """Handle YooMoney payment notifications."""
    body = await request.body()
    signature_header = x_signature or request.headers.get("X-Content-HMAC-SHA256")

    if YOOMONEY_WEBHOOK_SECRET:
        if not signature_header:
            logger.warning("Missing signature for YooMoney webhook")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="signature required")

        expected = compute_hmac_sha256(YOOMONEY_WEBHOOK_SECRET, body)
        if not hmac.compare_digest(expected, signature_header.strip().lower()):
            logger.warning("Invalid signature for YooMoney webhook")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        logger.error("Invalid JSON in YooMoney webhook: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json") from exc

    status_raw, normalized, metadata, _obj = _normalize_yoomoney_payload(payload)
    order_id = normalized.get("order_id") or "unknown"
    logger.info("YooMoney webhook status=%s order=%s", status_raw, order_id)

    try:
        user_row = await _find_user_for_yoomoney(metadata, normalized["email"], normalized["phone"])
    except Exception as exc:  # noqa: BLE001 — хотим логировать любые ошибки поиска
        logger.exception("Failed to locate user for YooMoney order %s: %s", order_id, exc)
        user_row = None

    await _upsert_payment(
        normalized,
        status_raw,
        at_user_id=(user_row or {}).get("at_user_id"),
        access_until=normalized.get("access_until"),
    )

    if not user_row:
        await notify_admins(
            (
                "⚠️ YooMoney: получено уведомление, но пользователь не найден.\n"
                f"Статус: {status_raw or '—'}\n"
                f"Email: {normalized['email'] or '—'}, телефон: {normalized['phone'] or '—'}\n"
                f"Order ID: {order_id}"
            )
        )
        return {"ok": True, "status": status_raw, "user_found": False}

    user_id = user_row["id"]
    tg_user_id = user_row.get("tg_user_id")
    access_until = normalized.get("access_until")
    amount_value = normalized.get("amount_value")
    currency = normalized.get("currency")
    amount_label = amount_value or ""
    if amount_value and currency:
        amount_label = f"{amount_value} {currency}"
    elif currency:
        amount_label = currency

    normalized_status = (status_raw or "").strip().lower()
    success_statuses = {"paid", "succeeded", "success"}
    failure_statuses = {"failed", "canceled", "cancelled", "refused", "rejected"}

    if normalized_status in success_statuses:
        try:
            await _set_member_active(user_id, access_until)
            await _mark_funnel_complete(user_id)
            invite = await gen_invite_link()
            access_label: Optional[str] = None
            if access_until:
                access_label = tz_aware_msk(access_until)
                confirmation = (
                    "🎉 Оплата получена! Доступ активен до "
                    f"{access_label}.\n\nТвой инвайт (активен 24ч): {invite}\n\n"
                    f"Начни отсюда: {WELCOME_POST_URL}"
                )
            else:
                confirmation = (
                    "🎉 Оплата получена! Доступ активирован.\n\n"
                    f"Твой инвайт (активен 24ч): {invite}\n\n"
                    f"Начни отсюда: {WELCOME_POST_URL}"
                )

            for attempt in range(MAX_RETRIES):
                try:
                    await bot.send_message(tg_user_id, confirmation)
                    break
                except Exception as exc:
                    if attempt == MAX_RETRIES - 1:
                        logger.error("Failed to deliver YooMoney confirmation to %s: %s", tg_user_id, exc)
                        await notify_admins(
                            f"⚠️ YooMoney: не удалось отправить подтверждение пользователю {tg_user_id}: {exc}"
                        )
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

            await notify_admins(
                (
                    "✅ YooMoney: успешная оплата.\n"
                    f"Order ID: {order_id}\n"
                    f"Сумма: {amount_label or '—'}\n"
                    f"Пользователь: {tg_user_id} (id={user_id})"
                )
            )
        except Exception as exc:  # noqa: BLE001 — логируем любые ошибки бизнес-логики
            logger.exception("Error processing YooMoney success for user %s: %s", user_id, exc)
            await notify_admins(
                f"❌ YooMoney: ошибка обработки успешной оплаты для пользователя {user_id}: {exc}"
            )

        return {
            "ok": True,
            "status": normalized_status,
            "user_found": True,
            "member_status": "member_active",
            "invite_link": invite,
            "access_until": access_label if access_until else None,
        }

    if normalized_status in failure_statuses:
        try:
            await _set_member_expired(user_id)
            warning = (
                "❌ Оплата не прошла или была отменена. Доступ к клубу приостановлен.\n"
                f"Поддержка: {SUPPORT_CONTACT}"
            )
            for attempt in range(MAX_RETRIES):
                try:
                    await bot.send_message(tg_user_id, warning)
                    break
                except Exception as exc:
                    if attempt == MAX_RETRIES - 1:
                        logger.error("Failed to deliver YooMoney failure notice to %s: %s", tg_user_id, exc)
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))

            await notify_admins(
                (
                    "⚠️ YooMoney: платеж отклонён или отменён.\n"
                    f"Order ID: {order_id}\n"
                    f"Статус: {normalized_status}\n"
                    f"Пользователь: {tg_user_id} (id={user_id})"
                )
            )
        except Exception as exc:
            logger.exception("Error processing YooMoney failure for user %s: %s", user_id, exc)
            await notify_admins(
                f"❌ YooMoney: ошибка обработки неуспешной оплаты для пользователя {user_id}: {exc}"
            )

        return {
            "ok": True,
            "status": normalized_status,
            "user_found": True,
            "member_status": "member_expired",
        }

    await notify_admins(
        (
            "ℹ️ YooMoney: получен вебхук с нестандартным статусом.\n"
            f"Order ID: {order_id}\n"
            f"Статус: {normalized_status or '—'}"
        )
    )
    return {"ok": True, "status": normalized_status, "user_found": True}


# ──────────────────────────────────────────────────────────────────────────────
# Локальный запуск
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None)
