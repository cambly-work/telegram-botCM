from __future__ import annotations

import html
import logging
import re
from datetime import date
from typing import Optional, TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from db import execute, fetchrow
from .config import TEST_FORM_URL
from .constants import FORM_ALIASES, FORM_SLUG_ANALYSIS, FORM_SLUG_TEST
from .states import AnalysisStates, TestStates

if TYPE_CHECKING:  # pragma: no cover
    from . import get_content as _get_content_type
    from . import get_content_with_source as _get_content_with_source_type
from keyboards import (
    ANALYSIS_BACK_BUTTON,
    ANALYSIS_CONFIRM_BUTTON,
    CANCEL_TEXT,
    analysis_confirm_keyboard,
    cancel_keyboard,
)

logger = logging.getLogger(__name__)

forms_router = Router(name="forms")

_URL_RE = re.compile(r"https?://[^\s<>\)\]]+", re.IGNORECASE)
_FORM_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9_-]+", re.IGNORECASE)


def _get_content(key: str, default: str = ""):
    from . import get_content as _get_content_impl

    return _get_content_impl(key, default)


def _get_content_with_source(key: str, default: str = ""):
    from . import get_content_with_source as _get_content_with_source_impl

    return _get_content_with_source_impl(key, default)


def _lookup_form_alias(value: str) -> Optional[str]:
    if not value:
        return None

    cleaned = value.strip().lower()
    if not cleaned:
        return None

    alias = FORM_ALIASES.get(cleaned)
    if alias:
        return alias

    for candidate in (cleaned.replace("_", "-"), cleaned.replace(" ", "-")):
        alias = FORM_ALIASES.get(candidate)
        if alias:
            return alias

    return None


