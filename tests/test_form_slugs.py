from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from handlers import (  # noqa: E402  (import after sys.path setup)
    FORM_SLUG_ANALYSIS,
    FORM_SLUG_TEST,
    resolve_form_slug,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://example.com/form?form_slug=analysis", FORM_SLUG_ANALYSIS),
        ("https://example.com/form?slug=test", FORM_SLUG_TEST),
        ("https://example.com/form?form=разбор", FORM_SLUG_ANALYSIS),
    ],
)
def test_resolve_form_slug_from_url(url: str, expected: str) -> None:
    assert resolve_form_slug(url) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("analysis", FORM_SLUG_ANALYSIS),
        ("test", FORM_SLUG_TEST),
        ("TEST", FORM_SLUG_TEST),
    ],
)
def test_resolve_form_slug_from_raw_value(raw: str, expected: str) -> None:
    assert resolve_form_slug(raw) == expected


@pytest.mark.parametrize(
    "alias, expected",
    [
        ("разбор", FORM_SLUG_ANALYSIS),
        ("анкета", FORM_SLUG_ANALYSIS),
        ("magnetism-window", "magnetism-window"),
    ],
)
def test_resolve_form_slug_aliases(alias: str, expected: str) -> None:
    assert resolve_form_slug(alias) == expected


def test_resolve_form_slug_fallback_is_used() -> None:
    assert resolve_form_slug("https://example.com/form", FORM_SLUG_TEST) == FORM_SLUG_TEST
