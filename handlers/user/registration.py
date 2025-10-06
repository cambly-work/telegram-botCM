"""User registration handlers and helpers."""
from __future__ import annotations

import asyncio
import html
import re
from typing import Optional
from urllib.parse import parse_qs

from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.chat_action import ChatActionSender

from db import execute, fetchrow
from keyboards import cancel_keyboard

from ..core import (
    _get_notify_admins,
    _is_admin_setting_enabled,
    build_menu_keyboard,
    get_content,
    get_user_with_id,
    is_admin_id,
    logger,
    render_content,
)
from .states import RegistrationStates

router = Router(name="user-registration")


async def ensure_user(tg_user: types.User, utm: dict | None = None) -> dict:
    """Create a user if missing and update profile details."""
    row = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user.id)
    if row:
        utm_updates = {}
        if utm:
            if utm.get("utm_source"):
                utm_updates["utm_source"] = utm["utm_source"]
            if utm.get("utm_medium"):
                utm_updates["utm_medium"] = utm["utm_medium"]
            if utm.get("utm_campaign"):
                utm_updates["utm_campaign"] = utm["utm_campaign"]

        update_fields = [
            "username=$2",
            "full_name=$3",
            "last_activity_at=NOW()",
            "updated_at=NOW()",
        ]
        params = [tg_user.id, tg_user.username, tg_user.full_name]
        param_count = 3

        for field, value in utm_updates.items():
            param_count += 1
            update_fields.append(f"{field}=${param_count}")
            params.append(value)

        await execute(
            f"UPDATE users SET {', '.join(update_fields)} WHERE tg_user_id=$1",
            *params,
        )
        return await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user.id)

    utm_source = (utm or {}).get("utm_source")
    utm_medium = (utm or {}).get("utm_medium")
    utm_campaign = (utm or {}).get("utm_campaign")

    await execute(
        """INSERT INTO users (tg_user_id, username, full_name, utm_source, utm_medium, utm_campaign, created_at, updated_at, last_activity_at)
           VALUES ($1,$2,$3,$4,$5,$6, NOW(), NOW(), NOW())""",
        tg_user.id,
        tg_user.username,
        tg_user.full_name,
        utm_source,
        utm_medium,
        utm_campaign,
    )

    created = await fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user.id)
    logger.info("ensure_user: created user tg_id=%s id=%s", tg_user.id, created["id"])
    return created


def parse_start_utm(text: Optional[str]) -> dict:
    if not text or " " not in text:
        return {}
    try:
        _, payload = text.split(" ", 1)
        if payload.startswith("/start "):
            payload = payload[7:]
        qs = parse_qs(payload, keep_blank_values=True)
        return {k: (v[0] if isinstance(v, list) else v) for k, v in qs.items()}
    except Exception:
        return {}


@router.message(CommandStart())
async def on_start(message: types.Message, state: FSMContext):
    user = await get_user_with_id(message.from_user.id)

    if not user:
        utm_params = parse_start_utm(message.text)
        await ensure_user(message.from_user, utm=utm_params)
        user = await get_user_with_id(message.from_user.id)

    if not user.get("name") or not user.get("email") or not user.get("phone"):
        await state.set_state(RegistrationStates.waiting_name)
        await message.answer(
            "Добро пожаловать! Для начала нам нужно познакомиться. Как тебя зовут?",
            reply_markup=cancel_keyboard(),
        )
        return

    is_admin = is_admin_id(message.from_user.id)
    kb = await build_menu_keyboard(user=user, is_admin=is_admin, section="root")

    welcome_template = await get_content(
        "menu.start",
        "Добро пожаловать в CODE: Магнетизм. Это пространство для развития и перемен. Выбери раздел в меню, чтобы начать, {name}!",
    )
    display_name = (
        user.get("name")
        or user.get("full_name")
        or message.from_user.full_name
        or message.from_user.first_name
        or "друг"
    )
    welcome_text = render_content(
        welcome_template,
        name=display_name,
        NAME=display_name,
    )

    async with ChatActionSender.typing(chat_id=message.chat.id, bot=message.bot):
        await asyncio.sleep(0.15)
        await message.answer(welcome_text, reply_markup=kb)


