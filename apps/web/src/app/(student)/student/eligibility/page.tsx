"use client";

import { useRef, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseDifficulty } from "@/components/academic/CourseDifficulty";
import { CourseIdentity, CourseOptions } from "@/components/academic/CourseIdentity";
import type {
  AdaptiveCourseResponse,
  CanTakeDecisionResponse,
  Decision,
  DecisionReason,
  DependencyGroupEvidenceResponse,
  EligibilityExplanationGraph,
  EligibilityGraphMode,
  PrerequisiteLogicStatus,
} from "@/lib/api/student-types";
import { EligibilityExplanationGraphPanel } from "./EligibilityExplanationGraph";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { LoadingSkeletonCard } from "@/components/ui/LoadingSkeleton";
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  CloseIcon,
  EligibilityIcon,
  InfoIcon,
  SearchIcon,
  CompassIcon,
} from "@/components/ui/Icons";

function translateReason(reason: DecisionReason): string {
  switch (reason) {
    case "NO_PREREQUISITES":
      return "لا تتطلب هذه المادة أي متطلبات سابقة في الخطة الدراسية.";
    case "PREREQUISITES_SATISFIED":
      return "تم استيفاء جميع المتطلبات السابقة الأكاديمية بنجاح.";
    case "MISSING_PREREQUISITE_GROUP":
      return "توجد مجموعة متطلبات سابقة إلزامية لم يتم اجتيازها بعد.";
    case "PREREQUISITE_LOGIC_UNRESOLVED":
      return "منطق المتطلبات السابقة غير محسوم ويتطلب تدقيق المرشد الأكاديمي.";
    case "PREREQUISITE_SOURCE_CONFLICT":
      return "يوجد تعارض في توثيق المتطلبات السابقة بين المصادر.";
    case "VERIFIED_PREREQUISITE_MODEL_INCOMPLETE":
      return "نموذج المتطلبات السابقة المعتمد غير مكتمل لهذه المادة.";
    case "TARGET_ALREADY_COMPLETED":
      return "لقد اجتزت هذه المادة مسبقاً وسجلت في رصيدك الأكاديمي.";
    case "TARGET_CURRENTLY_ENROLLED":
      return "هذه المادة مسجلة ومدرجة قيد الدراسة في الفصل الجاري.";
    default:
      return String(reason);
  }
}

function translateLogicStatus(status: PrerequisiteLogicStatus): { label: string; variant: BadgeVariant } {
  switch (status) {
    case "verified":
      return { label: "موثق ومعتمد قطيعاً", variant: "success" };
    case "not_applicable":
      return { label: "لا توجد متطلبات", variant: "neutral" };
    case "unresolved":
      return { label: "غير محسوم", variant: "warning" };
    case "source_conflict":
      return { label: "تعارض مصادر", variant: "error" };
    default:
      return { label: status, variant: "neutral" };
  }
}

