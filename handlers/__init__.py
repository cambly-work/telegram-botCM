"""Root handlers package wiring."""
from .core import *  # noqa: F401,F403
from .core import router
from .user import (
    AnalysisStates,
    HWStates,
    RegistrationStates,
    SupportStates,
    router as user_router,
)

router.include_router(user_router)

_core_all = globals().get("__all__", [])

__all__ = [
    *_core_all,
    "router",
    "AnalysisStates",
    "HWStates",
    "RegistrationStates",
    "SupportStates",
]

del _core_all
