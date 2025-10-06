"""Support handlers router."""
from aiogram import F, Router
from aiogram.filters import Command, StateFilter

from ..core import (
    _SUPPORT_QUESTION_CALLBACK,
    cmd_support,
    menu_support,
    support_prompt_question,
    support_receive_question,
)
from .states import SupportStates

router = Router(name="user-support")

router.message(Command("support"))(cmd_support)
router.message(StateFilter("*"), F.text == "🆘 Поддержка")(menu_support)
router.callback_query(F.data == _SUPPORT_QUESTION_CALLBACK)(support_prompt_question)
router.message(SupportStates.waiting_question)(support_receive_question)

__all__ = ["router"]
