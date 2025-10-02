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
