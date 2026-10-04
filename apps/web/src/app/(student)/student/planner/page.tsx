"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseDifficulty } from "@/components/academic/CourseDifficulty";
import { CourseIdentity } from "@/components/academic/CourseIdentity";
import { AcademicGraphExplanation } from "@/components/academic/AcademicGraphExplanation";
import type { AcademicExplanationGraph, AdaptiveCourseResponse } from "@/lib/api/student-types";
import type {
  PlannedCourseEntryResponse,
  SemesterPlanOptionResponse,
  SemesterPlanRequest,
  SemesterPlannerResponse,
} from "@/lib/api/student-types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { LoadingSkeletonCard } from "@/components/ui/LoadingSkeleton";
import { StatCard } from "@/components/ui/StatCard";
import {
  CheckCircleIcon,
  CoursesIcon,
  EligibilityIcon,
  InfoIcon,
  PlannerIcon,
  CompassIcon,
} from "@/components/ui/Icons";

export default function PlannerPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const identities = useCourseIdentities(auth.isAuthenticated);

  // Constraints
  const [maxCreditHours, setMaxCreditHours] = useState<number>(15);
  const [maxCourses, setMaxCourses] = useState<number | undefined>(undefined);
  const [maxOptions, setMaxOptions] = useState<number>(3);

  // States
  const [result, setResult] = useState<SemesterPlannerResponse | null>(null);
  const [adaptive, setAdaptive] = useState<AdaptiveCourseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedOptionIndex, setSelectedOptionIndex] = useState<number>(0);
  const [acceptHeavyBalance, setAcceptHeavyBalance] = useState(false);
  const [graph, setGraph] = useState<AcademicExplanationGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState(false);
  const lastGraphRequest = useRef<SemesterPlanRequest | null>(null);
  const graphRequestId = useRef(0);

  const loadGraph = async (request: SemesterPlanRequest) => {
    const currentId = ++graphRequestId.current;
    setGraphLoading(true);
    setGraphError(false);
    try {
      const nextGraph = await new StudentApiService(client).createSemesterPlanGraph(request);
      if (currentId === graphRequestId.current) setGraph(nextGraph);
    } catch {
      if (currentId === graphRequestId.current) setGraphError(true);
    } finally {
      if (currentId === graphRequestId.current) setGraphLoading(false);
    }
  };

  const handleGeneratePlans = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoading(true);
    setErrorMessage(null);
    setResult(null);
    graphRequestId.current += 1;
    setGraph(null);
    setGraphError(false);

    try {
      const api = new StudentApiService(client);
      const req: SemesterPlanRequest = {
        max_credit_hours: maxCreditHours,
        max_courses: maxCourses && maxCourses > 0 ? maxCourses : null,
        max_options: maxOptions,
        accept_heavy_balance: acceptHeavyBalance,
      };
      const [data, intelligence] = await Promise.all([
        api.createSemesterPlans(req), api.getAdaptiveCourseIntelligence().catch(() => null),
      ]);
      setResult(data);
      setAdaptive(intelligence);
      setSelectedOptionIndex(0);
      lastGraphRequest.current = req;
      setLoading(false);
      void loadGraph(req);
    } catch {
      setErrorMessage("تعذر توليد خطة الفصل الدراسي. تأكد من توفر مواد مؤهلة في خطتك الأكاديمية.");
    } finally {
      setLoading(false);
    }
  };

  const selectedOption: SemesterPlanOptionResponse | null =
    result?.plan_options && result.plan_options.length > selectedOptionIndex
      ? result.plan_options[selectedOptionIndex]
      : null;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-[#C9A45C]/30 pb-5">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">
            المخطط الفصلي الرياضي
          </span>
          <span className="text-xs text-[#C6B69C]">توليد خيارات مثلى</span>
        </div>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#F3E9D8]">
          مخطط الفصل الدراسي
        </h1>
        <p className="text-xs text-[#C6B69C]">
          توليد باقات تسجيل فصلي متوازنة ومثلى، تراعي حدود الساعات، الأثر الأكاديمي، والمتطلبات السابقة.
        </p>
      </div>

      {/* Constraints Config Card */}
      <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xs">
        <form onSubmit={handleGeneratePlans} className="space-y-6">
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
            {/* Max Credits */}
            <div>
              <label className="block text-xs font-bold text-[#F3E9D8] mb-2">
                الحد الأقصى للساعات المعتمدة *
              </label>
              <div className="flex items-center gap-2">
                {[12, 15, 18].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setMaxCreditHours(preset)}
                    className={`rounded-xl px-3 py-1.5 font-mono text-xs font-bold transition-colors ${
                      maxCreditHours === preset
                        ? "bg-[#D9884A] text-[#F3E9D8] shadow-xs"
                        : "bg-[#0F1A17] text-[#C6B69C] border border-[#C9A45C]/30 hover:bg-[#16362E]"
                    }`}
                  >
                    {preset} س
                  </button>
                ))}
                <input
                  type="number"
                  min={3}
                  max={24}
                  value={maxCreditHours}
                  onChange={(e) => setMaxCreditHours(Number(e.target.value))}
                  className="w-20 rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2 font-mono text-xs font-bold text-center text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                />
              </div>
            </div>

            {/* Max Courses */}
            <div>
              <label className="block text-xs font-bold text-[#F3E9D8] mb-2">
                الحد الأقصى لعدد المواد (اختياري)
              </label>
              <input
                type="number"
                min={1}
                max={8}
                placeholder="بدون حد (تلقائي)"
                value={maxCourses ?? ""}
                onChange={(e) =>
                  setMaxCourses(e.target.value ? Number(e.target.value) : undefined)
                }
                className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 font-mono text-xs text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
              />
            </div>

            {/* Max Options */}
            <div>
              <label className="block text-xs font-bold text-[#F3E9D8] mb-2">
                عدد الخيارات البديلة المطلوبة
              </label>
              <select
                value={maxOptions}
                onChange={(e) => setMaxOptions(Number(e.target.value))}
                className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 text-xs text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
              >
                <option value={1}>خيار واحد فقط</option>
                <option value={2}>خياران (أساسي وبديل)</option>
                <option value={3}>3 خيارات (موصى به)</option>
                <option value={5}>5 خيارات متقدمة</option>
              </select>
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={acceptHeavyBalance} onChange={(e) => setAcceptHeavyBalance(e.target.checked)} /> أوافق على عرض خيارات قد تتجاوز مادتين ثقيلتين حفظياً عندما يلزم ذلك / Allow heavy-balance relaxation</label>
          <div className="flex justify-end pt-2 border-t border-[#C9A45C]/20">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#D9884A] px-7 py-3 text-xs font-bold text-[#F3E9D8] shadow-xs hover:bg-[#0E5A4F] hover:text-white transition-all disabled:opacity-50"
            >
              <CompassIcon className="h-4 w-4" />
              <span>{loading ? "جاري احتساب الخيارات الفصلية..." : "توليد خيارات الفصل الدراسي"}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Error State */}
      {errorMessage ? (
        <div role="alert" className="rounded-2xl border border-[#F07869]/40 bg-[#351B17] p-5 text-xs text-[#F07869]">
          <p className="font-bold">{errorMessage}</p>
        </div>
      ) : null}

      {/* Loading Skeleton */}
      {loading ? (
        <div role="status" aria-live="polite" aria-label="جارٍ احتساب الخيارات الفصلية" className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
          </div>
          <LoadingSkeletonCard />
        </div>
      ) : null}

      {/* Results */}
      {!loading && result && result.plan_options.length > 0 ? (
        <div className="space-y-6">
          {result.balance_relaxation_required ? <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">BALANCE_CONSTRAINT_RELAXATION_REQUIRED: قد يتطلب بلوغ حمل الساعات المختار أكثر من مادتين ثقيلتين حفظياً. الخيارات المتوازنة معروضة افتراضياً؛ يمكنك الموافقة صراحةً على عرض الخيارات الأثقل.</p> : null}
          {/* Options Selection Header */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-[#C6B69C]">خيارات الباقات المولدة:</span>
              {result.plan_options.map((option, idx) => (
                <button
                  key={option.rank}
                  type="button"
                  onClick={() => setSelectedOptionIndex(idx)}
                  className={`rounded-2xl px-4 py-2 text-xs font-bold transition-all ${
                    selectedOptionIndex === idx
                      ? "bg-[#D9884A] text-[#F3E9D8] shadow-xs font-extrabold"
                      : "bg-[#14201B] text-[#C6B69C] border border-[#C9A45C]/30 hover:bg-[#0F1A17]"
                  }`}
                >
                  الخيار #{option.rank} {idx === 0 ? "(الأفضل تقييماً)" : ""}
                </button>
              ))}
            </div>

            <span className="text-xs font-mono text-[#C6B69C]">
              تم فحص {result.evaluated_candidate_count} مادة محتملة
            </span>
          </div>

          {selectedOption ? (
            <div className="space-y-6">
              {/* Option Summary Card */}
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <StatCard
                  title="إجمالي الساعات"
                  value={`${selectedOption.total_credit_hours} س`}
                  subtitle={`من أصل حد ${maxCreditHours} ساعة`}
                  icon={<PlannerIcon className="h-5 w-5" />}
                  variant="gold"
                />
                <StatCard
                  title="عدد المواد"
                  value={selectedOption.total_courses}
                  subtitle={`${selectedOption.mandatory_course_count} مواد إجبارية`}
                  icon={<CoursesIcon className="h-5 w-5" />}
                />
                <StatCard
                  title="إضافة رصيد للخطة"
                  value={`${selectedOption.completed_plan_credit_delta} س`}
                  subtitle="مساهمة فعلية في متطلبات التخرج"
                  icon={<CheckCircleIcon className="h-5 w-5" />}
                />
                <StatCard
                  title="تفتح مواداً لاحقة"
                  value={selectedOption.newly_eligible_count}
                  subtitle="مواد ستصبح متاحة في الفصل القادم"
                  icon={<CompassIcon className="h-5 w-5" />}
                />
              </div>

              <section className="rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-4 text-xs" aria-label="توازن الفصل">
                <h3 className="font-bold">توازن الفصل / Semester balance</h3>
                <p>المواد المعتمدة على الحفظ / Memorization-heavy: {selectedOption.memorization_heavy_count ?? 0} / 2 · العبء المتوقع / Estimated workload: {selectedOption.estimated_workload ?? "UNKNOWN"}</p>
                <p>التوازن بين المواد العملية والنظرية / Course-type balance: {selectedOption.learning_type_counts?.map(([kind, count]) => `${kind} ${count}`).join(" · ") ?? "Unknown"}</p>
                {selectedOption.balance_warning ? <p className="text-amber-900">{selectedOption.balance_warning}</p> : null}
              </section>

              {/* Course List in Selected Option */}
              <div className="overflow-hidden rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] shadow-xs">
                <div className="border-b border-[#C9A45C]/30 bg-[#0F1A17]/80 px-6 py-4 flex items-center justify-between">
                  <h3 className="font-bold text-[#F3E9D8] text-sm">
                    مواد الباقة المقترحة للخيار #{selectedOption.rank}
                  </h3>
                  <Badge variant="gold">
                    مجموع رتب التوصية: {selectedOption.recommendation_rank_sum}
                  </Badge>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-right text-xs">
                    <thead>
                      <tr className="border-b border-[#C9A45C]/30 bg-[#192720] text-[#C6B69C]">
                        <th className="px-6 py-3.5 font-bold">المادة</th>
                        <th className="px-6 py-3.5 font-bold">الصعوبة المتوقعة</th>
                        <th className="px-6 py-3.5 font-bold">الساعات</th>
                        <th className="px-6 py-3.5 font-bold">المجموعة التابعة</th>
                        <th className="px-6 py-3.5 font-bold">النوع</th>
                        <th className="px-6 py-3.5 font-bold">رتبة التوصية</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#C9A45C]/10">
                      {selectedOption.courses.map((course: PlannedCourseEntryResponse) => (
                        <tr key={course.course_code} className="hover:bg-[#192720] transition-colors">
                          <td className="px-6 py-4 text-[#F3E9D8]">
                            <CourseIdentity courseCode={course.course_code} nameAr={course.course_name_ar} nameEn={course.course_name_en} />
                          </td>
                          <td className="px-6 py-4 font-bold text-[#F3E9D8]">
                            <CourseDifficulty course={adaptive?.courses.find((item) => item.course_code === course.course_code)} />
                          </td>
                          <td className="px-6 py-4 font-mono text-[#F3E9D8]">
                            {course.credit_hours} ساعات
                          </td>
                          <td className="px-6 py-4 font-mono text-[#C6B69C]" dir="ltr">
                            {course.requirement_group_code}
                          </td>
                          <td className="px-6 py-4">
                            <span className="rounded-md bg-[#0F1A17] px-2 py-0.5 text-[10px] font-semibold text-[#E2B671] border border-[#C9A45C]/30">
                              {course.requirement_type === "MANDATORY" ? "إجباري" : "اختياري"}
                            </span>
                          </td>
                          <td className="px-6 py-4 font-mono font-bold text-[#D9884A]">
                            #{course.phase7_rank}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Newly Eligible Courses */}
              {selectedOption.newly_eligible_course_codes.length > 0 ? (
                <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#0B1210] p-5 text-xs">
                  <div className="flex items-center gap-2 mb-2 font-bold text-[#F3E9D8]">
                    <CompassIcon className="h-4 w-4 text-[#D9884A]" />
                    <span>المواد التي ستفتح للتسجيل عند اجتياز هذه الباقة:</span>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {selectedOption.newly_eligible_course_codes.map((code) => (
                      <span
                        key={code}
                        className="rounded-xl bg-[#14201B] px-3 py-1 font-mono text-xs font-bold text-[#D9884A] border border-[#C9A45C]/30 shadow-xs"
                        dir="ltr"
                      >
                        <CourseIdentity courseCode={code} identities={identities} compact />
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              <AcademicGraphExplanation graph={graph} identities={identities} focusId={`semester-planner:option:${selectedOption.rank}`}
                loading={graphLoading} error={graphError}
                onRetry={() => { if (lastGraphRequest.current) void loadGraph(lastGraphRequest.current); }} />

              {/* Non-Binding Notice */}
              <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-xs text-[#C6B69C] flex items-center gap-3">
                <InfoIcon className="h-5 w-5 text-[#D9884A] shrink-0" />
                <p>
                  <strong>إخلاء مسؤولية تنظيمي:</strong> هذه الباقة مقترحة لأغراض التخطيط الاسترشادي والمحاكاة وليست تسجيلاً رسمياً. التسجيل النهائي يتم عبر بوابة التسجيل الجامعية الرسمية بناءً على الشعب المطروحة.
                </p>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        !loading && (
          <EmptyState
            title="حدد المعايير لتوليد خيارات الفصل"
            description="اضبط الحد الأقصى للساعات المعتمدة وعدد الخيارات البديلة واضغط على 'توليد خيارات الفصل الدراسي' لبدء التخطيط."
            icon={<PlannerIcon className="h-7 w-7" />}
          />
        )
      )}
    </div>
  );
}
