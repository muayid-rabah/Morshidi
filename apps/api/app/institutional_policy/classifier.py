"""Deterministic academic engine classifier and handoff router (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
Questions querying computable academic eligibility, prerequisite satisfaction,
degree progress, graduation clearance, semester planning, or registration intent
MUST NEVER be answered by textual policy retrieval or LLM inference.
This classifier detects computable inquiries and routes them to authoritative engines.
"""

from __future__ import annotations

import re

from .enums import EngineHandoffTarget
from .models import DeterministicEngineHandoff

# Pre-compiled regex patterns for English and Arabic intent matching
_ELIGIBILITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(can\s+i\s+take|am\s+i\s+eligible|eligibility|prerequisite|prereq|can\s+i\s+register\s+course)\b", re.IGNORECASE),
    re.compile(r"(هل\s+يمكنني\s+(أخذ|تسجيل)|هل\s+يحق\s+لي\s+تسجيل|متطلب\s+سابق|هل\s+استوفيت|متطلبات\s+مادة|هل\s+أستطيع\s+تسجيل)"),
)

_PROGRESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(can\s+i\s+graduate|graduation\s+clearance|remaining\s+credits|credits\s+left|hours\s+remaining|how\s+many\s+hours\s+left|did\s+i\s+finish\s+requirements)\b", re.IGNORECASE),
    re.compile(r"(هل\s+يمكنني\s+التخرج|هل\s+يحق\s+لي\s+التخرج|الساعات\s+المتبقية|متطلبات\s+التخرج|إنهاء\s+الخطة|كم\s+ساعة\s+متبقية|متى\s+أتخرج)"),
)

_SEMESTER_PLANNER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(what\s+courses\s+should\s+i\s+take|plan\s+my\s+semester|recommend\s+courses\s+for\s+next|semester\s+schedule|course\s+load\s+for\s+next)\b", re.IGNORECASE),
    re.compile(r"(ما\s+هي\s+المواد\s+التي\s+أسجلها|خطة\s+الفصل|توصيات\s+المواد|جدول\s+الفصل\s+القادم|اقتراح\s+مواد\s+للفصل|رتبلي\s+مواد\s+الفصل\s+القادم)"),
)

_DEGREE_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(degree\s+path|graduation\s+path|earliest\s+graduation|how\s+many\s+semesters\s+to\s+finish|longest\s+prerequisite\s+sequence)\b", re.IGNORECASE),
    re.compile(r"(مسار\s+التخرج|أقرب\s+فصل\s+للتخرج|كم\s+فصل\s+متبقي|أسرع\s+مسار)"),
)

_MOCK_REGISTRATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(submit\s+mock\s+registration|mock\s+cart|registration\s+intent|declare\s+registration)\b", re.IGNORECASE),
    re.compile(r"(تسجيل\s+تجريبي|رغبات\s+التسجيل|إرسال\s+التسجيل\s+المبدئي)"),
)


def classify_academic_query(query_text: str) -> DeterministicEngineHandoff | None:
    """Classify whether a query pertains to a computable academic rule.

    Returns a typed DeterministicEngineHandoff with the target engine if the query
    requires deterministic computation, or None if the query is a general
    regulatory policy inquiry eligible for institutional policy retrieval.
    """
    cleaned = query_text.strip()
    if not cleaned:
        return None

    for pattern in _ELIGIBILITY_PATTERNS:
        if pattern.search(cleaned):
            return DeterministicEngineHandoff(
                target_engine=EngineHandoffTarget.ELIGIBILITY_ENGINE,
                query_topic="PREREQUISITE_AND_COURSE_ELIGIBILITY",
                reason=(
                    "Course eligibility and prerequisite satisfaction are computable academic facts "
                    "determined strictly by the Phase 5 Eligibility Engine. Policy text cannot decide student eligibility."
                ),
            )

    for pattern in _PROGRESS_PATTERNS:
        if pattern.search(cleaned):
            return DeterministicEngineHandoff(
                target_engine=EngineHandoffTarget.PROGRESS_ENGINE,
                query_topic="ACADEMIC_PROGRESS_AND_GRADUATION_CLEARANCE",
                reason=(
                    "Degree progress, earned credit audit, and graduation clearance are monotonic "
                    "computable facts determined strictly by the Phase 6 Progress Engine."
                ),
            )

    for pattern in _SEMESTER_PLANNER_PATTERNS:
        if pattern.search(cleaned):
            return DeterministicEngineHandoff(
                target_engine=EngineHandoffTarget.SEMESTER_PLANNER_ENGINE,
                query_topic="SEMESTER_WORKLOAD_AND_COURSE_SELECTION",
                reason=(
                    "Semester course recommendations and workload planning are governed strictly "
                    "by the Phase 8 Semester Planner Engine."
                ),
            )

    for pattern in _DEGREE_PATH_PATTERNS:
        if pattern.search(cleaned):
            return DeterministicEngineHandoff(
                target_engine=EngineHandoffTarget.DEGREE_PATH_ENGINE,
                query_topic="DEGREE_PATH_AND_COMPLETION_TIMELINE",
                reason=(
                    "Multi-semester degree path simulation and completion horizons are determined "
                    "strictly by the Phase 9 Degree Path Engine."
                ),
            )

    for pattern in _MOCK_REGISTRATION_PATTERNS:
        if pattern.search(cleaned):
            return DeterministicEngineHandoff(
                target_engine=EngineHandoffTarget.MOCK_REGISTRATION_ENGINE,
                query_topic="MOCK_REGISTRATION_INTENT_PERSISTENCE",
                reason=(
                    "Registration intent validation and declared demand are managed strictly "
                    "by the Phase 6 Mock Registration Engine."
                ),
            )

    return None
