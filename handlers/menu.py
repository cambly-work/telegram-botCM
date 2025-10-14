"""Menu-related helpers and handlers."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from aiogram import types
from aiogram.types import ReplyKeyboardMarkup
import yaml

from keyboards import (
    info_menu_keyboard,
    learning_menu_keyboard,
    main_menu_keyboard,
    materials_menu_keyboard,
    profile_menu_keyboard,
)
from settings import YOOMONEY_CHECKOUT_URL

from .config import AT_PRODUCT_ID_CLUB, SUPPORT_CONTACT
from .content import get_content

if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from aiogram import Bot


__all__ = [
    "_MENU_SECTION_PROMPTS",
    "_resolve_checkout_links",
    "answer_with_main_menu",
    "build_menu_keyboard",
    "send_about_section",
    "send_faq_section",
    "send_menu_section",
    "send_magnetism_window_section",
    "send_pay_section",
    "send_rules_section",
]


_MENU_SECTION_PROMPTS: dict[str, tuple[str, str]] = {
    "root": (
        "menu.prompts.root",
        (
            "Главное меню.\n\n"
            "Разделы: «О клубе», «Обучение», «Материалы» и «Профиль». Выбери, что интересно прямо сейчас."
        ),
    ),
    "info": ("menu.prompts.info", "Раздел «О клубе».\n\nВыбери интересующий пункт."),
    "learning": (
        "menu.prompts.learning",
        "Раздел «Обучение».\n\nЗдесь собраны бесплатные уроки, «Мой прогресс», тест и запись на разбор.",
    ),
    "materials": (
        "menu.prompts.materials",
        "Раздел «Материалы».\n\nМатериалы недели, каталог клуба, практики, челленджи и расписание эфиров.",
    ),
    "profile": (
        "menu.prompts.profile",
        "Раздел «Профиль».\n\nПроверяй контакты, статус доступа и обновляй данные.",
    ),
}


async def build_menu_keyboard(
    *,
    user: Optional[dict],
    is_admin: bool,
    section: str = "root",
) -> ReplyKeyboardMarkup:
    """Собирает клавиатуру главного меню."""
    from . import get_menu_flags  # локальный импорт для избежания циклов

    flags = await get_menu_flags()
    payments_open = flags.get("payments_open", True)
    weekly_enabled = flags.get("show_weekly_materials", True)
    schedule_enabled = flags.get("show_schedule", True)
    has_pay = bool(AT_PRODUCT_ID_CLUB)

    if section == "info":
        return info_menu_keyboard()
    if section == "learning":
        return learning_menu_keyboard()
    if section == "materials":
        return materials_menu_keyboard(
            weekly_enabled=weekly_enabled,
            schedule_enabled=schedule_enabled,
        )
    if section == "profile":
        return profile_menu_keyboard(
            has_pay=has_pay,
            payments_open=payments_open,
        )

    return main_menu_keyboard(
        is_admin=is_admin,
        has_pay=has_pay,
        payments_open=payments_open,
    )


async def answer_with_main_menu(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    text: str,
    *,
    section: str = "root",
    from_callback: bool = False,
    use_main_menu_keyboard: bool = True,
    **answer_kwargs: Any,
) -> None:
    """Отправляет или обновляет сообщение с главным меню."""
    from . import get_user_with_id  # локальный импорт для избежания циклов

    user_row = user or await get_user_with_id(message.from_user.id)
    if use_main_menu_keyboard:
        kb = await build_menu_keyboard(user=user_row, is_admin=is_admin, section=section)
        answer_kwargs.setdefault("reply_markup", kb)
    await message.answer(text, **answer_kwargs)


async def send_menu_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    section: str,
    *,
    from_callback: bool = False,
) -> None:
    """Показывает выбранный раздел меню с соответствующей клавиатурой."""
    from . import get_user_with_id  # локальный импорт для избежания циклов

    prompt_key, default_text = _MENU_SECTION_PROMPTS.get(
        section, _MENU_SECTION_PROMPTS["root"]
    )

    user_row = user
    if not user_row:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        if chat_id:
            user_row = await get_user_with_id(chat_id)

    prompt_text = await get_content(prompt_key, default_text)
    keyboard = await build_menu_keyboard(user=user_row, is_admin=is_admin, section=section)
    await message.answer(prompt_text, reply_markup=keyboard)


async def send_about_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    about_text = await get_content(
        "menu.about",
        (
            "CODE: Магнетизм — закрытое пространство для тех, кто хочет:\n\n"
            "- Управлять вниманием, мыслями и эмоциями\n"
            "- Укрепить уверенность и личный магнетизм\n"
            "- Изменить сценарии в отношениях и деньгах\n\n"
            "Внутри тебя ждут:\n"
            "- Подкасты и практики\n"
            "- Челленджи и разборы\n"
            "- Структурная система развития\n\n"
            "Готова присоединиться? Оформи доступ в меню."
        ),
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        about_text,
        section="info",
        from_callback=from_callback,
    )


async def send_faq_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    faq_text = await get_content(
        "menu.faq",
        (
            "FAQ.\n\n"
            "Как получить доступ? — Оформи участие в разделе «Оплата».\n\n"
            "Как проходят уроки? — Видеоуроки + практики, доступ через меню.\n\n"
            f"Как задать вопрос? — Кнопка «Вопрос» в уроке или {SUPPORT_CONTACT}.\n\n"
            "Как продлить доступ? — Раздел «Оплата»."
        ),
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        faq_text,
        section="info",
        from_callback=from_callback,
    )


async def send_rules_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    rules_text = await get_content(
        "menu.rules",
        (
            "Правила CODE: Магнетизм.\n\n"
            "1. Уважение к участницам (участникам).\n"
            "2. Только полезный контент.\n"
            "3. Без спама и рекламы.\n"
            "4. Конфиденциальность.\n"
            "5. Без оскорблений и дискриминации.\n\n"
            "Нарушение = блокировка доступа."
        ),
    )

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        rules_text,
        section="info",
        from_callback=from_callback,
    )


def _resolve_checkout_url() -> str:
    checkout_url = (YOOMONEY_CHECKOUT_URL or "").strip()
    if not checkout_url and AT_PRODUCT_ID_CLUB:
        checkout_url = f"https://antitraining.example/checkout/{AT_PRODUCT_ID_CLUB}"
    return checkout_url


async def _resolve_checkout_links(bot: "Bot") -> Dict[str, str]:
    """Возвращает ссылки для оплаты: deep-link и прямой checkout."""
    from . import _resolve_deep_link  # локальный импорт для избежания циклов

    checkout_url = _resolve_checkout_url()
    deep_link = await _resolve_deep_link(bot, {"section": "pay"})
    display_url = checkout_url or deep_link
    return {
        "display": display_url,
        "deep_link": deep_link or "",
        "external": checkout_url or "",
    }


def _normalize_pay_template(template: str, fallback: str) -> str:
    """Return a valid payment template, ignoring structured YAML dumps."""

    if not template or not template.strip():
        return fallback

    try:
        parsed = yaml.safe_load(template)
    except yaml.YAMLError:
        return template

    if parsed is None:
        return fallback

    if isinstance(parsed, dict) and set(parsed) == {"closed"}:
        return fallback

    return template


async def send_pay_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    from . import get_menu_flags  # локальный импорт для избежания циклов
    from . import render_content  # локальный импорт для избежания циклов

    links = await _resolve_checkout_links(message.bot)
    checkout_url = links["display"]

    if not checkout_url:
        await answer_with_main_menu(
            message,
            user,
            is_admin,
            "Сейчас доступ в клуб бесплатный.",
            section="root",
            from_callback=from_callback,
        )
        return

    flags = await get_menu_flags()
    payments_open = flags.get("payments_open", True)
    if not payments_open:
        closed_text = await get_content(
            "menu.pay.closed",
            "Оплата временно закрыта. Мы сообщим о новом окне, как только оно откроется.",
        )
        await answer_with_main_menu(
            message,
            user,
            is_admin,
            closed_text,
            section="root",
            from_callback=from_callback,
        )
        return

    user_row = user or {}
    missing_contacts: list[str] = []
    buttons_hint_parts: list[str] = []
    if not user_row.get("email"):
        missing_contacts.append("email")
        buttons_hint_parts.append("«Изменить email»")
    if not user_row.get("phone"):
        missing_contacts.append("номер телефона")
        buttons_hint_parts.append("«Изменить телефон»")

    if missing_contacts:
        if len(missing_contacts) == 1:
            missing_text = missing_contacts[0]
        else:
            missing_text = " и ".join(missing_contacts)
        buttons_hint = " и ".join(buttons_hint_parts)
        missing_list = "\n".join(f"• {item}" for item in missing_contacts)
        missing_template = await get_content(
            "menu.pay.missing_contacts",
            (
                "Оплата недоступна без контактов. "
                "Добавь {missing_contacts} в разделе «Профиль». "
                "Используй {buttons_hint}, чтобы заполнить данные."
            ),
        )
        notice = render_content(
            missing_template,
            missing_contacts=missing_text,
            MISSING_CONTACTS=missing_text,
            missing_contacts_list=missing_list,
            MISSING_CONTACTS_LIST=missing_list,
            buttons_hint=buttons_hint,
            BUTTONS_HINT=buttons_hint,
        )
        await answer_with_main_menu(
            message,
            user,
            is_admin,
            notice,
            section="root",
            from_callback=from_callback,
        )
        return

    pay_default = (
        "Доступ в клуб CODE: Магнетизм.\n\n"
        "Тариф: Полный доступ — 2690₽ (единовременно).\n\n"
        "Ссылка на оплату: {checkout_url}\n\n"
        "После оплаты бот автоматически активирует доступ."
    )
    pay_template_raw = await get_content("menu.pay", pay_default)
    pay_template = _normalize_pay_template(pay_template_raw, pay_default)
    pay_text = render_content(
        pay_template,
        checkout_url=checkout_url,
        CHECKOUT_URL=checkout_url,
        CHECKOUT_DEEP_LINK=links["deep_link"],
        CHECKOUT_EXTERNAL_URL=links["external"],
    )

    if flags.get("payments_manual_review", False):
        manual_hint = await get_content(
            "menu.pay.manual_review",
            (
                "Платежи проходят ручную проверку. "
                "Если вы уже оплатили, команда подтвердит доступ и пришлёт уведомление."
            ),
        )
        if manual_hint:
            pay_text = f"{pay_text}\n\n{manual_hint.strip()}"

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        pay_text,
        section="root",
        from_callback=from_callback,
    )


async def send_magnetism_window_section(
    message: types.Message,
    user: Optional[dict],
    is_admin: bool,
    *,
    from_callback: bool = False,
) -> None:
    from . import extract_first_url, mark_form_started, render_content, resolve_form_slug

    default_form_url = "https://forms.gle/iNcUGfiLGNkLW1dc8"
    template = await get_content(
        "menu.learning.magnetism_window",
        (
            "Окно в Магнетизм.\n\n"
            "Заполни форму и получи доступ к следующему шагу.\n\n"
            "{form_url}"
        ),
    )
    default_slug = resolve_form_slug(default_form_url, "magnetism-window")
    message_text = render_content(
        template,
        form_url=default_form_url,
        FORM_URL=default_form_url,
        form_slug=default_slug or "",
        FORM_SLUG=default_slug or "",
    )

    displayed_form_url = extract_first_url(message_text) or default_form_url
    slug = resolve_form_slug(displayed_form_url, default_slug or "magnetism-window")

    await answer_with_main_menu(
        message,
        user,
        is_admin,
        message_text,
        section="learning",
        from_callback=from_callback,
    )

    if slug:
        await mark_form_started(user.get("id"), slug)
