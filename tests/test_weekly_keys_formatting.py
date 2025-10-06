from handlers.constants import TELEGRAM_MESSAGE_LIMIT
from handlers.profile import _format_weekly_keys_section


def test_weekly_keys_section_truncates_with_notice():
    header = "🔑 Ключи недели:"
    # Create lines long enough to exceed Telegram's limit when combined.
    lines = [
        f"🔒 Неделя {week}: " + ("ключ" * 40)
        for week in range(1, 60)
    ]

    section_text, omitted = _format_weekly_keys_section(
        lines,
        header=header,
        leading_break="",
    )

    assert len(section_text) <= TELEGRAM_MESSAGE_LIMIT
    assert omitted > 0
    assert "...и ещё" in section_text
    assert f"{omitted} недель" in section_text
    assert section_text.splitlines()[-1].startswith("...и ещё")
