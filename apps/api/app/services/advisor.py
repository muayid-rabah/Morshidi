"""Authenticated, read-only coordination for the advisor boundary."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import asyncio
import re
from time import perf_counter
import unicodedata

from app.advisor.explanation import (
    AdvisorExplanationProvider,
    ExplanationFailure,
    ExplanationLanguage,
    ExplanationStatus,
    build_explanation_input,
    deterministic_explanation,
    explanation_passes_guards,
    invoke_explanation_provider,
)
from app.advisor.interpretation import (
    InterpretationStatus,
    invoke_advisor_provider_async,
    normalize_advisor_interpretation,
)
from app.advisor.models import (
    AdvisorIntent,
    EntityResolutionStatus,
    StructuredAdvisorResult,
)
from app.advisor.orchestrator import AdvisorContext, orchestrate_advisor_request
from app.advisor.provider import AdvisorLLMProvider, ProviderFailure, RawAdvisorInterpretation
from app.degree_path.models import DegreePathCapacityError, DegreePathComputationTimeout
from app.core.academic_compute import AcademicComputeLimiter
from app.services.student import DEGREE_PATH_BUDGET_SECONDS
from app.catalog.repository import AcademicCatalogRepository
from app.student.models import StudentAcademicState
from app.student.repository import StudentAcademicRepository


class AdvisorConfigurationError(RuntimeError):
    """The server-side advisor service has not been configured."""


class AdvisorProviderError(RuntimeError):
    """A typed provider-boundary failure that contains no provider payload."""

    def __init__(self, failure: ProviderFailure) -> None:
        super().__init__(failure.message_key)
        self.failure = failure


@dataclass(frozen=True)
class AdvisorServiceResult:
    structured_result: StructuredAdvisorResult
    explanation: str | None
    explanation_status: ExplanationStatus
    explanation_language: ExplanationLanguage | None


logger = logging.getLogger(__name__)


def _academic_guard_intent(message: str) -> AdvisorIntent | None:
    """Catch obvious academic-decision requests missed by the LLM router.

    This is a deny-only safety net, not an allowlist for general conversation.
    Ambiguous academic requests still pass through normal clarification rules.
    """
    normalized = unicodedata.normalize("NFKC", message).casefold()
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", normalized)
    normalized = normalized.translate(str.maketrans("أإآى", "اااي"))

    if re.search(r"(?:مسار|خط[ةه]).{0,35}(?:تخرج|درج[ةه])|(?:degree|graduation)\s+path", normalized):
        return AdvisorIntent.DEGREE_PATH_MODELING
    if re.search(r"(?:خطة|خطه|تخطيط).{0,35}(?:فصل|سمستر)|(?:semester|term)\s+plan", normalized):
        return AdvisorIntent.SEMESTER_PLANNING
    if re.search(r"(?:متطلب(?:ات)?\s+سابق[ةه]?|prerequisit|course\s+requirement)", normalized):
        return AdvisorIntent.COURSE_INFORMATION
    if re.search(r"(?:اسجل|تسجيل|انزل|register|enroll|eligible|eligibility).{0,60}(?:ماد[ةه]|مساق|كورس|course|\b\d{6,8}\b)|(?:هل\s+اقدر\s+اسجل|can\s+i\s+(?:take|register|enroll))", normalized):
        return AdvisorIntent.COURSE_ELIGIBILITY
    if re.search(r"(?:كم\s+ساع[ةه]?\s+(?:ضايل|باقي|متبقي|عندي|لي|علي)|(?:ساع[ةه]|credit).{0,30}(?:ضايل|باقي|متبقي|remaining|left|completed|do\s+i\s+have|عندي|لي|علي)|(?:remaining|completed)\s+credits?|how\s+many\s+credits?)", normalized):
        return AdvisorIntent.REMAINING_REQUIREMENTS
    if re.search(r"(?:كم|شو|what|which).{0,25}(?:ماد[ةه]|مواد|مساق|courses?|classes?).{0,35}(?:خلصت|انهيت|نجحت|باقي|متبقي|passed|completed|remaining)|(?:ماد[ةه]|مواد|مساق|courses?|classes?).{0,25}(?:خلصت|انهيت|نجحت|باقي|متبقي|passed|completed|remaining)", normalized):
        return AdvisorIntent.REMAINING_REQUIREMENTS
    if re.search(r"(?:تقدمي|وضعي|معدلي|سجلي|academic\s+progress|my\s+(?:gpa|grades|transcript))", normalized):
        return AdvisorIntent.ACADEMIC_STATUS
    if re.search(r"(?:ترشيح|اقترح|تنصحني|recommend).{0,40}(?:ماد[ةه]|مساق|course|class|فصل|semester)", normalized):
        return AdvisorIntent.COURSE_RECOMMENDATIONS
    if re.search(r"(?:شو\s+انزل|what\s+(?:courses?|classes?)\s+should\s+i\s+take|should\s+i\s+take).{0,45}(?:فصل|semester|course|class|ماد[ةه]|مساق)", normalized):
        return AdvisorIntent.COURSE_RECOMMENDATIONS
    if re.search(r"(?:لائح[ةه]|لوائح|سياس[ةه]|policy|regulation).{0,45}(?:جامع[ةه]|university|academic|تسجيل|graduation)|(?:جامع[ةه]|university).{0,45}(?:لائح[ةه]|لوائح|سياس[ةه]|policy|regulation)", normalized):
        return AdvisorIntent.CLARIFICATION_REQUIRED
    if re.search(r"(?:لو|اذا|if\s+i).{0,50}(?:رسبت|فشلت|fail|غيرت\s+تخصص|change\s+major|رفعت\s+ساعات|increase.{0,15}credit)", normalized):
        return AdvisorIntent.CLARIFICATION_REQUIRED
    if re.search(r"(?:you|your|you've|انت|عندك|لديك|يمكنك).{0,50}(?:gpa|معدل|credit|ساع[ةه]|eligible|مؤهل|تخرج|graduat|course|ماد[ةه])|(?:eligible|مؤهل).{0,35}(?:graduat|تخرج|register|تسجيل)", normalized):
        return AdvisorIntent.CLARIFICATION_REQUIRED
    return None


class AdvisorService:
    """Load only authoritative data needed by one interpreted advisor intent."""

    def __init__(
        self,
        student_repository: StudentAcademicRepository,
        catalog_repository: AcademicCatalogRepository,
        provider: AdvisorLLMProvider,
        explanation_provider: AdvisorExplanationProvider | None = None,
        academic_compute_limiter: AcademicComputeLimiter | None = None,
    ) -> None:
        self._student_repository = student_repository
        self._catalog_repository = catalog_repository
        self._provider = provider
        self._explanation_provider = explanation_provider
        self._academic_compute_limiter = academic_compute_limiter or AcademicComputeLimiter()

    async def advise(self, owner_user_id: str, message: str) -> StructuredAdvisorResult:
        """Interpret once, load server-owned context in batches, and orchestrate."""

        structured, _ = await self._advise_interpreted(owner_user_id, message)
        return structured

    async def _advise_interpreted(
        self, owner_user_id: str, message: str, conversation_context: str = "",
    ) -> tuple[StructuredAdvisorResult, str | None]:
        started = perf_counter()

        provider_output = await invoke_advisor_provider_async(
            self._provider, message, conversation_context)
        routing_ms = round((perf_counter() - started) * 1000, 1)
        if isinstance(provider_output, ProviderFailure):
            raise AdvisorProviderError(provider_output)
        assert isinstance(provider_output, RawAdvisorInterpretation)

        if provider_output.intent == AdvisorIntent.GENERAL_CHAT.value:
            guarded_intent = _academic_guard_intent(message)
            if guarded_intent is None and provider_output.general_response is not None:
                # A misbehaving general-chat response must not assert academic decisions.
                if _academic_guard_intent(provider_output.general_response) is not None:
                    guarded_intent = AdvisorIntent.CLARIFICATION_REQUIRED
            if guarded_intent is not None:
                provider_output = RawAdvisorInterpretation(
                    intent=guarded_intent.value,
                    course_codes_mentioned=tuple(re.findall(r"(?<!\d)\d{6,8}(?!\d)", message))
                    if guarded_intent in (AdvisorIntent.COURSE_ELIGIBILITY, AdvisorIntent.COURSE_INFORMATION) else (),
                )

        state: StudentAcademicState | None = None
        student_context_ms = 0.0
        catalog_ms = 0.0
        resolution_catalog = ()
        if _needs_course_catalog(provider_output):
            phase_started = perf_counter()
            state = await self._student_repository.load_student_academic_state(owner_user_id)
            student_context_ms += (perf_counter() - phase_started) * 1000
            phase_started = perf_counter()
            resolution_catalog = await self._catalog_repository.load_advisor_course_catalog(
                state.study_plan_id
            )
            catalog_ms += (perf_counter() - phase_started) * 1000

        interpretation = normalize_advisor_interpretation(
            message,
            provider_output,
            resolution_catalog,
        )
        if interpretation.status is InterpretationStatus.INTERPRETATION_FAILED:
            assert interpretation.failure is not None
            raise AdvisorProviderError(interpretation.failure)
        request = interpretation.normalized_request
        assert request is not None

        if request.intent is AdvisorIntent.GENERAL_CHAT:
            assert provider_output.general_response is not None
            result = orchestrate_advisor_request(request, AdvisorContext())
            logger.info("advisor_timing route=GENERAL_CHAT routing_ms=%s total_ms=%.1f", routing_ms, (perf_counter() - started) * 1000)
            return result, provider_output.general_response.strip()

        if request.intent in (
            AdvisorIntent.GENERAL_ACADEMIC_INFORMATION,
            AdvisorIntent.CLARIFICATION_REQUIRED,
            AdvisorIntent.OUT_OF_SCOPE,
            AdvisorIntent.OPTION_COMPARISON,
        ):
            return orchestrate_advisor_request(request, AdvisorContext()), None
        if (
            request.course_resolution is not None
            and request.course_resolution.status is EntityResolutionStatus.NOT_FOUND
        ):
            return orchestrate_advisor_request(request, AdvisorContext()), None

        if state is None:
            phase_started = perf_counter()
            state = await self._student_repository.load_student_academic_state(owner_user_id)
            student_context_ms += (perf_counter() - phase_started) * 1000

        progress_catalog = None
        eligibility_catalog = None
        if request.intent in (
            AdvisorIntent.ACADEMIC_STATUS,
            AdvisorIntent.REMAINING_REQUIREMENTS,
            AdvisorIntent.COURSE_RECOMMENDATIONS,
            AdvisorIntent.SEMESTER_PLANNING,
            AdvisorIntent.DEGREE_PATH_MODELING,
            AdvisorIntent.COURSE_INFORMATION,
        ):
            phase_started = perf_counter()
            progress_catalog = await self._catalog_repository.load_progress_catalog(
                state.study_plan_id
            )
            catalog_ms += (perf_counter() - phase_started) * 1000
        if request.intent in (
            AdvisorIntent.COURSE_ELIGIBILITY,
            AdvisorIntent.COURSE_RECOMMENDATIONS,
            AdvisorIntent.SEMESTER_PLANNING,
            AdvisorIntent.DEGREE_PATH_MODELING,
            AdvisorIntent.COURSE_INFORMATION,
        ):
            phase_started = perf_counter()
            eligibility_catalog = await self._catalog_repository.load_plan_eligibility_catalog(
                state.study_plan_id
            )
            catalog_ms += (perf_counter() - phase_started) * 1000

        context = AdvisorContext(
            progress_catalog=progress_catalog,
            eligibility_catalog=eligibility_catalog,
            student_attempts=state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )
        phase_started = perf_counter()
        if request.intent in (AdvisorIntent.DEGREE_PATH_MODELING, AdvisorIntent.SEMESTER_PLANNING):
            def calculate(check_budget):
                bounded_context = AdvisorContext(
                    progress_catalog=context.progress_catalog,
                    eligibility_catalog=context.eligibility_catalog,
                    student_attempts=context.student_attempts,
                    reported_cumulative_gpa=context.reported_cumulative_gpa,
                    reported_gpa_scale=context.reported_gpa_scale,
                    reported_earned_credit_hours=context.reported_earned_credit_hours,
                    check_budget=check_budget,
                )
                return orchestrate_advisor_request(request, bounded_context)

            result = await self._academic_compute_limiter.run(calculate)
        else:
            result = orchestrate_advisor_request(request, context)
        deterministic_ms = (perf_counter() - phase_started) * 1000
        logger.info("advisor_timing route=%s routing_ms=%s student_context_ms=%.1f catalog_ms=%.1f deterministic_ms=%.1f total_structured_ms=%.1f", "ACADEMIC_DEEP" if request.intent in (AdvisorIntent.COURSE_RECOMMENDATIONS, AdvisorIntent.SEMESTER_PLANNING, AdvisorIntent.DEGREE_PATH_MODELING) else "ACADEMIC_DIRECT", routing_ms, student_context_ms, catalog_ms, deterministic_ms, (perf_counter() - started) * 1000)
        return result, None

    async def advise_with_explanation(
        self,
        owner_user_id: str,
        message: str,
        conversation_context: str = "",
    ) -> AdvisorServiceResult:
        """Add presentational prose after orchestration without changing its result."""

        structured, general_response = await self._advise_interpreted(
            owner_user_id, message, conversation_context)
        if general_response is not None:
            return AdvisorServiceResult(
                structured, general_response, ExplanationStatus.GENERATED,
                ExplanationLanguage.ARABIC if any("\u0600" <= character <= "\u06ff" for character in message) else ExplanationLanguage.ENGLISH,
            )
        template = deterministic_explanation(message, structured)
        if template is not None:
            return AdvisorServiceResult(
                structured,
                template.text,
                ExplanationStatus.NOT_REQUIRED,
                template.language,
            )
        if self._explanation_provider is None:
            return AdvisorServiceResult(
                structured,
                None,
                ExplanationStatus.UNAVAILABLE,
                None,
            )
        explanation_input = build_explanation_input(message, structured)
        llm_started = perf_counter()
        response = await invoke_explanation_provider(
            self._explanation_provider,
            explanation_input,
        )
        logger.info("advisor_timing explanation_llm_ms=%.1f", (perf_counter() - llm_started) * 1000)
        if isinstance(response, ExplanationFailure):
            logger.warning("advisor explanation failed")
            return AdvisorServiceResult(
                structured,
                None,
                ExplanationStatus.UNAVAILABLE,
                None,
            )
        if not explanation_passes_guards(explanation_input, structured, response):
            logger.warning("advisor explanation rejected by grounding guard")
            return AdvisorServiceResult(
                structured,
                None,
                ExplanationStatus.REJECTED_BY_GUARD,
                None,
            )
        return AdvisorServiceResult(
            structured,
            response.text,
            ExplanationStatus.GENERATED,
            response.language,
        )


def _needs_course_catalog(raw: RawAdvisorInterpretation) -> bool:
    return (
        raw.intent in (
            AdvisorIntent.COURSE_ELIGIBILITY.value,
            AdvisorIntent.COURSE_INFORMATION.value,
        )
        and bool(raw.course_mentions or raw.course_codes_mentioned)
    )
