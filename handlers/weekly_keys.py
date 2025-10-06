from __future__ import annotations

import html
import logging
from typing import Sequence

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db import fetch, fetchrow, transaction
from .constants import (
    SYSTEM_ADMIN_ACTOR,
    TELEGRAM_MESSAGE_LIMIT,
    USER_KEY_STATUS_AVAILABLE,
    USER_KEY_STATUS_CLAIMED,
    USER_KEY_STATUS_REVOKED,
    WEEKLY_KEY_STATUS_ACTIVE,
)

logger = logging.getLogger("handlers.weekly_keys")

weekly_keys_router = Router(name="weekly-keys")


def _format_weekly_keys_section(
    lines: Sequence[str],
    *,
    header: str,
    prefix_length: int = 0,
    leading_break: str = "\n\n",
    max_length: int = TELEGRAM_MESSAGE_LIMIT,
    truncation_template: str = "...и ещё {count} недель",
) -> tuple[str, int]:
    if not lines:
        return "", 0

    section_text = f"{leading_break}{header}"
    if prefix_length + len(section_text) > max_length:
        return "", len(lines)

    added_lines: list[str] = []
    index = 0
    while index < len(lines):
        candidate_lines = added_lines + [lines[index]]
        candidate_text = section_text + "\n" + "\n".join(candidate_lines)
        if prefix_length + len(candidate_text) <= max_length:
            added_lines.append(lines[index])
            section_text = candidate_text
            index += 1
            continue
        break

    omitted = len(lines) - index
    if omitted <= 0:
        return section_text, 0

    notice = truncation_template.format(count=omitted)
    if prefix_length + len(section_text + "\n" + notice) <= max_length:
        return section_text + "\n" + notice, omitted

    return section_text, omitted


async def list_weekly_keys_for_user(user_id: int | None) -> list[dict]:
    if user_id is None:
        rows = await fetch(
            """
            SELECT id, week, status AS key_status, title, key_description, bonus_description, bonus_link
            FROM weekly_keys
            WHERE status = $1
            ORDER BY week
            """,
            WEEKLY_KEY_STATUS_ACTIVE,
        )
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item.setdefault("user_status", None)
            result.append(item)
        return result

    rows = await fetch(
        """
        SELECT
            wk.id,
            wk.week,
            wk.status     AS key_status,
            wk.title,
            wk.key_description,
            wk.bonus_description,
            wk.bonus_link,
            uk.status     AS user_status,
            uk.claimed_at,
            uk.granted_at
        FROM weekly_keys wk
        LEFT JOIN user_keys uk
          ON uk.weekly_key_id = wk.id AND uk.user_id = $1
        WHERE wk.status = $2
        ORDER BY wk.week
        """,
        user_id,
        WEEKLY_KEY_STATUS_ACTIVE,
    )
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        item.setdefault("user_status", None)
        result.append(item)
    return result


async def upsert_weekly_key(entry: dict) -> dict:
    week = int(entry.get("week"))
    status = str(entry.get("status", WEEKLY_KEY_STATUS_ACTIVE)).strip().lower()
    if status not in {WEEKLY_KEY_STATUS_ACTIVE, "inactive"}:
        status = "inactive"

    row = await fetchrow(
        """
        INSERT INTO weekly_keys (week, status, title, key_description, bonus_description, bonus_link, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ON CONFLICT (week)
        DO UPDATE SET
            status = EXCLUDED.status,
            title = EXCLUDED.title,
            key_description = EXCLUDED.key_description,
            bonus_description = EXCLUDED.bonus_description,
            bonus_link = EXCLUDED.bonus_link,
            updated_at = NOW()
        RETURNING *
        """,
        week,
        status,
        entry.get("title"),
        entry.get("key_description"),
        entry.get("bonus_description"),
        entry.get("bonus_link"),
    )
    return dict(row)