@router.message(RegistrationStates.waiting_name, F.text.len() > 0)
async def registration_receive_name(message: types.Message, state: FSMContext):
    name = message.text.strip()

    await execute(
        "UPDATE users SET name=$2, updated_at=NOW() WHERE tg_user_id=$1",
        message.from_user.id,
        name,
    )

    await state.set_state(RegistrationStates.waiting_email)
    await message.answer(
        "Укажи email для связи:",
        reply_markup=cancel_keyboard(),
    )


@router.message(RegistrationStates.waiting_email, F.text.len() > 0)
async def registration_receive_email(message: types.Message, state: FSMContext):
    email = (message.text or "").strip()

    if not validate_email(email):
        await message.answer(
            "Формат неверный. Пример: name@mail.com",
            reply_markup=cancel_keyboard(),
        )
        return

    await execute(
        "UPDATE users SET email=$2, updated_at=NOW() WHERE tg_user_id=$1",
        message.from_user.id,
        email,
    )

    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer(
        "Укажи номер телефона:",
        reply_markup=cancel_keyboard(),
    )


@router.message(RegistrationStates.waiting_phone, F.text.len() > 0)
async def registration_receive_phone(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.text or "")

    if not validate_phone(phone):
        await message.answer(
            "Формат неверный. Пример: +79991234567",
            reply_markup=cancel_keyboard(),
        )
        return

    await execute(
        "UPDATE users SET phone=$2, updated_at=NOW() WHERE tg_user_id=$1",
        message.from_user.id,
        phone,
    )

    await state.clear()

    user = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)
    kb = await build_menu_keyboard(user=user, is_admin=is_admin, section="root")

    completion_template = await get_content(
        "menu.registration_complete",
        "Регистрация завершена, {name}!\n\nТеперь тебе доступно:\n- Бесплатные уроки\n- Доступ в клуб\n- Отслеживание прогресса\n\nВыбирай в меню и начинай.",
    )
    display_name = (
        user.get("name")
        or user.get("full_name")
        or message.from_user.full_name
        or message.from_user.first_name
        or "друг"
    )
    completion_text = render_content(
        completion_template,
        name=display_name,
        NAME=display_name,
    )

    await message.answer(completion_text, reply_markup=kb)

    notify_admins = _get_notify_admins()
    if notify_admins and await _is_admin_setting_enabled("notify_registration"):
        card_lines = [
            "🆕 Новая регистрация",
            f"tg-id: <code>{message.from_user.id}</code>",
        ]
        if user and user.get("id"):
            card_lines.append(f"user-id: <code>{user['id']}</code>")
        full_name = user.get("full_name") if user else None
        if full_name:
            card_lines.append(f"Имя: {html.escape(full_name)}")
        if message.from_user.username:
            card_lines.append(f"Username: @{message.from_user.username}")
        email = (user or {}).get("email")
        if email:
            card_lines.append(f"Email: {html.escape(email)}")
        if phone:
            card_lines.append(f"Телефон: {html.escape(phone)}")
        try:
            await notify_admins("\n".join(card_lines))
        except Exception as exc:  # pragma: no cover - notification failures are non-critical
            logger.warning(
                "registration: notify_admins failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )


def normalize_phone(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = _PHONE_DIGITS_RE.sub("", cleaned)

    if cleaned.startswith("8") and len(cleaned) == 11:
        cleaned = "+7" + cleaned[1:]
    elif cleaned.startswith("7") and len(cleaned) == 11:
        cleaned = "+" + cleaned
    elif len(cleaned) == 10 and cleaned.isdigit():
        cleaned = "+7" + cleaned

    if cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned

    return cleaned


def validate_phone(phone: str) -> bool:
    normalized = normalize_phone(phone)
    if not normalized.startswith("+"):
        return False
    digits = normalized[1:]
    if not digits.isdigit():
        return False
    return len(digits) >= 7


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


_PHONE_DIGITS_RE = re.compile(r"[^\d+]")
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

__all__ = [
    "router",
    "ensure_user",
    "parse_start_utm",
    "normalize_phone",
    "validate_phone",
    "validate_email",
]
