import asyncio
from types import SimpleNamespace

import handlers
import handlers.menu as menu


def test_send_pay_section_uses_default_template_for_yaml_dump(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_menu_flags():
        return {"payments_open": True, "payments_manual_review": True}

    async def fake_get_content(key, default):
        if key == "menu.pay":
            return "closed: |\n  Оплата временно закрыта.\n"
        if key == "menu.pay.manual_review":
            return "Ручная проверка активирована."
        return default

    async def fake_resolve_checkout_links(bot):
        return {
            "display": "https://example.com/pay",
            "deep_link": "",
            "external": "https://example.com/pay",
        }

    async def fake_answer(message, user_row, is_admin, text, **kwargs):
        captured["text"] = text
        captured["kwargs"] = kwargs

    monkeypatch.setattr(handlers, "get_menu_flags", fake_get_menu_flags)
    monkeypatch.setattr(menu, "get_content", fake_get_content)
    monkeypatch.setattr(menu, "_resolve_checkout_links", fake_resolve_checkout_links)
    monkeypatch.setattr(menu, "answer_with_main_menu", fake_answer)

    message = SimpleNamespace(from_user=SimpleNamespace(id=42), bot=SimpleNamespace())
    user = {"id": 1, "email": "user@example.com", "phone": "+79991234567"}

    async def run():
        await handlers.send_pay_section(message, user, is_admin=False)

    asyncio.run(run())

    text = captured.get("text", "")
    assert "closed:" not in text
    assert "Ссылка на оплату: https://example.com/pay" in text
    assert text.strip().endswith("Ручная проверка активирована.")


def test_send_pay_section_requires_contacts(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_get_menu_flags():
        return {"payments_open": True}

    async def fake_get_content(key, default):
        return default

    async def fake_resolve_checkout_links(bot):
        return {"display": "https://example.com/pay", "deep_link": "", "external": ""}

    async def fake_answer(message, user_row, is_admin, text, **kwargs):
        captured["text"] = text
        captured["kwargs"] = kwargs

    monkeypatch.setattr(handlers, "get_menu_flags", fake_get_menu_flags)
    monkeypatch.setattr(menu, "get_content", fake_get_content)
    monkeypatch.setattr(menu, "_resolve_checkout_links", fake_resolve_checkout_links)
    monkeypatch.setattr(menu, "answer_with_main_menu", fake_answer)

    message = SimpleNamespace(from_user=SimpleNamespace(id=24), bot=SimpleNamespace())
    user = {"id": 2, "email": None, "phone": None}

    async def run():
        await handlers.send_pay_section(message, user, is_admin=False)

    asyncio.run(run())

    text = captured.get("text", "")
    assert "Оплата недоступна" in text
    assert "Профиль" in text
    assert "Изменить email" in text