async def grant_weekly_key(
    user_id: int,
    week: int,
    *,
    granted_by: int | None = None,
) -> dict:
    async with transaction() as conn:
        weekly_row = await conn.fetchrow(
            "SELECT * FROM weekly_keys WHERE week = $1",
            week,
        )
        if not weekly_row:
            return {"success": False, "error": "not_configured"}

        weekly = dict(weekly_row)
        if weekly.get("status") != WEEKLY_KEY_STATUS_ACTIVE:
            return {"success": False, "error": "inactive", "weekly": weekly}

        existing_row = await conn.fetchrow(
            "SELECT * FROM user_keys WHERE user_id = $1 AND weekly_key_id = $2",
            user_id,
            weekly_row["id"],
        )
        if existing_row and existing_row["status"] == USER_KEY_STATUS_CLAIMED:
            return {
                "success": False,
                "error": "already_claimed",
                "weekly": weekly,
                "user_key": dict(existing_row),
            }

        result_row = await conn.fetchrow(
            """
            INSERT INTO user_keys (user_id, weekly_key_id, week, status, bonus_link, granted_by, granted_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (user_id, weekly_key_id)
            DO UPDATE SET
                status = EXCLUDED.status,
                bonus_link = COALESCE(EXCLUDED.bonus_link, user_keys.bonus_link),
                granted_by = EXCLUDED.granted_by,
                granted_at = NOW(),
                revoked_at = NULL,
                revoked_by = NULL
            RETURNING *
            """,
            user_id,
            weekly_row["id"],
            week,
            USER_KEY_STATUS_AVAILABLE,
            weekly.get("bonus_link"),
            granted_by,
        )

        previous_status = existing_row["status"] if existing_row else None
        updated = previous_status != USER_KEY_STATUS_AVAILABLE

        return {
            "success": True,
            "updated": updated,
            "weekly": weekly,
            "user_key": dict(result_row),
        }


async def revoke_weekly_key(
    user_id: int,
    week: int,
    *,
    revoked_by: int | None = None,
) -> dict:
    async with transaction() as conn:
        weekly_row = await conn.fetchrow(
            "SELECT * FROM weekly_keys WHERE week = $1",
            week,
        )
        if not weekly_row:
            return {"success": False, "error": "not_configured"}

        weekly = dict(weekly_row)
        existing_row = await conn.fetchrow(
            "SELECT * FROM user_keys WHERE user_id = $1 AND weekly_key_id = $2",
            user_id,
            weekly_row["id"],
        )
        if not existing_row:
            return {"success": False, "error": "not_granted", "weekly": weekly}

        if existing_row["status"] == USER_KEY_STATUS_REVOKED:
            return {
                "success": False,
                "error": "already_revoked",
                "weekly": weekly,
                "user_key": dict(existing_row),
            }

        result_row = await conn.fetchrow(
            """
            UPDATE user_keys
               SET status = $3,
                   revoked_at = NOW(),
                   revoked_by = $4
             WHERE user_id = $1 AND weekly_key_id = $2
             RETURNING *
            """,
            user_id,
            weekly_row["id"],
            USER_KEY_STATUS_REVOKED,
            revoked_by,
        )

        return {
            "success": True,
            "updated": True,
            "weekly": weekly,
            "user_key": dict(result_row),
        }


async def claim_weekly_bonus(user_id: int, week: int) -> dict:
    async with transaction() as conn:
        weekly_row = await conn.fetchrow(
            "SELECT * FROM weekly_keys WHERE week = $1",
            week,
        )
        if not weekly_row:
            return {"success": False, "error": "not_configured"}

        weekly = dict(weekly_row)
        if weekly.get("status") != WEEKLY_KEY_STATUS_ACTIVE:
            return {"success": False, "error": "inactive", "weekly": weekly}

        user_key_row = await conn.fetchrow(
            "SELECT * FROM user_keys WHERE user_id = $1 AND weekly_key_id = $2",
            user_id,
            weekly_row["id"],
        )
        if not user_key_row:
            return {"success": False, "error": "not_granted", "weekly": weekly}

        if user_key_row["status"] == USER_KEY_STATUS_REVOKED:
            return {"success": False, "error": "revoked", "weekly": weekly}

        if user_key_row["status"] == USER_KEY_STATUS_CLAIMED:
            return {"success": False, "error": "already_claimed", "weekly": weekly}

        if user_key_row["status"] != USER_KEY_STATUS_AVAILABLE:
            return {"success": False, "error": "not_ready", "weekly": weekly}

        bonus_link = user_key_row.get("bonus_link") or weekly.get("bonus_link")

        result_row = await conn.fetchrow(
            """
            UPDATE user_keys
               SET status = $2,
                   claimed_at = NOW(),
                   bonus_link = COALESCE($3, user_keys.bonus_link)
             WHERE id = $1
             RETURNING *
            """,
            user_key_row["id"],
            USER_KEY_STATUS_CLAIMED,
            bonus_link,
        )

        return {
            "success": True,
            "weekly": weekly,
            "user_key": dict(result_row),
            "bonus_link": bonus_link,
        }