export default function EligibilityPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const identities = useCourseIdentities(auth.isAuthenticated);

  const [courseCodeInput, setCourseCodeInput] = useState("");
  const [result, setResult] = useState<CanTakeDecisionResponse | null>(null);
  const [adaptive, setAdaptive] = useState<AdaptiveCourseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [graph, setGraph] = useState<EligibilityExplanationGraph | null>(null);
  const [graphMode, setGraphMode] = useState<EligibilityGraphMode>("why");
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState(false);
  const graphRequestRef = useRef(0);

  const loadGraph = async (code: string, mode: EligibilityGraphMode) => {
    const requestId = ++graphRequestRef.current;
    setGraphMode(mode);
    setGraph(null);
    setGraphLoading(true);
    setGraphError(false);
    try {
      const data = await new StudentApiService(client).getEligibilityExplanationGraph(code, mode);
      if (requestId === graphRequestRef.current) setGraph(data);
    } catch {
      if (requestId === graphRequestRef.current) setGraphError(true);
    } finally {
      if (requestId === graphRequestRef.current) setGraphLoading(false);
    }
  };

  const handleCheck = async () => {
    const code = courseCodeInput.trim().toUpperCase();
    if (!code) {
      setErrorMessage("يرجى إدخال رمز المادة المراد فحص أهليتها.");
      return;
    }

    setCourseCodeInput(code);
    setLoading(true);
    setErrorMessage(null);
    setResult(null);
    graphRequestRef.current += 1;
    setGraph(null);
    setGraphError(false);
    setGraphLoading(false);
    setGraphMode("why");

    try {
      const api = new StudentApiService(client);
      const [data, intelligence] = await Promise.all([
        api.checkEligibility(code), api.getAdaptiveCourseIntelligence().catch(() => null),
      ]);
      setResult(data);
      setAdaptive(intelligence);
      setLoading(false);
      void loadGraph(data.target_course_code, "why");
    } catch (err: unknown) {
      if (err instanceof Error && err.message === "NOT_FOUND") {
        setErrorMessage(`المادة ذات الرمز (${code}) غير موجودة في الخطة الدراسية الحالية.`);
      } else {
        setErrorMessage("تعذر الاتصال بمحرك التحقق الحتمي. يرجى المحاولة لاحقاً.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-[#C9A45C]/30 pb-5">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">
            المحرك الحتمي للأهلية
          </span>
          <span className="text-xs text-[#C6B69C]">قواعد أكاديمية قطعية</span>
        </div>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#F3E9D8]">
          فحص أهلية تسجيل مادة
        </h1>
        <p className="text-xs text-[#C6B69C]">
          فحص استيفاء المتطلبات السابقة والشروط النظامية لتسجيل أي مادة دراسية وفق قواعد جامعتك.
        </p>
      </div>

      {/* Search / Check Box */}
      <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xs">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleCheck();
          }}
          className="space-y-4"
        >
          <div>
            <label className="block text-xs font-bold text-[#F3E9D8] mb-2">
              رمز المادة الأكاديمية (Course Code)
            </label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <SearchIcon className="pointer-events-none absolute right-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#C6B69C]" />
                <input
                  type="text"
                  value={courseCodeInput}
                  list="eligibility-course-identities"
                  onChange={(e) => setCourseCodeInput(e.target.value.toUpperCase())}
                  placeholder="أدخل رمز المادة هنا..."
                  className="w-full rounded-2xl border border-[#C9A45C]/30 bg-[#192720] py-3 pr-12 pl-4 font-mono text-sm font-bold uppercase text-[#F3E9D8] placeholder-[#C6B69C]/50 focus:border-[#D9884A] focus:bg-[#14201B] focus:outline-hidden focus:ring-2 focus:ring-[#D9884A]/20"
                  dir="ltr"
                />
                <CourseOptions id="eligibility-course-identities" identities={identities} />
                {courseCodeInput && <CourseIdentity courseCode={courseCodeInput} identities={identities} />}
              </div>
              <button
                type="submit"
                disabled={loading || !courseCodeInput.trim()}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#D9884A] px-7 py-3 text-xs font-bold text-[#F3E9D8] shadow-xs hover:bg-[#0E5A4F] hover:text-white transition-all disabled:opacity-50"
              >
                <EligibilityIcon className="h-4 w-4" />
                <span>{loading ? "جاري الفحص..." : "فحص الأهلية"}</span>
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Error Message */}
      {errorMessage ? (
        <div role="alert" className="rounded-2xl border border-[#F07869]/40 bg-[#351B17] p-5 text-xs text-[#F07869]">
          <div className="flex items-center gap-2 font-bold mb-1">
            <AlertTriangleIcon className="h-4 w-4" />
            <span>تنبيه في فحص المادة</span>
          </div>
          <p>{errorMessage}</p>
        </div>
      ) : null}

      {/* Loading Skeleton */}
      {loading ? (
        <div role="status" aria-live="polite" aria-label="جارٍ فحص الأهلية" className="space-y-4">
          <LoadingSkeletonCard />
          <LoadingSkeletonCard />
        </div>
      ) : null}

      {/* Decision Results */}
      {!loading && result ? (
        <div className="space-y-6">
          {/* Main Decision Banner */}
          <div
            className={`rounded-3xl border p-7 shadow-xs ${
              result.decision === "ELIGIBLE"
                ? "border-[#5B9974]/50 bg-[#16362E]/50"
                : result.decision === "NOT_ELIGIBLE"
                ? "border-[#F07869]/40 bg-[#351B17]/40"
                : "border-amber-300 bg-amber-50/50"
            }`}
          >
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-4">
                <div
                  className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl shadow-xs ${
                    result.decision === "ELIGIBLE"
                      ? "bg-[#1A4738] text-[#9DCEA9]"
                      : result.decision === "NOT_ELIGIBLE"
                      ? "bg-[#47231D] text-[#F07869]"
                      : "bg-amber-100 text-amber-900"
                  }`}
                >
                  {result.decision === "ELIGIBLE" ? (
                    <CheckCircleIcon className="h-7 w-7" />
                  ) : (
                    <AlertTriangleIcon className="h-7 w-7" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <CourseIdentity courseCode={result.target_course_code} nameAr={result.target_name_ar} nameEn={result.target_name_en} />
                  </div>
                  <h2 className="text-xl font-bold tracking-tight text-[#F3E9D8] mt-0.5">
                    {result.decision === "ELIGIBLE"
                      ? "مؤهل لتسجيل المادة (ELIGIBLE)"
                      : result.decision === "NOT_ELIGIBLE"
                      ? "غير مؤهل لتسجيل المادة (NOT_ELIGIBLE)"
                      : "تتطلب مراجعة المرشد (REVIEW_REQUIRED)"}
                  </h2>
                  <p className="text-xs text-[#C6B69C] mt-1">
                    {result.decision === "ELIGIBLE"
                      ? "مستوفٍ لكافة المتطلبات السابقة والشروط الأكاديمية المقررة في الخطة."
                      : result.decision === "NOT_ELIGIBLE"
                      ? "توجد متطلبات سابقة أو قيود أكاديمية تحول دون التسجيل في الوقت الراهن."
                      : "الحالة تتطلب موافقة أو تدقيقاً استثنائياً من المرشد الأكاديمي."}
                  </p>
                </div>
              </div>

              <div>
                <Badge
                  variant={
                    result.decision === "ELIGIBLE"
                      ? "success"
                      : result.decision === "NOT_ELIGIBLE"
                      ? "error"
                      : "review"
                  }
                  size="md"
                >
                  {result.decision}
                </Badge>
              </div>
            </div>
          </div>

          <EligibilityExplanationGraphPanel
            identities={identities}
            graph={graph}
            mode={graphMode}
            loading={graphLoading}
            error={graphError}
            canAskWhyNot={result.decision !== "ELIGIBLE"}
            onModeChange={(mode) => { void loadGraph(result.target_course_code, mode); }}
            onRetry={() => { void loadGraph(result.target_course_code, graphMode); }}
          />

          <section className="rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-4" aria-label="تقدير صعوبة المادة وقاعدة الساعات">
            <CourseDifficulty course={adaptive?.courses.find((item) => item.course_code === result.target_course_code)} />
            {result.academic_rule_traces?.map((trace) => <p key={trace.rule_id} className="mt-2 text-sm" role="status">
              {trace.reason_ar} / {trace.reason_en} · {trace.earned_completed_credits ?? "غير معروف"}/{trace.required_credits} · {trace.result}
            </p>)}
          </section>

          {/* Details Grid */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {/* Target & Attempt Details */}
            <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-xs space-y-4">
              <h3 className="text-sm font-bold text-[#F3E9D8] border-b border-[#C9A45C]/30 pb-3">
                بيانات المادة وحالة المحاولة
              </h3>

              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[#C6B69C]">رمز المادة:</span>
                  <span className="font-mono font-bold text-[#F3E9D8]" dir="ltr">
                    <CourseIdentity courseCode={result.target_course_code} nameAr={result.target_name_ar} nameEn={result.target_name_en} identities={identities} />
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#C6B69C]">حالة توثيق المتطلبات:</span>
                  <Badge variant={translateLogicStatus(result.prerequisite_logic_status).variant}>
                    {translateLogicStatus(result.prerequisite_logic_status).label}
                  </Badge>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#C6B69C]">مجتازة مسبقاً:</span>
                  <span className="font-bold text-[#F3E9D8]">
                    {result.target_attempt_state.has_passed_target ? "نعم (مجتازة)" : "لا"}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#C6B69C]">قيد الدراسة حالياً:</span>
                  <span className="font-bold text-[#F3E9D8]">
                    {result.target_attempt_state.has_in_progress_target ? "نعم (قيد الدراسة)" : "لا"}
                  </span>
                </div>

                {result.raw_prerequisite_text ? (
                  <div className="pt-2 border-t border-[#C9A45C]/20">
                    <span className="block text-[11px] font-bold text-[#C6B69C] mb-1">
                      النص الأصلي لشرط المتطلب في الخطة:
                    </span>
                    <span className="block rounded-xl bg-[#0F1A17] p-2.5 font-mono text-[11px] text-[#E2B671] border border-[#C9A45C]/30" dir="ltr">
                      {result.raw_prerequisite_text}
                    </span>
                  </div>
                ) : null}
              </div>
            </div>

            {/* Reasons List */}
            <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-xs space-y-4">
              <h3 className="text-sm font-bold text-[#F3E9D8] border-b border-[#C9A45C]/30 pb-3">
                أسباب القرار الأكاديمي الحتمي
              </h3>

              {result.reasons.length === 0 ? (
                <p className="text-xs text-[#C6B69C]">لا توجد أسباب مسجلة.</p>
              ) : (
                <ul className="space-y-2.5 text-xs">
                  {result.reasons.map((reason, idx) => (
                    <li
                      key={idx}
                      className="flex items-start gap-2.5 rounded-2xl bg-[#0B1210] p-3 border border-[#C9A45C]/20"
                    >
                      <CompassIcon className="h-4 w-4 shrink-0 text-[#D9884A] mt-0.5" />
                      <div>
                        <p className="font-bold text-[#F3E9D8]">{translateReason(reason)}</p>
                        <p className="font-mono text-[10px] text-[#C6B69C]" dir="ltr">
                          Code: {reason}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Satisfied Dependency Groups */}
          {result.satisfied_dependency_groups.length > 0 ? (
            <div className="rounded-3xl border border-[#5B9974]/50 bg-[#14201B] p-6 shadow-xs space-y-4">
              <div className="flex items-center gap-2">
                <CheckCircleIcon className="h-5 w-5 text-emerald-600" />
                <h3 className="text-sm font-bold text-[#F3E9D8]">
                  مجموعات المتطلبات المستوفاة بنجاح ({result.satisfied_dependency_groups.length})
                </h3>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {result.satisfied_dependency_groups.map((group: DependencyGroupEvidenceResponse) => (
                  <div
                    key={group.group_number}
                    className="rounded-2xl border border-emerald-100 bg-[#16362E]/40 p-4 text-xs"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-[#B8DEBF]">
                        مجموعة {group.group_number} ({group.dependency_type === "prerequisite" ? "متطلب سابق" : "متطلب متزامن"})
                      </span>
                      <Badge variant="success" size="sm">مستوفاة</Badge>
                    </div>
                    <div className="space-y-1">
                      <span className="text-[11px] text-[#C6B69C]">المواد المجتازة:</span>
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {group.passed_option_course_codes.map((code) => (
                          <span
                            key={code}
                            className="rounded-lg bg-[#14201B] px-2 py-0.5 font-mono text-xs font-bold text-[#9DCEA9] border border-[#5B9974]/50"
                            dir="ltr"
                          >
                            <CourseIdentity courseCode={code} identities={identities} compact />
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Missing Dependency Groups */}
          {result.missing_dependency_groups.length > 0 ? (
            <div className="rounded-3xl border border-[#F07869]/40 bg-[#14201B] p-6 shadow-xs space-y-4">
              <div className="flex items-center gap-2">
                <AlertTriangleIcon className="h-5 w-5 text-[#F07869]" />
                <h3 className="text-sm font-bold text-[#F3E9D8]">
                  المتطلبات السابقة غير المستوفاة ({result.missing_dependency_groups.length})
                </h3>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {result.missing_dependency_groups.map((group: DependencyGroupEvidenceResponse) => (
                  <div
                    key={group.group_number}
                    className="rounded-2xl border border-[#F07869]/30 bg-[#351B17]/40 p-4 text-xs"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-[#F6A094]">
                        مجموعة {group.group_number} ({group.dependency_type === "prerequisite" ? "متطلب سابق" : "متطلب متزامن"})
                      </span>
                      <Badge variant="error" size="sm">مطلوب اجتيازها</Badge>
                    </div>
                    <div className="space-y-1">
                      <span className="text-[11px] text-[#C6B69C]">المواد المطلوبة في هذه المجموعة:</span>
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {group.option_course_codes.map((code) => (
                          <span
                            key={code}
                            className="rounded-lg bg-[#14201B] px-2 py-0.5 font-mono text-xs font-bold text-[#F07869] border border-[#F07869]/40"
                            dir="ltr"
                          >
                            <CourseIdentity courseCode={code} identities={identities} compact />
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Governance Notice */}
          <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-xs text-[#C6B69C] flex items-center gap-3">
            <InfoIcon className="h-5 w-5 text-[#D9884A] shrink-0" />
            <p>
              <strong>مبدأ الحوكمة الأكاديمية:</strong> الذكاء الاصطناعي يشرح والقواعد الحتمية تقرر. تم إصدار نتيجة الأهلية أعلاه مباشرة من محرك القواعد الأكاديمية المعتمد.
            </p>
          </div>
        </div>
      ) : (
        !loading && (
          <EmptyState
            title="ابدأ بفحص أهلية أي مادة"
            description="أدخل رمز المادة في المربع أعلاه أو اختر إحدى المواد المقترحة للتحقق من أهليتك لتسجيلها واستيفائك لمتطلباتها."
            icon={<EligibilityIcon className="h-7 w-7" />}
          />
        )
      )}
    </div>
  );
}
