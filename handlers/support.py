"""Support-related handlers and utilities."""

from __future__ import annotations

import html
import logging
from typing import Any, Optional, TYPE_CHECKING
from urllib.parse import urlparse

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards import CANCEL_TEXT, cancel_keyboard
from settings import ADMIN_IDS, STAFF_ADMIN_IDS

from .config import SUPPORT_CONTACT
from .content import get_content
from .states import SupportStates

if TYPE_CHECKING:  # pragma: no cover - imported for type hints only
    from . import (
        _get_notify_admins,
        answer_with_main_menu,
        get_user_with_id,
        is_admin_id,
        render_content,
    )

logger = logging.getLogger("handlers.support")

_SUPPORT_CHANNELS_CONFIG: tuple[dict[str, str], ...] = (
    {
        "key": "telegram",
        "setting": "settings.support.telegram_url",
        "title": "Telegram-чат",
        "emoji": "💬",
        "description": "Связь с командой.",
        "type": "telegram",
    },
    {
        "key": "youtube",
        "setting": "settings.support.youtube_url",
        "title": "YouTube",
        "emoji": "📺",
        "description": "Разборы и эфиры.",
        "type": "url",
    },
    {
        "key": "instagram",
        "setting": "settings.support.instagram_url",
        "title": "Instagram",
        "emoji": "📸",
        "description": "Новости и закулисье.",
        "type": "url",
    },
    {
        "key": "email",
        "setting": "settings.support.email",
        "title": "Email",
        "emoji": "✉️",
        "description": "Почта поддержки.",
        "type": "email",
    },
    {
        "key": "site",
        "setting": "settings.support.site_url",
        "title": "Сайт",
        "emoji": "🌐",
        "description": "Полезные ссылки и база знаний.",
        "type": "url",
    },
)

_SUPPORT_QUESTION_CALLBACK = "support:ask"

support_router = Router(name="support")


def _normalize_support_link(raw: str, kind: str) -> tuple[str, str]:
    value = (raw or "").strip()
    if not value:
        return "", ""

    if kind == "telegram":
        normalized = value
        if normalized.startswith("@"):
            username = normalized[1:]
            return f"https://t.me/{username}", f"@{username}"
        parsed = urlparse(normalized)
        if parsed.scheme:
            display = normalized
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc.lower() == "t.me"
                and parsed.path
            ):
                username = parsed.path.strip("/")
                if username:
                    display = f"@{username}"
            return normalized, display
        normalized = normalized.replace("t.me/", "").lstrip("@")
        if not normalized:
            return "", ""
        return f"https://t.me/{normalized}", f"@{normalized}"

    if kind == "email":
        if value.startswith("mailto:"):
            address = value.split("mailto:", 1)[1] or value
            return value, address
        return f"mailto:{value}", value

    parsed = urlparse(value)
    if not parsed.scheme:
        value = f"https://{value.lstrip('/')}"
    return value, value


async def _prepare_support_channels() -> tuple[list[dict[str, str]], dict[str, str]]:
    placeholders: dict[str, str] = {}
    channels: list[dict[str, str]] = []

    for config in _SUPPORT_CHANNELS_CONFIG:
        raw_value = (await get_content(config["setting"], default="")).strip()
        if not raw_value and config["key"] == "telegram":
            raw_value = SUPPORT_CONTACT

        url, display = _normalize_support_link(raw_value, config.get("type", "url"))
        if not url:
            continue

        label = f"{config['emoji']} {config['title']}"
        description = config.get("description", "")
        line = (
            f"{config['emoji']} <a href=\"{html.escape(url, quote=True)}\">"
            f"{html.escape(config['title'])}</a>"
        )
        if description:
            line += f" — {html.escape(description)}"

        channels.append(
            {
                "key": config["key"],
                "label": label,
                "url": url,
                "description": description,
                "display": display,
                "line": line,
            }
        )

        placeholders[f"support_{config['key']}_url"] = url
        placeholders[f"support_{config['key']}_label"] = label
        placeholders[f"support_{config['key']}_description"] = description
        placeholders[f"support_{config['key']}_display"] = display

        if config["key"] == "email":
            placeholders["support_email"] = display
            placeholders["support_email_url"] = url

        if config["key"] in {"youtube", "instagram"}:
            placeholders[f"{config['key']}_url"] = url

    if not channels:
        fallback_url, fallback_display = _normalize_support_link(SUPPORT_CONTACT, "telegram")
        if fallback_url:
            telegram_cfg = next(
                (cfg for cfg in _SUPPORT_CHANNELS_CONFIG if cfg["key"] == "telegram"),
                None,
            )
            title = telegram_cfg["title"] if telegram_cfg else "Поддержка"
            emoji = telegram_cfg["emoji"] if telegram_cfg else "💬"
            description = telegram_cfg.get("description", "") if telegram_cfg else "Связь с командой."
            label = f"{emoji} {title}"
            line = (
                f"{emoji} <a href=\"{html.escape(fallback_url, quote=True)}\">"
                f"{html.escape(title)}</a>"
            )
            if description:
                line += f" — {html.escape(description)}"

            channels.append(
                {
                    "key": "telegram",
                    "label": label,
                    "url": fallback_url,
                    "description": description,
                    "display": fallback_display,
                    "line": line,
                }
            )

            placeholders.setdefault("support_telegram_url", fallback_url)
            placeholders.setdefault("support_telegram_label", label)
            placeholders.setdefault("support_telegram_description", description)
            placeholders.setdefault("support_telegram_display", fallback_display)

    channels_text = "\n".join(channel["line"] for channel in channels)
    if not channels_text:
        channels_text = f"• {html.escape(SUPPORT_CONTACT)}"

    placeholders["support_channels_text"] = channels_text
    placeholders["support_channels"] = channels_text

    return channels, placeholders