def _weekly_key_icon(status: str | None) -> str:
    if status in (USER_KEY_STATUS_AVAILABLE, USER_KEY_STATUS_CLAIMED):
        return "✅"
    return "🔒"


async def send_weekly_keys_overview_message(
    message: types.Message,
    user_row: dict,
    *,
    from_callback: bool = False,
    allow_edit: bool = False,
) -> bool:
    try:
        keys = await list_weekly_keys_for_user(user_row.get("id"))
    except AssertionError:
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("weekly keys overview failed: %s", exc)
        return False
    if not keys:
        return False

    lines: list[str] = []
    buttons: list[list[InlineKeyboardButton]] = []

    for key in keys:
        status = key.get("user_status")
        icon = _weekly_key_icon(status)
        title = key.get("title") or key.get("key_description") or f"Неделя {key['week']}"
        parts: list[str] = [f"{icon} {title}"]

        if status == USER_KEY_STATUS_AVAILABLE:
            parts.append("— бонус доступен")
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🎁 Бонус недели {key['week']}",
                        callback_data=f"weekly_bonus:{key['week']}",
                    )
                ]
            )
        elif status == USER_KEY_STATUS_CLAIMED:
            parts.append("— бонус получен")
        elif status == USER_KEY_STATUS_REVOKED:
            parts.append("— доступ отозван")
        else:
            parts.append("— ещё закрыт")

        lines.append(" ".join(parts))

    text, _ = _format_weekly_keys_section(
        lines,
        header="🔑 Ключи недели:",
        leading_break="",
    )
    if not text:
        text = "🔑 Ключи недели:"
    markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    if from_callback and allow_edit and getattr(message, "chat", None):
        try:
            await message.edit_text(
                text,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            return True
        except TelegramBadRequest:
            pass

    await message.answer(
        text,
        reply_markup=markup,
        disable_web_page_preview=True,
    )
    return True


@weekly_keys_router.callback_query(F.data.startswith("weekly_bonus:"))
async def weekly_bonus_callback(call: types.CallbackQuery, state: FSMContext):
    if not call.from_user:
        return

    try:
        _, raw_week = call.data.split(":", 1)
        week = int(raw_week)
    except (ValueError, AttributeError, TypeError):
        await call.answer("Некорректный ключ.", show_alert=True)
        return

    from . import get_user_with_id, log_admin_action

    user = await get_user_with_id(call.from_user.id)
    if not user:
        await call.answer("Перезапусти /start.", show_alert=True)
        return

    result = await claim_weekly_bonus(user["id"], week)
    if not result.get("success"):
        error = result.get("error")
        messages = {
            "not_configured": "Ключ ещё не настроен. Попробуй позже.",
            "inactive": "Эта неделя пока закрыта.",
            "not_granted": "Ключ ещё не активирован.",
            "revoked": "Ключ был отозван администратором.",
            "already_claimed": "Бонус уже выдан.",
        }
        await call.answer(messages.get(error, "Не получилось выдать бонус. Попробуй позже."), show_alert=True)
        if call.message:
            await send_weekly_keys_overview_message(
                call.message,
                user,
                from_callback=True,
                allow_edit=True,
            )
        return

    weekly = result.get("weekly", {})
    bonus_link = result.get("bonus_link")
    bonus_description = weekly.get("bonus_description")

    lines = [f"🎁 <b>Бонус недели {week}</b>"]
    if bonus_description:
        lines.append(html.escape(bonus_description))
    if bonus_link:
        lines.append("")
        lines.append(bonus_link)

    await log_admin_action(
        SYSTEM_ADMIN_ACTOR,
        "weekly_bonus_claim",
        {
            "week": week,
            "user_id": user["id"],
            "bonus_link": bonus_link,
        },
    )

    await call.answer("Бонус отправлен!", show_alert=False)

    target_message = call.message
    if target_message:
        await send_weekly_keys_overview_message(
            target_message,
            user,
            from_callback=True,
            allow_edit=True,
        )
        await target_message.answer(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    else:
        await call.bot.send_message(
            call.from_user.id,
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

