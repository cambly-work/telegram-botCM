"""Tests for the settings helpers."""
from __future__ import annotations

import importlib
import os


def test_admin_ids_skips_invalid_tokens():
    """Valid admin IDs should be preserved even if some tokens are invalid."""
    import settings as settings_module

    original_admin_ids = os.environ.get("ADMIN_IDS")
    os.environ["ADMIN_IDS"] = "101,invalid,  202 , ,foo"

    importlib.reload(settings_module)
    try:
        assert settings_module.ADMIN_IDS == {101, 202}
    finally:
        if original_admin_ids is None:
            os.environ.pop("ADMIN_IDS", None)
        else:
            os.environ["ADMIN_IDS"] = original_admin_ids
        importlib.reload(settings_module)


def test_admin_ids_supports_whitespace_delimiters():
    """Whitespace-delimited IDs should also be parsed correctly."""
    import settings as settings_module

    original_admin_ids = os.environ.get("ADMIN_IDS")
    os.environ["ADMIN_IDS"] = "101  202\n303"

    importlib.reload(settings_module)
    try:
        assert settings_module.ADMIN_IDS == {101, 202, 303}
    finally:
        if original_admin_ids is None:
            os.environ.pop("ADMIN_IDS", None)
        else:
            os.environ["ADMIN_IDS"] = original_admin_ids
        importlib.reload(settings_module)


def test_admin_ids_extracts_numbers_from_mixed_tokens():
    """Numeric substrings should be extracted even with surrounding text."""
    import settings as settings_module

    original_admin_ids = os.environ.get("ADMIN_IDS")
    os.environ["ADMIN_IDS"] = "[101, 202]"

    importlib.reload(settings_module)
    try:
        assert settings_module.ADMIN_IDS == {101, 202}
    finally:
        if original_admin_ids is None:
            os.environ.pop("ADMIN_IDS", None)
        else:
            os.environ["ADMIN_IDS"] = original_admin_ids
        importlib.reload(settings_module)


def test_admin_ids_logs_tokens_without_numbers(caplog):
    """Tokens without digits should still trigger logging and skip parsing."""
    import settings as settings_module

    original_admin_ids = os.environ.get("ADMIN_IDS")
    os.environ["ADMIN_IDS"] = "id=303; role=admin"

    importlib.reload(settings_module)
    try:
        assert settings_module.ADMIN_IDS == {303}
        warnings = [record.message for record in caplog.records if record.levelname == "WARNING"]
        assert any("role=admin" in message for message in warnings)
    finally:
        if original_admin_ids is None:
            os.environ.pop("ADMIN_IDS", None)
        else:
            os.environ["ADMIN_IDS"] = original_admin_ids
        importlib.reload(settings_module)


def test_admin_ids_handles_multiple_numbers_in_single_token():
    """Multiple numbers inside a token should all be captured."""
    import settings as settings_module

    original_admin_ids = os.environ.get("ADMIN_IDS")
    os.environ["ADMIN_IDS"] = "tg=404,  505"

    importlib.reload(settings_module)
    try:
        assert settings_module.ADMIN_IDS == {404, 505}
    finally:
        if original_admin_ids is None:
            os.environ.pop("ADMIN_IDS", None)
        else:
            os.environ["ADMIN_IDS"] = original_admin_ids
        importlib.reload(settings_module)
