"""Authorize, interpret one metric, then project only its deterministic signal."""

from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID

from app.institutional_intelligence_service import (
    InstitutionalIntelligenceService, InstitutionalIntelligenceServiceError,
    InstitutionalIntelligenceServiceErrorCode,
)
from app.mock_registration_persistence.errors import MockRegistrationPersistenceError
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository

from .catalog import METRIC_CATALOG, METRIC_CATALOG_VERSION
from .interpreter import (
    InstitutionalQueryInterpreter, InterpreterUnavailable, InvalidInterpreterOutput,
    validated_metric,
)
from .models import (
    AbstentionReason, InstitutionalAIQueryRequest, InstitutionalAIQueryResponse,
    QueryInterpretation, QueryProvenance, QueryResult, QueryStatus,
)


_UNSAFE_REQUEST = re.compile(
    r"\b(?:select|drop|insert|update|delete|sql|schema|table|rows?|"
    r"gpa|transcript|email|names?|identifiers?|database|ignore|reveal|override)\b|"
    r"\b(?:student|students)\s+(?:data|records|ids|names|list)\b|"
    r"\b(?:show|list|give\s+me)\s+(?:all\s+)?(?:the\s+)?students?\b|"
    r"(?:بيانات\s+الطلاب|أسماء\s+الطلاب|اسماء\s+الطلاب|معدلاتهم|معدل\s+الطلاب|"
    r"أرقامهم\s+الجامعية|ارقامهم\s+الجامعية|قائمة\s+الطلاب|سجلات\s+الطلاب|"
    r"الطلاب\s+اللي|من\s+هم\s+أصحاب|من\s+هم\s+اصحاب|أعطني\s+الطلاب|اعطيني\s+الطلاب|"
    r"تجاهل\s+التعليمات|تجاهل\s+القواعد|اكشف\s+قاعدة\s+البيانات|"
    r"متوسط\s+معدل|أفضل\s+طالب|افضل\s+طالب|نسبة\s+التوظيف)",
    re.IGNORECASE,
)


def _abstain(reason: AbstentionReason) -> InstitutionalAIQueryResponse:
    return InstitutionalAIQueryResponse(status=QueryStatus.ABSTAINED, abstention_reason=reason)


def _language(question: str) -> str:
    return "ar" if re.search(r"[\u0600-\u06ff]", question) else "en"


