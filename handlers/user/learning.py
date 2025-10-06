"""Handlers for learning and homework flows."""
from aiogram import F, Router
from aiogram.filters import StateFilter

from keyboards import (
    FEEDBACK_OPTIONS,
    LEARNING_PROGRESS_BUTTON,
    LESSON_DONE,
    LESSON_QUESTION,
    LESSON_SKIP,
    NEXT_LESSON,
    SKIP_FEEDBACK,
    WRITE_FEEDBACK,
)

from ..core import (
    analysis_collect_contact,
    analysis_collect_format,
    analysis_collect_time,
    analysis_confirm_request,
    feedback_quick_choice,
    feedback_receive_text,
    feedback_request_text,
    feedback_skip,
    hw_receive_answer,
    menu_analysis,
    lesson_mark_done,
    lesson_next,
    lesson_question,
    lesson_receive_question,
    lesson_skip,
    menu_learning_progress,
    menu_lessons,
)
from .states import AnalysisStates, HWStates

router = Router(name="user-learning")

router.message(StateFilter("*"), F.text == "Бесплатные уроки")(menu_lessons)
router.message(StateFilter("*"), F.text == "Записаться на разбор")(menu_analysis)
router.message(F.text == LEARNING_PROGRESS_BUTTON)(menu_learning_progress)
router.message(F.text == LESSON_DONE)(lesson_mark_done)
router.message(F.text == LESSON_SKIP)(lesson_skip)
router.message(F.text == LESSON_QUESTION)(lesson_question)
router.message(F.text == NEXT_LESSON)(lesson_next)
router.message(HWStates.waiting_answer, F.text.len() > 0)(hw_receive_answer)
router.message(HWStates.waiting_feedback, F.text.len() > 0)(feedback_receive_text)
router.message(HWStates.waiting_feedback, F.text == WRITE_FEEDBACK)(feedback_request_text)
router.message(HWStates.waiting_feedback, F.text == SKIP_FEEDBACK)(feedback_skip)
router.message(HWStates.waiting_feedback, F.text.in_(list(FEEDBACK_OPTIONS.keys())))(feedback_quick_choice)
router.message(HWStates.waiting_question, F.text.len() > 0)(lesson_receive_question)
router.message(AnalysisStates.waiting_format)(analysis_collect_format)
router.message(AnalysisStates.waiting_contact)(analysis_collect_contact)
router.message(AnalysisStates.waiting_time)(analysis_collect_time)
router.message(AnalysisStates.waiting_confirm)(analysis_confirm_request)

__all__ = ["router"]
