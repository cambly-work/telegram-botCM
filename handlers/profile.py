"""Profile-related handlers and helpers."""

from __future__ import annotations

import html
import logging
from datetime import timedelta, timezone
from typing import Any, Optional, Sequence

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from db import execute, fetch
from keyboards import CANCEL_TEXT, cancel_keyboard
from utils import normalize_phone

from .constants import (
    TELEGRAM_MESSAGE_LIMIT,
    USER_KEY_STATUS_AVAILABLE,
    USER_KEY_STATUS_CLAIMED,
    USER_KEY_STATUS_REVOKED,
    WEEKLY_KEY_STATUS_ACTIVE,
)
from .progress import _coerce_datetime
from .states import ProfileStates

logger = logging.getLogger("handlers.profile")

profile_router = Router(name="profile")

_PROFILE_STATUS_TITLES: dict[str, str] = {
    "lead_funnel": "Без подписки",
    "member_active": "Активный доступ",
    "member_expired": "Доступ истёк",
}

_MEMBERSHIP_STATUS_LABELS: dict[str, str] = {
    "lead_funnel": "Без подписки",
    "member_active": "Активный доступ",
    "member_expired": "Доступ истёк",
}

_MSK_TZ = timezone(timedelta(hours=3))


def _format_access_date(value: Any) -> str:
    dt = _coerce_datetime(value)
    if not dt:
        return ""
    try:
        return dt.astimezone(_MSK_TZ).strftime("%d.%m.%Y")
    except Exception:  # pragma: no cover - fallback for unexpected tz issues
        return ""


def _membership_summary(user_row: dict | None) -> dict[str, str]:
    user_row = user_row or {}
    status_code = str(user_row.get("status") or "lead_funnel").lower()
    status_label = (
        _MEMBERSHIP_STATUS_LABELS.get(status_code)
        or _PROFILE_STATUS_TITLES.get(status_code)
        or status_code.replace("_", " ").title()
    )
    access_date = _format_access_date(user_row.get("access_until"))

    if status_code == "member_active":
        if access_date:
            access_line = f"Доступ активен до {access_date}"
            access_short = f"до {access_date}"
        else:
            access_line = "Доступ активен"
            access_short = "активен"
    elif status_code == "member_expired":
        if access_date:
            access_line = f"Доступ истёк {access_date}"
            access_short = f"истёк {access_date}"
        else:
            access_line = "Доступ истёк"
            access_short = "истёк"
    else:
        if access_date:
            access_line = f"Доступ не активирован (ожидаем до {access_date})"
            access_short = f"ожидает до {access_date}"
        else:
            access_line = "Доступ не активирован"
            access_short = "не активирован"

    return {
        "status_code": status_code,
        "status_label": status_label,
        "access_date": access_date,
        "access_line": access_line,
        "status_line": f"Статус участия: {status_label}",
        "summary": f"{status_label} · {access_short}" if access_short else status_label,
        "access_short": access_short,
    }


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

    while added_lines:
        added_lines.pop()
        omitted += 1
        base_section = f"{leading_break}{header}"
        if added_lines:
            base_section += "\n" + "\n".join(added_lines)
        if prefix_length + len(base_section + "\n" + notice) <= max_length:
            return base_section + "\n" + notice, omitted

    base_section = f"{leading_break}{header}"
    if prefix_length + len(base_section + "\n" + notice) <= max_length:
        return base_section + "\n" + notice, omitted

    return base_section, omitted


def _weekly_key_icon(status: str | None) -> str:
    if status in (USER_KEY_STATUS_AVAILABLE, USER_KEY_STATUS_CLAIMED):
        return "✅"
    return "🔒"


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