async def send_support_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    from . import answer_with_main_menu, render_content

    channels, channel_placeholders = await _prepare_support_channels()

    support_template = await get_content(
        "menu.support",
        (
            "Поддержка.\n\n"
            "Если есть вопросы или сложности — пиши сюда: {support}. Мы отвечаем лично и максимально быстро."
        ),
    )

    placeholders = {
        "support": SUPPORT_CONTACT,
        "support_contact": SUPPORT_CONTACT,
    }
    placeholders.update(channel_placeholders)

    support_text = render_content(support_template, **placeholders)

    inline_rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=channel["label"], url=channel["url"])]
        for channel in channels
        if channel.get("url")
    ]
    if ADMIN_IDS or STAFF_ADMIN_IDS:
        inline_rows.append(
            [
                InlineKeyboardButton(
                    text="✉️ Задать вопрос команде",
                    callback_data=_SUPPORT_QUESTION_CALLBACK,
                )
            ]
        )

    inline_keyboard = InlineKeyboardMarkup(inline_keyboard=inline_rows) if inline_rows else None

    answer_kwargs: dict[str, Any] = {"disable_web_page_preview": True}
    use_main_menu_keyboard = inline_keyboard is None
    if inline_keyboard:
        answer_kwargs["reply_markup"] = inline_keyboard

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        support_text,
        section="root",
        from_callback=from_callback,
        use_main_menu_keyboard=use_main_menu_keyboard,
        **answer_kwargs,
    )


@support_router.callback_query(F.data == _SUPPORT_QUESTION_CALLBACK)
async def support_prompt_question(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SupportStates.waiting_question)
    await state.update_data(support_context="menu.support")

    prompt_text = (
        "Напиши вопрос одним сообщением — команда поддержки увидит его сразу.\n\n"
        f"Если передумала — нажми «{CANCEL_TEXT}»."
    )

    if callback.message:
        await callback.message.answer(prompt_text, reply_markup=cancel_keyboard())
    await callback.answer()


@support_router.message(SupportStates.waiting_question)
async def support_receive_question(message: types.Message, state: FSMContext) -> None:
    from . import _get_notify_admins, get_user_with_id, is_admin_id

    if message.text and message.text.strip().lower() == CANCEL_TEXT.lower():
        from . import cancel_handler

        await cancel_handler(message, state)
        return

    data = await state.get_data() or {}
    context_label = str(data.get("support_context") or "menu.support").strip()

    question_text = (message.text or message.caption or "").strip()
    user_row = await get_user_with_id(message.from_user.id)
    is_admin = is_admin_id(message.from_user.id)

    summary_lines = [
        "🆘 Новый вопрос в поддержку",
        f"tg-id: <code>{message.from_user.id}</code>",
    ]
    if user_row and user_row.get("id"):
        summary_lines.append(f"user-id: <code>{user_row['id']}</code>")
    if user_row and user_row.get("full_name"):
        summary_lines.append(f"Имя: {html.escape(user_row['full_name'])}")
    if message.from_user.username:
        summary_lines.append(f"Username: @{message.from_user.username}")
    if context_label:
        summary_lines.append(f"Контекст: {html.escape(context_label)}")
    if question_text:
        summary_lines.append(f"Вопрос: {html.escape(question_text)}")
    else:
        summary_lines.append(f"Вопрос: [сообщение типа {message.content_type}]")

    notify_admins = _get_notify_admins()
    if notify_admins:
        try:
            await notify_admins("\n".join(summary_lines))
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "support_question: notify_admins failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )

    staff_recipients = list(ADMIN_IDS)
    staff_recipients.extend(staff_id for staff_id in STAFF_ADMIN_IDS if staff_id not in ADMIN_IDS)

    for admin_id in staff_recipients:
        try:
            await message.forward(admin_id)
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "support_question: forward failed tg_user_id=%s admin_id=%s err=%s",
                message.from_user.id,
                admin_id,
                exc,
            )

    await state.clear()

    confirm_text = (
        "Передала вопрос команде поддержки. "
        f"Ответ придёт в поддержку: {SUPPORT_CONTACT}."
    )

    from . import answer_with_main_menu

    await answer_with_main_menu(
        message,
        user_row,
        is_admin,
        confirm_text,
        section="root",
    )


__all__ = [
    "support_router",
    "send_support_section",
    "support_prompt_question",
    "support_receive_question",
]
