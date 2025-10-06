"""FSM states for user flows."""
from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_name = State()
    waiting_email = State()
    waiting_phone = State()


class AnalysisStates(StatesGroup):
    waiting_format = State()
    waiting_contact = State()
    waiting_time = State()
    waiting_confirm = State()


class HWStates(StatesGroup):
    waiting_answer = State()
    waiting_feedback = State()
    waiting_question = State()


class SupportStates(StatesGroup):
    waiting_question = State()
