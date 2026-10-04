"""Pure validation and normalization of untrusted advisor interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import inspect

from app.advisor.models import (
    AdvisorContractError,
    AdvisorIntent,
    ClarificationReason,
    ClarificationRequest,
    CourseResolution,
    EntityResolutionStatus,
    NormalizedAdvisorRequest,
    OutOfScopeReason,
    ResolvedCourseReference,
)
from app.advisor.provider import (
    AdvisorInterpretationInput,
    AdvisorLLMProvider,
    ProviderInterpretationResponse,
    ProviderFailure,
    ProviderFailureType,
    RawAdvisorInterpretation,
)
from app.degree_path.models import DegreePathConstraintError, DegreePathConstraints
from app.planner.models import PlannerConstraintError, PlannerConstraints


class InterpretationStatus(str, Enum):
    """Outcome of provider invocation plus deterministic normalization."""

    SUCCESS = "SUCCESS"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    INTERPRETATION_FAILED = "INTERPRETATION_FAILED"


@dataclass(frozen=True)
class AdvisorInterpretationResult:
    """Typed boundary result; failures never contain a guessed request."""

    status: InterpretationStatus
    normalized_request: NormalizedAdvisorRequest | None = None
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if self.status is InterpretationStatus.INTERPRETATION_FAILED:
            if self.failure is None or self.normalized_request is not None:
                raise ValueError("INTERPRETATION_FAILED requires only a failure")
        elif self.normalized_request is None or self.failure is not None:
            raise ValueError("successful interpretation states require only a request")
        elif self.status is InterpretationStatus.CLARIFICATION_REQUIRED:
            if self.normalized_request.intent is not AdvisorIntent.CLARIFICATION_REQUIRED:
                raise ValueError("clarification status requires a clarification request")
        elif self.normalized_request.intent is AdvisorIntent.CLARIFICATION_REQUIRED:
            raise ValueError("clarification requests require clarification status")


def interpret_advisor_message(
    provider: AdvisorLLMProvider,
    user_message: str,
    catalog: tuple[ResolvedCourseReference, ...],
) -> AdvisorInterpretationResult:
    """Invoke one provider once, then validate its output deterministically."""

    provider_response = invoke_advisor_provider(provider, user_message)
    if isinstance(provider_response, ProviderFailure):
        return AdvisorInterpretationResult(
            InterpretationStatus.INTERPRETATION_FAILED,
            failure=provider_response,
        )
    if not isinstance(provider_response, RawAdvisorInterpretation):
        return _failed(
            ProviderFailureType.MALFORMED_STRUCTURED_OUTPUT,
            "advisor.interpretation.malformed_output",
        )
    return normalize_advisor_interpretation(user_message, provider_response, catalog)


def invoke_advisor_provider(
    provider: AdvisorLLMProvider,
    user_message: str,
) -> ProviderInterpretationResponse:
    """Invoke the provider once and collapse unsafe failures to typed results."""

    try:
        provider_input = AdvisorInterpretationInput(user_message)
    except (TypeError, ValueError):
        return ProviderFailure(
            ProviderFailureType.SCHEMA_MISMATCH,
            "advisor.interpretation.schema_mismatch",
        )
    try:
        provider_response = provider.interpret(provider_input)
    except TimeoutError:
        return ProviderFailure(
            ProviderFailureType.TIMEOUT,
            "advisor.interpretation.timeout",
        )
    except Exception:
        return ProviderFailure(
            ProviderFailureType.PROVIDER_UNAVAILABLE,
            "advisor.interpretation.provider_unavailable",
        )
    if not isinstance(provider_response, (RawAdvisorInterpretation, ProviderFailure)):
        return ProviderFailure(
            ProviderFailureType.MALFORMED_STRUCTURED_OUTPUT,
            "advisor.interpretation.malformed_output",
        )
    return provider_response


async def invoke_advisor_provider_async(
    provider: AdvisorLLMProvider,
    user_message: str,
    conversation_context: str = "",
) -> ProviderInterpretationResponse:
    """Async-safe provider invocation supporting sync test and async production adapters."""

    try:
        provider_input = AdvisorInterpretationInput(user_message, conversation_context)
    except (TypeError, ValueError):
        return ProviderFailure(
            ProviderFailureType.SCHEMA_MISMATCH,
            "advisor.interpretation.schema_mismatch",
        )
    try:
        provider_response = provider.interpret(provider_input)
        if inspect.isawaitable(provider_response):
            provider_response = await provider_response
    except TimeoutError:
        return ProviderFailure(
            ProviderFailureType.TIMEOUT,
            "advisor.interpretation.timeout",
        )
    except Exception:
        return ProviderFailure(
            ProviderFailureType.PROVIDER_UNAVAILABLE,
            "advisor.interpretation.provider_unavailable",
        )
    if not isinstance(provider_response, (RawAdvisorInterpretation, ProviderFailure)):
        return ProviderFailure(
            ProviderFailureType.MALFORMED_STRUCTURED_OUTPUT,
            "advisor.interpretation.malformed_output",
        )
    return provider_response


def normalize_advisor_interpretation(
    user_message: str,
    raw: RawAdvisorInterpretation,
    catalog: tuple[ResolvedCourseReference, ...],
) -> AdvisorInterpretationResult:
    """Convert untrusted provider fields into the accepted Phase 10.2 request."""

    if not isinstance(user_message, str) or not user_message.strip() or user_message != user_message.strip():
        return _schema_failure()
    schema_failure = _validate_raw_shape(raw)
    if schema_failure is not None:
        return schema_failure

    if raw.intent is None or raw.intent == AdvisorIntent.CLARIFICATION_REQUIRED.value:
        return _clarification(user_message, ClarificationReason.AMBIGUOUS_INTENT)
    try:
        intent = AdvisorIntent(raw.intent)
    except (TypeError, ValueError):
        return _failed(
            ProviderFailureType.UNSUPPORTED_PROVIDER_RESPONSE,
            "advisor.interpretation.unsupported_intent",
        )

    if not _fields_allowed_for_intent(raw, intent):
        return _schema_failure()

    if intent in (AdvisorIntent.COURSE_ELIGIBILITY, AdvisorIntent.COURSE_INFORMATION):
        references = raw.course_codes_mentioned + raw.course_mentions
        if not references:
            return _clarification(user_message, ClarificationReason.MISSING_COURSE)
        try:
            resolution = resolve_course_references(references, catalog)
        except (AdvisorContractError, TypeError, ValueError):
            return _schema_failure()
        if resolution.status is EntityResolutionStatus.AMBIGUOUS:
            return _clarification(
                user_message,
                ClarificationReason.AMBIGUOUS_COURSE,
                resolution=resolution,
            )
        return _success(
            NormalizedAdvisorRequest(
                user_message=user_message,
                intent=intent,
                course_resolution=resolution,
            )
        )

    if intent is AdvisorIntent.SEMESTER_PLANNING:
        if raw.max_credit_hours_per_semester is None:
            return _clarification(user_message, ClarificationReason.MISSING_REQUIRED_CONSTRAINT)
        try:
            constraints = PlannerConstraints(
                max_credit_hours=raw.max_credit_hours_per_semester,
                max_courses=raw.max_courses_per_semester,
            )
        except (PlannerConstraintError, TypeError, ValueError):
            return _schema_failure()
        return _success(
            NormalizedAdvisorRequest(user_message, intent, planning_constraints=constraints)
        )

    if intent is AdvisorIntent.DEGREE_PATH_MODELING:
        if raw.max_credit_hours_per_semester is None:
            return _clarification(user_message, ClarificationReason.MISSING_REQUIRED_CONSTRAINT)
        try:
            constraint_arguments: dict[str, object] = {
                "max_credit_hours_per_semester": raw.max_credit_hours_per_semester,
                "max_courses_per_semester": raw.max_courses_per_semester,
            }
            if raw.max_semesters_ahead is not None:
                constraint_arguments["max_semesters_ahead"] = raw.max_semesters_ahead
            if raw.max_paths is not None:
                constraint_arguments["max_paths"] = raw.max_paths
            constraints = DegreePathConstraints(**constraint_arguments)  # type: ignore[arg-type]
        except (DegreePathConstraintError, TypeError, ValueError):
            return _schema_failure()
        return _success(
            NormalizedAdvisorRequest(user_message, intent, planning_constraints=constraints)
        )

    if intent is AdvisorIntent.OPTION_COMPARISON:
        if not raw.option_references:
            return _clarification(user_message, ClarificationReason.AMBIGUOUS_OPTION_REFERENCE)
        try:
            request = NormalizedAdvisorRequest(
                user_message,
                intent,
                option_references=raw.option_references,
            )
        except AdvisorContractError:
            return _schema_failure()
        return _success(request)

    if intent is AdvisorIntent.OUT_OF_SCOPE:
        return _success(
            NormalizedAdvisorRequest(
                user_message,
                intent,
                out_of_scope_reason=OutOfScopeReason.UNSUPPORTED_CAPABILITY,
            )
        )

    return _success(NormalizedAdvisorRequest(user_message, intent))


def resolve_course_references(
    references: tuple[str, ...],
    catalog: tuple[ResolvedCourseReference, ...],
) -> CourseResolution:
    """Resolve exact codes or canonical names without aliases or fuzzy matching."""

    if not isinstance(references, tuple) or not isinstance(catalog, tuple):
        raise TypeError("references and catalog must be tuples")
    if any(not isinstance(course, ResolvedCourseReference) for course in catalog):
        raise TypeError("catalog must contain ResolvedCourseReference values")
    codes = tuple(course.course_code for course in catalog)
    if len(codes) != len(set(codes)):
        raise ValueError("catalog course codes must be unique")

    matches: set[ResolvedCourseReference] = set()
    for reference in references:
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("course references must be non-empty strings")
        normalized_reference = _normalize_match_text(reference)
        for course in catalog:
            if _course_matches(normalized_reference, course):
                matches.add(course)

    ordered = tuple(sorted(matches, key=lambda course: course.course_code))
    if not ordered:
        return CourseResolution(EntityResolutionStatus.NOT_FOUND)
    if len(ordered) == 1:
        return CourseResolution(EntityResolutionStatus.RESOLVED, resolved_course=ordered[0])
    return CourseResolution(
        EntityResolutionStatus.AMBIGUOUS,
        candidate_course_codes=tuple(course.course_code for course in ordered),
        candidate_courses=ordered,
    )


def _normalize_match_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _course_matches(reference: str, course: ResolvedCourseReference) -> bool:
    candidates = (course.course_code, course.canonical_arabic_name)
    if course.canonical_english_name is not None:
        candidates += (course.canonical_english_name,)
    return any(reference == _normalize_match_text(candidate) for candidate in candidates)


def _validate_raw_shape(
    raw: RawAdvisorInterpretation,
) -> AdvisorInterpretationResult | None:
    if raw.intent is not None and not isinstance(raw.intent, str):
        return _schema_failure()
    for value in (raw.course_mentions, raw.course_codes_mentioned):
        if not isinstance(value, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            return _schema_failure()
    if not isinstance(raw.option_references, tuple) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in raw.option_references
    ):
        return _schema_failure()
    for value in (
        raw.max_courses_per_semester,
        raw.max_semesters_ahead,
        raw.max_paths,
    ):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            return _schema_failure()
    if raw.clarification_hint is not None and (
        not isinstance(raw.clarification_hint, str) or not raw.clarification_hint.strip()
    ):
        return _schema_failure()
    if raw.general_response is not None and (
        not isinstance(raw.general_response, str) or not raw.general_response.strip()
    ):
        return _schema_failure()
    return None


def _fields_allowed_for_intent(raw: RawAdvisorInterpretation, intent: AdvisorIntent) -> bool:
    if (intent is AdvisorIntent.GENERAL_CHAT) != (raw.general_response is not None):
        return False
    has_course = bool(raw.course_mentions or raw.course_codes_mentioned)
    has_options = bool(raw.option_references)
    has_credit_or_courses = (
        raw.max_credit_hours_per_semester is not None
        or raw.max_courses_per_semester is not None
    )
    has_degree_bounds = raw.max_semesters_ahead is not None or raw.max_paths is not None

    if intent in (AdvisorIntent.COURSE_ELIGIBILITY, AdvisorIntent.COURSE_INFORMATION):
        return not has_options and not has_credit_or_courses and not has_degree_bounds
    if intent is AdvisorIntent.SEMESTER_PLANNING:
        return not has_course and not has_options and not has_degree_bounds
    if intent is AdvisorIntent.DEGREE_PATH_MODELING:
        return not has_course and not has_options
    if intent is AdvisorIntent.OPTION_COMPARISON:
        return not has_course and not has_credit_or_courses and not has_degree_bounds
    return not has_course and not has_options and not has_credit_or_courses and not has_degree_bounds


def _success(request: NormalizedAdvisorRequest) -> AdvisorInterpretationResult:
    return AdvisorInterpretationResult(InterpretationStatus.SUCCESS, normalized_request=request)


def _clarification(
    user_message: str,
    reason: ClarificationReason,
    *,
    resolution: CourseResolution | None = None,
) -> AdvisorInterpretationResult:
    candidates = () if resolution is None else resolution.candidate_course_codes
    clarification = ClarificationRequest(
        reason,
        {
            ClarificationReason.MISSING_COURSE: "advisor.clarify.missing_course",
            ClarificationReason.AMBIGUOUS_COURSE: "advisor.clarify.ambiguous_course",
            ClarificationReason.AMBIGUOUS_INTENT: "advisor.clarify.ambiguous_intent",
            ClarificationReason.MISSING_REQUIRED_CONSTRAINT: "advisor.clarify.required_constraint",
            ClarificationReason.AMBIGUOUS_OPTION_REFERENCE: "advisor.clarify.option_reference",
        }[reason],
        candidates,
    )
    request = NormalizedAdvisorRequest(
        user_message,
        AdvisorIntent.CLARIFICATION_REQUIRED,
        course_resolution=resolution,
        clarification_request=clarification,
    )
    return AdvisorInterpretationResult(
        InterpretationStatus.CLARIFICATION_REQUIRED,
        normalized_request=request,
    )


def _schema_failure() -> AdvisorInterpretationResult:
    return _failed(
        ProviderFailureType.SCHEMA_MISMATCH,
        "advisor.interpretation.schema_mismatch",
    )


def _failed(
    failure_type: ProviderFailureType,
    message_key: str,
) -> AdvisorInterpretationResult:
    return AdvisorInterpretationResult(
        InterpretationStatus.INTERPRETATION_FAILED,
        failure=ProviderFailure(failure_type, message_key),
    )
