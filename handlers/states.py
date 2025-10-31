"""Finite state machine definitions for bot handlers."""
from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_email = State()
    waiting_phone = State()


class AnalysisStates(StatesGroup):
    waiting_request = State()


class HWStates(StatesGroup):
    waiting_answer = State()
    waiting_feedback = State()
    waiting_question = State()


class SupportStates(StatesGroup):
    waiting_question = State()


class BroadcastStates(StatesGroup):
    waiting_segment = State()
    waiting_body = State()
    waiting_confirm = State()
    waiting_template_title = State()
    waiting_template_delete = State()


class ProfileStates(StatesGroup):
    waiting_email = State()
    waiting_phone = State()


class AdminContentStates(StatesGroup):
    waiting_value = State()
    waiting_custom_key = State()
    waiting_custom_value = State()
    waiting_view_key = State()
    waiting_history_key = State()
    waiting_history_choice = State()
    waiting_import_file = State()


class AdminBehaviorStates(StatesGroup):
    waiting_start_text = State()
    waiting_start_media = State()
    waiting_registration_text = State()
    waiting_onboarding_text = State()
    waiting_onboarding_delete = State()


class AdminScheduleStates(StatesGroup):
    waiting_week = State()
    waiting_datetime = State()
    waiting_type = State()
    waiting_description = State()
    waiting_link = State()
    waiting_event_id_edit = State()
    waiting_event_id_archive = State()
    waiting_event_id_restore = State()


class AdminUserStates(StatesGroup):
    choosing_segment = State()
    browsing_users = State()
    viewing_user = State()
    waiting_contacts = State()
    waiting_progress = State()
    waiting_delete_confirm = State()


class AdminPaymentsStates(StatesGroup):
    waiting_access_user = State()
    waiting_revoke_user = State()
    waiting_payment_review = State()


class AdminMaterialsStates(StatesGroup):
    waiting_create_payload = State()
    waiting_update_payload = State()
    waiting_delete_slug = State()
    waiting_delete_confirm = State()
    waiting_grant_payload = State()
    waiting_revoke_payload = State()


class AdminMaterialAssetsStates(StatesGroup):
    waiting_category = State()
    waiting_action = State()
    waiting_add_text = State()
    waiting_add_media = State()
    waiting_delete_choice = State()


class AdminWeeklyKeysStates(StatesGroup):
    waiting_bulk_payload = State()
    waiting_revoke_payload = State()
    waiting_upload_payload = State()


class TestStates(StatesGroup):
    waiting_birthdate = State()
    waiting_name = State()


__all__ = [
    "RegistrationStates",
    "AnalysisStates",
    "HWStates",
    "SupportStates",
    "BroadcastStates",
    "ProfileStates",
    "AdminContentStates",
    "AdminBehaviorStates",
    "AdminScheduleStates",
    "AdminUserStates",
    "AdminPaymentsStates",
    "AdminMaterialsStates",
    "AdminMaterialAssetsStates",
    "AdminWeeklyKeysStates",
    "TestStates",
]