def _fingerprint(metric_id: str, university_id: UUID, request: InstitutionalAIQueryRequest, provenance: QueryProvenance) -> str:
    payload = {
        "metric_catalog_version": METRIC_CATALOG_VERSION,
        "metric_id": metric_id,
        "university_id": str(university_id),
        "target_period_id": str(request.target_period_id),
        "study_plan_id": str(request.study_plan_id),
        "course_code": request.course_code,
        "catalog_version": provenance.catalog_version,
        "prerequisite_version": provenance.prerequisite_version,
        "demand_source_version": provenance.demand_source_version,
        "policy_version": provenance.policy_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _answer(status: str, label: str, value: int | float | str | None, unit: str, language: str) -> str:
    if status == "SUPPRESSED":
        return ("النتيجة محجوبة وفق سياسة الإفصاح المؤسسي." if language == "ar"
                else "The result is withheld under institutional disclosure policy.")
    if status == "INSUFFICIENT_DATA":
        return ("لا تتوفر بيانات كافية لحساب هذا المؤشر." if language == "ar"
                else "There is insufficient data to compute this metric.")
    if status == "REVIEW_REQUIRED":
        return ("هذا المؤشر يتطلب مراجعة بسبب حالة البيانات الحالية." if language == "ar"
                else "This metric requires review because of the current evidence state.")
    if status == "NOT_APPLICABLE":
        return "هذا المؤشر غير منطبق على النطاق المحدد." if language == "ar" else "This metric is not applicable to this scope."
    return f"{label}: {value} {unit}."


class InstitutionalAIQueryService:
    def __init__(
        self, intelligence: InstitutionalIntelligenceService,
        memberships: SupabaseMockRegistrationRepository,
        interpreter: InstitutionalQueryInterpreter,
    ) -> None:
        self._intelligence = intelligence
        self._memberships = memberships
        self._interpreter = interpreter

    async def available_analyst_universities(self, actor_id: str) -> tuple[UUID, ...]:
        try:
            rows = await self._memberships.load_active_memberships_for_user(
                subject_user_id=UUID(actor_id), role="INSTITUTIONAL_ANALYST")
        except MockRegistrationPersistenceError as error:
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.PERSISTENCE_UNAVAILABLE) from error
        if not rows:
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED)
        return tuple(sorted({row.university_id for row in rows}))

    async def evaluate(self, actor_id: str, request: InstitutionalAIQueryRequest) -> InstitutionalAIQueryResponse:
        university_id = await self._intelligence.authorize_analyst_university(actor_id, request.university_id)
        if _UNSAFE_REQUEST.search(request.question):
            return _abstain(AbstentionReason.UNSUPPORTED_QUERY)
        language = _language(request.question)
        try:
            interpretation = await self._interpreter.interpret(
                request.question, METRIC_CATALOG,
                {"university_id": str(university_id), "target_period_id": str(request.target_period_id),
                 "study_plan_id": str(request.study_plan_id), "course_code": request.course_code},
                language,
            )
        except InterpreterUnavailable:
            return _abstain(AbstentionReason.PROVIDER_UNAVAILABLE)
        except InvalidInterpreterOutput:
            return _abstain(AbstentionReason.INVALID_PROVIDER_OUTPUT)
        metric, reason = validated_metric(interpretation)
        if reason is not None or metric is None:
            return _abstain(reason or AbstentionReason.INVALID_PROVIDER_OUTPUT)
        if interpretation.language != language:
            return _abstain(AbstentionReason.INVALID_PROVIDER_OUTPUT)
        try:
            intelligence = await self._intelligence.evaluate(
                actor_id, target_period_id=request.target_period_id,
                study_plan_id=request.study_plan_id, course_code=request.course_code,
                university_id=university_id,
            )
        except InstitutionalIntelligenceServiceError as error:
            if error.code in {
                InstitutionalIntelligenceServiceErrorCode.TARGET_PERIOD_UNAVAILABLE,
                InstitutionalIntelligenceServiceErrorCode.STUDY_PLAN_UNAVAILABLE,
                InstitutionalIntelligenceServiceErrorCode.COURSE_UNAVAILABLE,
                InstitutionalIntelligenceServiceErrorCode.AGGREGATION_SCOPE_INVALID,
            }:
                return _abstain(AbstentionReason.SCOPE_UNAVAILABLE)
            raise
        signal = intelligence.signals.get(metric.metric_id.value)
        if signal is None or signal.status not in {
            "AVAILABLE", "SUPPRESSED", "INSUFFICIENT_DATA", "REVIEW_REQUIRED", "NOT_APPLICABLE",
        }:
            return _abstain(AbstentionReason.METRIC_UNAVAILABLE)
        value = None if signal.status == "SUPPRESSED" else signal.value
        if signal.status != "AVAILABLE":
            value = None
        elif value is None:
            return _abstain(AbstentionReason.METRIC_UNAVAILABLE)
        if signal.status == "SUPPRESSED":
            flags = tuple(flag for flag in signal.quality_flags if flag == "SUPPRESSED_FOR_PRIVACY")
        else:
            flags = tuple(signal.quality_flags)
        provenance = QueryProvenance(
            catalog_version=intelligence.provenance.catalog_version,
            prerequisite_version=intelligence.provenance.prerequisite_version,
            demand_source_version=intelligence.provenance.demand_source_version,
            policy_version=intelligence.provenance.policy_version,
            computed_at=intelligence.provenance.computed_at,
        )
        return InstitutionalAIQueryResponse(
            status=QueryStatus.ANSWERED,
            interpretation=QueryInterpretation(
                metric_id=metric.metric_id.value,
                metric_label=metric.label_ar if language == "ar" else metric.label_en,
                metric_catalog_version=METRIC_CATALOG_VERSION,
                question_language=language,
                target_period_id=request.target_period_id,
                target_period_key=intelligence.target_period_key,
                study_plan_id=request.study_plan_id,
                course_code=request.course_code,
            ),
            result=QueryResult(
                status=signal.status, value=value, unit=signal.unit,
                quality_flags=flags,
                answer_text=_answer(signal.status, metric.label_ar if language == "ar" else metric.label_en,
                                    value, signal.unit, language),
            ),
            provenance=provenance,
            query_fingerprint=_fingerprint(metric.metric_id.value, university_id, request, provenance),
            limitations=metric.limitations,
        )