def _sanitize_form_slug(candidate: str) -> str:
    cleaned = (candidate or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("=", " ").replace("/", " ").replace("\u202f", " ")
    cleaned = cleaned.lower().replace(" ", "-")
    cleaned = _FORM_SLUG_SANITIZE_RE.sub("-", cleaned)
    return cleaned.strip("-")[:64]


def extract_first_url(text: str) -> Optional[str]:
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    url = match.group(0).rstrip(")\n.;]")
    return url


def resolve_form_slug(raw_value: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    candidates: list[str] = []
    raw = (raw_value or "").strip()
    if raw:
        if raw.startswith(("http://", "https://")):
            try:
                parsed = urlparse(raw)
                query = parse_qs(parsed.query or "")
                for key in ("form_slug", "slug", "form", "f"):
                    values = query.get(key)
                    if values:
                        candidates.extend(values)
                if parsed.fragment:
                    candidates.append(parsed.fragment)
            except Exception:
                candidates.append(raw)
        else:
            if "=" in raw:
                _, _, value = raw.partition("=")
                if value:
                    candidates.append(value)
            candidates.append(raw)
    if fallback:
        candidates.append(fallback)

    for candidate in candidates:
        alias = _lookup_form_alias(candidate)
        if alias:
            return alias

        slug = _sanitize_form_slug(candidate)
        if slug:
            alias = _lookup_form_alias(slug)
            if alias:
                return alias
            return slug
    return None


async def mark_form_started(user_id: int, form_slug: str) -> None:
    slug = resolve_form_slug(form_slug)
    if not slug:
        return

    await execute(
        """
        INSERT INTO form_sessions (user_id, form_slug, started_at, completed_at, last_reminder_at, reminder_count)
        VALUES ($1, $2, NOW(), NULL, NULL, 0)
        ON CONFLICT (user_id, form_slug) DO UPDATE
        SET started_at = CASE
                WHEN form_sessions.completed_at IS NOT NULL THEN EXCLUDED.started_at
                ELSE form_sessions.started_at
            END,
            completed_at = NULL,
            last_reminder_at = CASE
                WHEN form_sessions.completed_at IS NOT NULL THEN NULL
                ELSE form_sessions.last_reminder_at
            END,
            reminder_count = CASE
                WHEN form_sessions.completed_at IS NOT NULL THEN 0
                ELSE form_sessions.reminder_count
            END
        """,
        user_id,
        slug,
    )
    logger.info("form_session: started user_id=%s slug=%s", user_id, slug)


async def mark_form_completed(user_id: int, form_slug: str) -> tuple[Optional[dict], bool]:
    slug = resolve_form_slug(form_slug)
    if not slug:
        return None, False

    existing = await fetchrow(
        "SELECT * FROM form_sessions WHERE user_id=$1 AND form_slug=$2",
        user_id,
        slug,
    )
    if existing and existing.get("completed_at"):
        return existing, False

    if existing:
        row = await fetchrow(
            """
            UPDATE form_sessions
            SET completed_at = NOW(),
                last_reminder_at = NULL
            WHERE id = $1
            RETURNING *
            """,
            existing["id"],
        )
        logger.info("form_session: completed user_id=%s slug=%s (existing)", user_id, slug)
        return row, True

    row = await fetchrow(
        """
        INSERT INTO form_sessions (user_id, form_slug, started_at, completed_at, last_reminder_at, reminder_count)
        VALUES ($1, $2, NOW(), NOW(), NULL, 0)
        RETURNING *
        """,
        user_id,
        slug,
    )
    logger.info("form_session: completed user_id=%s slug=%s (new)", user_id, slug)
    return row, True


async def upsert_test_request(
    *,
    tg_user_id: int,
    user_id: Optional[int],
    birthdate: date,
    preferred_name: Optional[str],
) -> Optional[dict]:
    try:
        return await fetchrow(
            """
            INSERT INTO test_requests (tg_user_id, user_id, birthdate, preferred_name, status)
            VALUES ($1, $2, $3, $4, 'waiting')
            ON CONFLICT (tg_user_id) DO UPDATE
            SET user_id = COALESCE(EXCLUDED.user_id, test_requests.user_id),
                birthdate = EXCLUDED.birthdate,
                preferred_name = EXCLUDED.preferred_name,
                status = 'waiting',
                updated_at = NOW()
            RETURNING *
            """,
            tg_user_id,
            user_id,
            birthdate,
            preferred_name,
        )
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning(
            "test_request upsert failed: tg_user_id=%s err=%s",
            tg_user_id,
            exc,
        )
        return None


async def create_analysis_request(
    *,
    tg_user_id: int,
    user_id: Optional[int],
    preferred_format: str,
    contact: str,
    preferred_time: str,
) -> Optional[dict]:
    try:
        return await fetchrow(
            """
            INSERT INTO analysis_requests (
                tg_user_id,
                user_id,
                preferred_format,
                contact,
                preferred_time
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            tg_user_id,
            user_id,
            preferred_format,
            contact,
            preferred_time,
        )
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning(
            "analysis_request insert failed: tg_user_id=%s err=%s",
            tg_user_id,
            exc,
        )
        return None


_ANALYSIS_DEFAULT_INTRO = (
    "Персональный разбор.\n\n"
    "Ответь на несколько вопросов, чтобы оставить заявку."
)
_ANALYSIS_DEFAULT_FORMAT_PROMPT = (
    "Расскажи, как тебе удобно провести разбор. Укажи желаемую дату/время и контакт для связи."
)
_ANALYSIS_DEFAULT_FORMAT_RETRY = (
    "Нужны желаемые дата/время и контакт, чтобы запланировать разбор. Напиши эти данные."
)
_ANALYSIS_DEFAULT_CONTACT_PROMPT = (
    "Оставь контакт для связи: телефон, @username или другой удобный способ."
)
_ANALYSIS_DEFAULT_CONTACT_RETRY = (
    "Нужен контакт, чтобы мы связались. Напиши телефон, @username или ссылку."
)
_ANALYSIS_DEFAULT_TIME_PROMPT = (
    "Когда тебе удобно провести разбор? Укажи несколько вариантов даты и времени."
)
_ANALYSIS_DEFAULT_TIME_RETRY = (
    "Напиши, когда тебе комфортно провести разбор. Можно предложить несколько слотов."
)
_ANALYSIS_DEFAULT_CONFIRM_PROMPT = (
    "Проверь заявку:\n"
    "• Детали запроса: {format}\n"
    "• Контакт: {contact}\n"
    "• Время: {time}\n\n"
    "Если всё верно — нажми «{confirm_button}»."
)
_ANALYSIS_DEFAULT_SUCCESS = (
    "Заявка сохранена. Команда свяжется с тобой, чтобы согласовать детали."
)

_ANALYSIS_BACK_TOKENS = {
    ANALYSIS_BACK_BUTTON.casefold(),
    ANALYSIS_BACK_BUTTON.strip().casefold(),
    "назад",
}


def _analysis_normalize_text(text: str | None) -> str:
    return (text or "").strip().casefold()


def _analysis_is_back(text: str | None) -> bool:
    if not text:
        return False
    normalized = _analysis_normalize_text(text)
    if not normalized:
        return False
    arrowless = normalized.replace("⬅️", "").strip()
    return normalized in _ANALYSIS_BACK_TOKENS or arrowless == "назад"


async def _analysis_get_intro_text() -> str:
    intro_text, _ = await _get_content_with_source("menu.analysis.intro", "")
    if intro_text.strip():
        return intro_text
    legacy_text, _ = await _get_content_with_source(
        "menu.analysis",
        _ANALYSIS_DEFAULT_INTRO,
    )
    return legacy_text or _ANALYSIS_DEFAULT_INTRO


async def _analysis_send_format_prompt(
    message: types.Message,
    *,
    include_intro: bool = False,
) -> None:
    from . import render_content

    parts: list[str] = []
    if include_intro:
        intro = (await _analysis_get_intro_text()).strip()
        if intro:
            parts.append(intro)
    prompt = (await _get_content("menu.analysis.format_prompt", _ANALYSIS_DEFAULT_FORMAT_PROMPT)).strip()
    if prompt:
        parts.append(prompt)
    text = "\n\n".join(parts) if parts else _ANALYSIS_DEFAULT_FORMAT_PROMPT
    await message.answer(text, reply_markup=cancel_keyboard())


async def _analysis_send_format_retry(message: types.Message) -> None:
    retry_text = await _get_content("menu.analysis.format_retry", _ANALYSIS_DEFAULT_FORMAT_RETRY)
    text = retry_text.strip() or _ANALYSIS_DEFAULT_FORMAT_RETRY
    await message.answer(text, reply_markup=cancel_keyboard())


async def _analysis_send_contact_prompt(message: types.Message) -> None:
    prompt = await _get_content("menu.analysis.contact_prompt", _ANALYSIS_DEFAULT_CONTACT_PROMPT)
    text = prompt.strip() or _ANALYSIS_DEFAULT_CONTACT_PROMPT
    await message.answer(
        text,
        reply_markup=cancel_keyboard(extra_buttons=[ANALYSIS_BACK_BUTTON]),
    )


async def _analysis_send_contact_retry(message: types.Message) -> None:
    retry_text = await _get_content("menu.analysis.contact_retry", _ANALYSIS_DEFAULT_CONTACT_RETRY)
    text = retry_text.strip() or _ANALYSIS_DEFAULT_CONTACT_RETRY
    await message.answer(
        text,
        reply_markup=cancel_keyboard(extra_buttons=[ANALYSIS_BACK_BUTTON]),
    )


async def _analysis_send_time_prompt(message: types.Message) -> None:
    prompt = await _get_content("menu.analysis.time_prompt", _ANALYSIS_DEFAULT_TIME_PROMPT)
    text = prompt.strip() or _ANALYSIS_DEFAULT_TIME_PROMPT
    await message.answer(
        text,
        reply_markup=cancel_keyboard(extra_buttons=[ANALYSIS_BACK_BUTTON]),
    )


async def _analysis_send_time_retry(message: types.Message) -> None:
    retry_text = await _get_content("menu.analysis.time_retry", _ANALYSIS_DEFAULT_TIME_RETRY)
    text = retry_text.strip() or _ANALYSIS_DEFAULT_TIME_RETRY
    await message.answer(
        text,
        reply_markup=cancel_keyboard(extra_buttons=[ANALYSIS_BACK_BUTTON]),
    )


def _analysis_escape_value(value: str | None) -> str:
    if value is None:
        return "—"
    cleaned = value.strip()
    return html.escape(cleaned) if cleaned else "—"


def _analysis_display_values(data: dict) -> tuple[str, str, str]:
    return (
        _analysis_escape_value(data.get("analysis_format")),
        _analysis_escape_value(data.get("analysis_contact")),
        _analysis_escape_value(data.get("analysis_time")),
    )


async def _analysis_send_confirm_prompt(message: types.Message, state: FSMContext) -> None:
    from . import render_content

    data = await state.get_data()
    if not data or not all(data.get(key) for key in ("analysis_format", "analysis_contact", "analysis_time")):
        await state.set_state(AnalysisStates.waiting_format)
        await _analysis_send_format_prompt(message)
        return

    format_value, contact_value, time_value = _analysis_display_values(data)
    template = await _get_content(
        "menu.analysis.confirm_prompt",
        _ANALYSIS_DEFAULT_CONFIRM_PROMPT,
    )
    rendered = render_content(
        template,
        format=format_value,
        contact=contact_value,
        time=time_value,
        confirm_button=ANALYSIS_CONFIRM_BUTTON,
    )
    fallback = render_content(
        _ANALYSIS_DEFAULT_CONFIRM_PROMPT,
        format=format_value,
        contact=contact_value,
        time=time_value,
        confirm_button=ANALYSIS_CONFIRM_BUTTON,
    )
    await message.answer(
        rendered.strip() or fallback,
        reply_markup=analysis_confirm_keyboard(),
    )


async def _analysis_success_text(data: dict) -> str:
    from . import render_content

    format_value, contact_value, time_value = _analysis_display_values(data)
    template = await _get_content(
        "menu.analysis.success",
        _ANALYSIS_DEFAULT_SUCCESS,
    )
    rendered = render_content(
        template,
        format=format_value,
        contact=contact_value,
        time=time_value,
    )
    fallback = render_content(
        _ANALYSIS_DEFAULT_SUCCESS,
        format=format_value,
        contact=contact_value,
        time=time_value,
    )
    return rendered.strip() or fallback


@forms_router.message(StateFilter("*"), F.text == "Пройти тест")
async def menu_test(message: types.Message, state: FSMContext):
    from . import (
        _get_user_and_admin,
        _reset_state_if_needed,
        ensure_user,
        render_content,
        send_test_section,
    )

    await _reset_state_if_needed(state)
    user, is_admin = await _get_user_and_admin(message)
    if not user:
        user = await ensure_user(message.from_user)

    result = await send_test_section(message, user, is_admin, only_text=True)
    if result:
        intro_text, slug = result
    else:
        intro_text, slug = "", FORM_SLUG_TEST

    await state.set_state(TestStates.waiting_birthdate)
    await state.update_data(
        test_form_slug=slug,
        test_user_id=(user or {}).get("id"),
    )

    intro_template = await _get_content("menu.test_intro", intro_text)
    intro_message = render_content(
        intro_template,
        test_url=TEST_FORM_URL,
        TEST_FORM_URL=TEST_FORM_URL,
    )

    birth_prompt_template = await _get_content(
        "menu.test_birthdate_prompt",
        (
            "Чтобы записать тебя на тест, напиши дату рождения.\n"
            "Подойдут варианты: 24.08.1992 или 24 августа 1992.\n\n"
            "Для отмены нажми «Отмена»."
        ),
    )
    birth_prompt = render_content(
        birth_prompt_template,
        test_url=TEST_FORM_URL,
        TEST_FORM_URL=TEST_FORM_URL,
    )

    parts = [intro_message.strip(), birth_prompt.strip()]
    message_text = "\n\n".join([part for part in parts if part])
    await message.answer(message_text, reply_markup=cancel_keyboard())


@forms_router.message(TestStates.waiting_birthdate, F.text.casefold() == CANCEL_TEXT.lower())
async def test_cancel_birthdate(message: types.Message, state: FSMContext):
    from . import cancel_handler

    await cancel_handler(message, state)


@forms_router.message(TestStates.waiting_birthdate)
async def test_collect_birthdate(message: types.Message, state: FSMContext):
    from . import (
        _format_birthdate,
        _get_notify_admins,
        _is_form_notification_enabled,
        cancel_handler,
        parse_birthdate,
        render_content,
    )

    if (message.text or "").casefold() == CANCEL_TEXT.lower():
        await cancel_handler(message, state)
        return

    birthdate = parse_birthdate(message.text)
    if not birthdate:
        invalid_template = await _get_content(
            "menu.test_birthdate_invalid",
            (
                "Не получилось распознать дату. Попробуй формат 24.08.1992 или 24 августа 1992.\n\n"
                "Если передумала — нажми «Отмена»."
            ),
        )
        response = render_content(
            invalid_template,
            raw=message.text or "",
            RAW=message.text or "",
        )
        await message.answer(response, reply_markup=cancel_keyboard())
        return

    await state.update_data(test_birthdate=birthdate.isoformat())
    await state.set_state(TestStates.waiting_name)

    name_prompt_template = await _get_content(
        "menu.test_name_prompt",
        (
            "Отлично! Как тебя записать в заявке?\n\n"
            "Можно указать короткое имя или ник."
        ),
    )
    formatted_birthdate = _format_birthdate(birthdate)
    name_prompt = render_content(
        name_prompt_template,
        birthdate=formatted_birthdate,
        BIRTHDATE=formatted_birthdate,
    )
    await message.answer(name_prompt, reply_markup=cancel_keyboard())

    notify_admins = _get_notify_admins()
    if notify_admins and await _is_form_notification_enabled(FORM_SLUG_TEST):
        stage_label = "ожидание имени"
        card_lines = [
            "🧪 Заявка на тест: обновление",
            f"tg-id: <code>{message.from_user.id}</code>",
            f"Дата рождения: {_format_birthdate(birthdate)}",
            f"Этап: {stage_label}",
        ]
        try:
            await notify_admins("\n".join(card_lines))
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "test_request: notify_admins birthdate failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )


@forms_router.message(TestStates.waiting_name, F.text.len() > 0)
async def test_collect_name(message: types.Message, state: FSMContext):
    from . import (
        _format_birthdate,
        _get_notify_admins,
        _get_user_and_admin,
        _is_form_notification_enabled,
        answer_with_main_menu,
        build_menu_keyboard,
        cancel_handler,
        ensure_user,
        render_content,
        mark_form_started as _mark_form_started,
        upsert_test_request as _upsert_test_request,
    )

    text = (message.text or "").strip()
    if text.lower() == CANCEL_TEXT.lower():
        await cancel_handler(message, state)
        return

    name = text
    if len(name) < 2:
        invalid_name_template = await _get_content(
            "menu.test_name_invalid",
            "Имя должно содержать хотя бы два символа. Попробуй снова.",
        )
        await message.answer(invalid_name_template, reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    birthdate_raw = data.get("test_birthdate")
    form_slug = data.get("test_form_slug") or FORM_SLUG_TEST
    stored_user_id = data.get("test_user_id")
    if not birthdate_raw:
        await state.set_state(TestStates.waiting_birthdate)
        await message.answer("Начнём с даты рождения. Напиши её ещё раз, пожалуйста.", reply_markup=cancel_keyboard())
        return

    birthdate = date.fromisoformat(birthdate_raw)

    user, is_admin = await _get_user_and_admin(message)
    if not user:
        user = await ensure_user(message.from_user)
    user_id = stored_user_id or (user or {}).get("id")

    if user_id and form_slug:
        try:
            await _mark_form_started(user_id, form_slug)
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "test_request: mark start retry failed user_id=%s slug=%s err=%s",
                user_id,
                form_slug,
                exc,
            )

    preferred_name = name
    await _upsert_test_request(
        tg_user_id=message.from_user.id,
        user_id=user_id,
        birthdate=birthdate,
        preferred_name=preferred_name,
    )

    await state.clear()

    thanks_template = await _get_content(
        "menu.test_thanks",
        (
            "Спасибо, {name}! Мы записали тебя на тестирование.\n"
            "Когда будет готов анализ, администратор напишет в Telegram."
        ),
    )
    safe_name = html.escape(preferred_name)
    if not safe_name:
        safe_name = html.escape(
            (user or {}).get("name")
            or (user or {}).get("full_name")
            or message.from_user.first_name
            or "друг"
        )
    formatted_birthdate = _format_birthdate(birthdate)
    thanks_text = render_content(
        thanks_template,
        name=safe_name,
        NAME=safe_name,
        birthdate=formatted_birthdate,
        BIRTHDATE=formatted_birthdate,
    )

    keyboard = await build_menu_keyboard(user=user, is_admin=is_admin, section="learning")
    await message.answer(thanks_text, reply_markup=keyboard)

    notify_admins = _get_notify_admins()
    if notify_admins and await _is_form_notification_enabled(FORM_SLUG_TEST):
        card_lines = [
            "🧪 Новая запись на тестирование",
            f"tg-id: <code>{message.from_user.id}</code>",
            f"Дата рождения: {_format_birthdate(birthdate)}",
            f"Имя: {safe_name if safe_name else '—'}",
        ]
        try:
            await notify_admins("\n".join(card_lines))
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "test_request: notify_admins failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )


@forms_router.message(StateFilter("*"), F.text == "Записаться на разбор")
async def menu_analysis(message: types.Message, state: FSMContext):
    from . import (
        _get_notify_admins,
        _get_user_and_admin,
        _is_form_notification_enabled,
        _reset_state_if_needed,
        answer_with_main_menu,
        ensure_user,
        mark_form_started as _mark_form_started,
    )

    await _reset_state_if_needed(state)
    user, _ = await _get_user_and_admin(message)
    if not user:
        user = await ensure_user(message.from_user)

    await state.set_state(AnalysisStates.waiting_format)
    await state.update_data(analysis_user_id=(user or {}).get("id"))

    intro = await _analysis_get_intro_text()
    await message.answer(intro.strip(), reply_markup=cancel_keyboard())
    await _analysis_send_format_prompt(message)

    if user and await _is_form_notification_enabled(FORM_SLUG_ANALYSIS):
        user_id = user.get("id")
        if user_id:
            try:
                await _mark_form_started(user_id, FORM_SLUG_ANALYSIS)
            except Exception as exc:  # pragma: no cover - logging only
                logger.warning(
                    "analysis_request: mark start failed user_id=%s err=%s",
                    user_id,
                    exc,
                )

    notify_admins = _get_notify_admins()
    if user and notify_admins and await _is_form_notification_enabled(FORM_SLUG_ANALYSIS):
        try:
            card_lines = [
                "🧭 Заявка на разбор: начало",
                f"tg-id: <code>{message.from_user.id}</code>",
            ]
            if user and user.get("id"):
                card_lines.append(f"user-id: <code>{user['id']}</code>")
            await notify_admins("\n".join(card_lines))
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "analysis_request: notify_admins start failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )


@forms_router.message(AnalysisStates.waiting_format)
async def analysis_collect_format(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if _analysis_normalize_text(text) == _analysis_normalize_text(CANCEL_TEXT):
        from . import cancel_handler

        await cancel_handler(message, state)
        return

    if not text:
        await _analysis_send_format_retry(message)
        return

    await state.update_data(analysis_format=text)
    await state.set_state(AnalysisStates.waiting_contact)
    await _analysis_send_contact_prompt(message)


@forms_router.message(AnalysisStates.waiting_contact)
async def analysis_collect_contact(message: types.Message, state: FSMContext):
    from . import cancel_handler

    text = (message.text or "").strip()
    if _analysis_normalize_text(text) == _analysis_normalize_text(CANCEL_TEXT):
        await cancel_handler(message, state)
        return
    if _analysis_is_back(text):
        await state.set_state(AnalysisStates.waiting_format)
        await _analysis_send_format_prompt(message)
        return

    if not text:
        await _analysis_send_contact_retry(message)
        return

    await state.update_data(analysis_contact=text)
    await state.set_state(AnalysisStates.waiting_time)
    await _analysis_send_time_prompt(message)


@forms_router.message(AnalysisStates.waiting_time)
async def analysis_collect_time(message: types.Message, state: FSMContext):
    from . import cancel_handler

    text = (message.text or "").strip()
    if _analysis_normalize_text(text) == _analysis_normalize_text(CANCEL_TEXT):
        await cancel_handler(message, state)
        return
    if _analysis_is_back(text):
        await state.set_state(AnalysisStates.waiting_contact)
        await _analysis_send_contact_prompt(message)
        return

    if not text:
        await _analysis_send_time_retry(message)
        return

    await state.update_data(analysis_time=text)
    await state.set_state(AnalysisStates.waiting_confirm)
    await _analysis_send_confirm_prompt(message, state)


@forms_router.message(AnalysisStates.waiting_confirm)
async def analysis_confirm_request(message: types.Message, state: FSMContext):
    from . import (
        _get_notify_admins,
        _get_user_and_admin,
        _is_form_notification_enabled,
        answer_with_main_menu,
        cancel_handler,
        ensure_user,
        create_analysis_request as _create_analysis_request,
        mark_form_completed as _mark_form_completed,
    )

    text = (message.text or "").strip()
    if _analysis_normalize_text(text) == _analysis_normalize_text(CANCEL_TEXT):
        await cancel_handler(message, state)
        return
    if _analysis_is_back(text):
        await state.set_state(AnalysisStates.waiting_time)
        await _analysis_send_time_prompt(message)
        return

    if _analysis_normalize_text(text) != _analysis_normalize_text(ANALYSIS_CONFIRM_BUTTON):
        await _analysis_send_confirm_prompt(message, state)
        return

    data = await state.get_data()
    if not data or not all(
        (data.get(key) or "").strip() for key in ("analysis_format", "analysis_contact", "analysis_time")
    ):
        await state.set_state(AnalysisStates.waiting_format)
        await _analysis_send_format_prompt(message, include_intro=True)
        return

    format_raw = (data.get("analysis_format") or "").strip()
    contact_raw = (data.get("analysis_contact") or "").strip()
    time_raw = (data.get("analysis_time") or "").strip()
    user_id = data.get("analysis_user_id")

    request_row = await _create_analysis_request(
        tg_user_id=message.from_user.id,
        user_id=user_id,
        preferred_format=format_raw,
        contact=contact_raw,
        preferred_time=time_raw,
    )

    if user_id and request_row:
        try:
            await _mark_form_completed(user_id, FORM_SLUG_ANALYSIS)
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "analysis_request: mark complete failed user_id=%s err=%s",
                user_id,
                exc,
            )

    notify_admins = _get_notify_admins()
    if request_row and notify_admins and await _is_form_notification_enabled(FORM_SLUG_ANALYSIS):
        try:
            format_value, contact_value, time_value = _analysis_display_values(data)
            card_lines = [
                "🧭 Заявка на разбор",
                f"tg-id: <code>{message.from_user.id}</code>",
            ]
            if user_id:
                card_lines.append(f"user-id: <code>{user_id}</code>")
            full_name = (message.from_user.full_name or "").strip()
            if full_name:
                card_lines.append(f"Имя: {html.escape(full_name)}")
            card_lines.extend(
                [
                    f"Формат: {format_value}",
                    f"Контакт: {contact_value}",
                    f"Время: {time_value}",
                ]
            )
            await notify_admins("\n".join(card_lines))
        except Exception as exc:  # pragma: no cover - logging only
            logger.warning(
                "analysis_request: notify_admins failed tg_user_id=%s err=%s",
                message.from_user.id,
                exc,
            )

    success_text = await _analysis_success_text(data)
    await state.clear()

    user, is_admin = await _get_user_and_admin(message)
    if not user:
        user = await ensure_user(message.from_user)

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        success_text,
        section="learning",
    )