async def send_profile_overview(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    from . import answer_with_main_menu, build_menu_keyboard, get_user_with_id

    user_row = user or await get_user_with_id(message.from_user.id)
    if not user_row:
        await answer_with_main_menu(
            message,
            user_row,
            is_admin,
            "Профиль не найден. Перезапусти /start, чтобы обновить данные.",
            section="profile",
            from_callback=from_callback,
        )
        return

    status_key = user_row.get("status") or "lead_funnel"
    ru_status_label = _PROFILE_STATUS_TITLES.get(status_key, "—")
    membership = _membership_summary(user_row)
    status_caption = membership["status_label"]
    if ru_status_label and ru_status_label not in {status_caption, "—"}:
        status_caption = f"{status_caption} ({ru_status_label})"
    access_line = membership["access_line"]

    email_value = user_row.get("email") or "—"
    phone_value = user_row.get("phone") or "—"
    name_value = user_row.get("name") or (user_row.get("full_name") or "—")

    try:
        weekly_keys = await list_weekly_keys_for_user(user_row.get("id"))
    except AssertionError:
        weekly_keys = []
    except Exception as exc:  # noqa: BLE001
        logger.warning("profile weekly keys fetch failed: %s", exc)
        weekly_keys = []
    keys_lines: list[str] = []
    for key in weekly_keys:
        base_title = key.get("title") or key.get("key_description")
        if base_title:
            label = f"Неделя {key['week']}: {base_title}"
        else:
            label = f"Неделя {key['week']}"
        status = key.get("user_status")
        if status == USER_KEY_STATUS_AVAILABLE:
            suffix = " — бонус доступен"
        elif status == USER_KEY_STATUS_CLAIMED:
            suffix = " — бонус получен"
        elif status == USER_KEY_STATUS_REVOKED:
            suffix = " — доступ отозван"
        else:
            suffix = " — ещё закрыт"
        keys_lines.append(f"{_weekly_key_icon(status)} {html.escape(label)}{suffix}")

    profile_text = (
        "<b>Твой профиль</b>\n\n"
        f"Имя: {html.escape(name_value)}\n"
        f"Email: {html.escape(email_value)}\n"
        f"Телефон: {html.escape(phone_value)}\n\n"
        f"Статус: {status_caption}\n"
        f"{access_line}\n\n"
        "Используй кнопки ниже, чтобы обновить контакты."
    )

    if keys_lines:
        keys_block, _ = _format_weekly_keys_section(
            keys_lines,
            header="🔑 <b>Ключи недели</b>",
            prefix_length=len(profile_text),
        )
        profile_text += keys_block

    keyboard = await build_menu_keyboard(
        user=user_row,
        is_admin=is_admin,
        section="profile",
    )

    await message.answer(profile_text, reply_markup=keyboard)


@profile_router.message(ProfileStates.waiting_email, F.text.casefold() == CANCEL_TEXT.lower())
async def profile_cancel_email(message: types.Message, state: FSMContext):
    from . import get_user_with_id, is_admin_id

    await state.clear()

    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)

    await message.answer("Изменение email отменено.")
    await send_profile_overview(message, user, is_admin)


@profile_router.message(ProfileStates.waiting_email, F.text.len() > 0)
async def profile_receive_email(message: types.Message, state: FSMContext):
    from . import get_user_with_id, is_admin_id, validate_email

    email = (message.text or "").strip()

    if not validate_email(email):
        await message.answer(
            "Формат email неверный. Пример: name@mail.com",
            reply_markup=cancel_keyboard(),
        )
        return

    await execute(
        "UPDATE users SET email=$2, updated_at=NOW() WHERE tg_user_id=$1",
        message.from_user.id,
        email,
    )
    await state.clear()

    await message.answer("Email обновлён ✅")
    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    await send_profile_overview(message, user, is_admin)


@profile_router.message(ProfileStates.waiting_phone, F.text.casefold() == CANCEL_TEXT.lower())
async def profile_cancel_phone(message: types.Message, state: FSMContext):
    from . import get_user_with_id, is_admin_id

    await state.clear()

    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)

    await message.answer("Изменение телефона отменено.")
    await send_profile_overview(message, user, is_admin)


@profile_router.message(ProfileStates.waiting_phone, F.text.len() > 0)
async def profile_receive_phone(message: types.Message, state: FSMContext):
    from . import get_user_with_id, is_admin_id, validate_phone

    raw_phone = (message.text or "").strip()

    if not validate_phone(raw_phone):
        await message.answer(
            "Номер не распознан. Укажи телефон в формате +79991234567.",
            reply_markup=cancel_keyboard(),
        )
        return

    normalized = normalize_phone(raw_phone)
    await execute(
        "UPDATE users SET phone=$2, updated_at=NOW() WHERE tg_user_id=$1",
        message.from_user.id,
        normalized,
    )
    await state.clear()

    await message.answer("Телефон обновлён ✅")
    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    await send_profile_overview(message, user, is_admin)


__all__ = [
    "profile_router",
    "send_profile_overview",
    "profile_cancel_email",
    "profile_receive_email",
    "profile_cancel_phone",
    "profile_receive_phone",
    "list_weekly_keys_for_user",
    "_format_weekly_keys_section",
    "_membership_summary",
    "_PROFILE_STATUS_TITLES",
]
