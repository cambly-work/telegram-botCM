"""User-facing handlers package."""
from aiogram import Router

from . import learning, profile, registration, support
from .states import AnalysisStates, HWStates, RegistrationStates, SupportStates

router = Router(name="user")

for module in (registration, learning, profile, support):
    router.include_router(module.router)

from .. import core as _core

_core.RegistrationStates = RegistrationStates
_core.AnalysisStates = AnalysisStates
_core.HWStates = HWStates
_core.SupportStates = SupportStates

__all__ = [
    "router",
    "AnalysisStates",
    "HWStates",
    "RegistrationStates",
    "SupportStates",
]
