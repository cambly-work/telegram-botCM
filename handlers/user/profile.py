"""Profile-related handlers routing."""
from aiogram import F, Router
from aiogram.filters import Command, StateFilter

from keyboards import CANCEL_TEXT

from ..core import (
    ProfileStates,
    cmd_profile,
    menu_profile_email,
    menu_profile_overview,
    menu_profile_phone,
    profile_cancel_email,
    profile_cancel_phone,
    profile_receive_email,
    profile_receive_phone,
)

router = Router(name="user-profile")

router.message(Command("profile"))(cmd_profile)
router.message(StateFilter("*"), F.text == "Мой профиль")(menu_profile_overview)
router.message(StateFilter("*"), F.text == "Изменить email")(menu_profile_email)
router.message(StateFilter("*"), F.text == "Изменить телефон")(menu_profile_phone)
router.message(ProfileStates.waiting_email, F.text.casefold() == CANCEL_TEXT.lower())(profile_cancel_email)
router.message(ProfileStates.waiting_email, F.text.len() > 0)(profile_receive_email)
router.message(ProfileStates.waiting_phone, F.text.casefold() == CANCEL_TEXT.lower())(profile_cancel_phone)
router.message(ProfileStates.waiting_phone, F.text.len() > 0)(profile_receive_phone)

__all__ = ["router"]
