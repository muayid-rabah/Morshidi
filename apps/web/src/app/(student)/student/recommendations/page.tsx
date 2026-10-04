"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  DashboardError,
  RecommendationCandidateResponse,
  RecommendationResponse,
  ReviewRequiredCourseResponse,
} from "@/lib/api/student-types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorAlert, isRetryableError } from "@/components/ui/ErrorAlert";
import { LoadingSkeletonCard } from "@/components/ui/LoadingSkeleton";
import { StatCard } from "@/components/ui/StatCard";
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  EligibilityIcon,
  InfoIcon,
  RecommendationsIcon,
  CompassIcon,
} from "@/components/ui/Icons";

export default function RecommendationsPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const identities = useCourseIdentities(auth.isAuthenticated);
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [adaptive, setAdaptive] = useState<AdaptiveCourseResponse | null>(null);
  const [error, setError] = useState<DashboardError | null>(null);
  const [loading, setLoading] = useState(true);
  const [graph, setGraph] = useState<AcademicExplanationGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState(false);
  const [expandedCourse, setExpandedCourse] = useState<string | null>(null);
  const graphRequestRef = useRef(0);

  const fetchGraph = async () => {
    const requestId = ++graphRequestRef.current;
    setGraphLoading(true);
    setGraphError(false);
    try {
      const nextGraph = await new StudentApiService(client).getRecommendationGraph();
      if (requestId === graphRequestRef.current) setGraph(nextGraph);
    } catch {
      if (requestId === graphRequestRef.current) setGraphError(true);
    } finally {
      if (requestId === graphRequestRef.current) setGraphLoading(false);
    }
  };

  // Filter
  const [filterType, setFilterType] = useState<"ALL" | "UNLOCKS" | "COMPLETES">("ALL");

  const fetchRecommendations = async () => {
    setLoading(true);
    setError(null);
    graphRequestRef.current += 1;
    setGraph(null);
    setGraphError(false);
    try {
      const api = new StudentApiService(client);
      const [res, intelligence] = await Promise.all([
        api.getRecommendations(), api.getAdaptiveCourseIntelligence().catch(() => null),
      ]);
      setData(res);
      setAdaptive(intelligence);
      void fetchGraph();
    } catch {
      setError("SERVER_ERROR");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (auth.isAuthenticated) {
      void fetchRecommendations();
    }
  }, [auth.isAuthenticated]);

  const stats = useMemo(() => {
    if (!data) return { total: 0, unlocks: 0, completes: 0, review: 0 };
    const total = data.ranked_recommendations.length;
    const unlocks = data.ranked_recommendations.filter((r) => r.newly_eligible_count > 0).length;
    const completes = data.ranked_recommendations.filter((r) => r.completes_requirement_group).length;
    const review = data.review_required_courses.length;
    return { total, unlocks, completes, review };
  }, [data]);

  const filteredRecommendations = useMemo(() => {
    if (!data?.ranked_recommendations) return [];
    const ranks = new Map(adaptive?.recommendations.map((item) => [item.course_code, item.rank]) ?? []);
    return data.ranked_recommendations.filter((r) => {
      if (filterType === "UNLOCKS") return r.newly_eligible_count > 0;
      if (filterType === "COMPLETES") return r.completes_requirement_group;
      return true;
    }).sort((a, b) => (ranks.get(a.course_code) ?? a.rank) - (ranks.get(b.course_code) ?? b.rank));
  }, [data, adaptive, filterType]);
  const difficultyByCode = useMemo(() => new Map(adaptive?.courses.map((item) => [item.course_code, item]) ?? []), [adaptive]);
  const recommendationByCode = useMemo(() => new Map(adaptive?.recommendations.map((item) => [item.course_code, item]) ?? []), [adaptive]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-2 border-b border-[#C9A45C]/30 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">
              التوجيه الأكاديمي الحتمي
            </span>
            <span className="text-xs text-[#C6B69C]">ترتيب خوارزمي معتمد</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#F3E9D8]">
            التوصيات الأكاديمية الذكية
          </h1>
          <p className="text-xs text-[#C6B69C]">
            ترتيب منهجي للمواد الموصى بتسجيلها وفق الأثر الأكاديمي، فتح المتطلبات اللاحقة، واستيفاء المجموعات.
          </p>
        </div>

        {data ? (
          <div className="flex items-center gap-2">
            <Badge variant="gold">
              سياسة التوصية: {data.recommendation_policy_version}
            </Badge>
          </div>
        ) : null}
      </div>

      {/* Error state */}
      {error ? (
        <ErrorAlert
          error={error}
          onRetry={isRetryableError(error) ? fetchRecommendations : undefined}
        />
      ) : null}

      {/* Loading */}
      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
          </div>
          <LoadingSkeletonCard />
        </div>
      ) : null}

      {/* Content */}
      {!loading && !error && data ? (
        <div className="space-y-8">
          {adaptive ? <section className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4" aria-label="ملخص وضعك الأكاديمي">
            <h2 className="font-bold">وضعك الأكاديمي · Your academic situation</h2>
            <p className="mt-1 text-sm">المعدل المُبلّغ / Reported GPA: {adaptive.profile.cumulative_gpa ?? "غير متاح"} / {adaptive.profile.gpa_scale ?? "—"} · الساعات المجتازة / Earned credits: {adaptive.profile.earned_completed_credits} · المواد المكتملة / Completed courses: {adaptive.profile.completed_courses.length}</p>
            <p className="mt-1 text-xs text-[#C6B69C]">ترتيب نمذجي مبني على الأهلية الحتمية والأدلة المتاحة؛ ليس قرار تسجيل رسمي. Modeled ranking, not registration approval. Grade-based personalization requires verified grades and an approved scale.</p>
          </section> : <p role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">تعذر تحميل التقدير الشخصي حالياً؛ الترتيب المعروض عام وليس توصية مخصصة. Personalized estimates are unavailable; the displayed order is generic.</p>}
          {/* Summary Stat Cards */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              title="إجمالي الموصى بها"
              value={stats.total}
              subtitle="مواد مؤهلة وفق القواعد المنمذجة"
              icon={<RecommendationsIcon className="h-5 w-5" />}
            />
            <StatCard
              title="تفتح مواداً لاحقة"
              value={stats.unlocks}
              subtitle="تفك تشابك شجرة المواد"
              icon={<CompassIcon className="h-5 w-5" />}
            />
            <StatCard
              title="تُتم استيفاء مجموعة"
              value={stats.completes}
              subtitle="تغلق متطلب تخرج إلزامي"
              icon={<CheckCircleIcon className="h-5 w-5" />}
            />
            <StatCard
              title="تتطلب مراجعة"
              value={stats.review}
              subtitle="حالات بحاجة لموافقة المرشد"
              icon={<AlertTriangleIcon className="h-5 w-5" />}
            />
          </div>

          {/* Methodology Banner */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#0F1A17] p-5 text-xs text-[#C6B69C]">
            <div className="flex items-start gap-3">
              <CompassIcon className="h-5 w-5 text-[#D9884A] shrink-0 mt-0.5" />
              <div className="space-y-1">
                <h3 className="font-bold text-[#F3E9D8]">منهجية الترتيب الأكاديمي الحتمي</h3>
                <p className="leading-relaxed">
                  {data.methodology_note ||
                    "يتم ترتيب المواد بناءً على معايير صارمة: أولوية متطلبات التخصص الإجبارية، الأثر في فتح مواد لاحقة، والمساهمة في تقليص الساعات المتبقية للمجموعة."}
                </p>
              </div>
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="flex flex-wrap items-center gap-2 border-b border-[#C9A45C]/30 pb-4">
            <span className="text-xs font-bold text-[#C6B69C]">تصفية التوصيات:</span>
            {[
              { key: "ALL", label: `كافة المواد (${stats.total})` },
              { key: "UNLOCKS", label: `تفتح مواداً لاحقة (${stats.unlocks})` },
              { key: "COMPLETES", label: `تُتم مجموعة (${stats.completes})` },
            ].map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setFilterType(tab.key as typeof filterType)}
                className={`rounded-xl px-3.5 py-1.5 text-xs font-bold transition-colors ${
                  filterType === tab.key
                    ? "bg-[#D9884A] text-[#F3E9D8] shadow-xs"
                    : "bg-[#14201B] text-[#C6B69C] border border-[#C9A45C]/30 hover:bg-[#0F1A17]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Ranked List */}
          {filteredRecommendations.length === 0 ? (
            <EmptyState
              title="لا توجد توصيات مطابقة"
              description="لم يتم العثور على مواد مطابقة لمعيار التصفية الحالي."
            />
          ) : (
            <div className="space-y-4">
              {filteredRecommendations.map((rec: RecommendationCandidateResponse) => (
                <div
                  key={rec.course_code}
                  className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-xs transition-all hover:border-[#D9884A]/70"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex items-start gap-4">
                      {/* Rank Badge */}
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#16362E] font-mono text-base font-extrabold text-[#D9884A] border border-[#C9A45C]/30">
                        #{recommendationByCode.get(rec.course_code)?.rank ?? rec.rank}
                      </div>

                      <div className="space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <CourseIdentity courseCode={rec.course_code} nameAr={rec.course_name_ar} nameEn={rec.course_name_en} />
                          <span className="rounded-md bg-[#0F1A17] px-2 py-0.5 text-[10px] font-mono font-bold text-[#D9884A] border border-[#C9A45C]/30" dir="ltr">
                            {rec.credit_hours} ساعات
                          </span>
                        </div>

                        <div className="mt-2">
                          <CourseDifficulty course={difficultyByCode.get(rec.course_code)} />
                          {adaptive ? <p className="text-xs">درجة التوصية النمذجية / Modeled score: {recommendationByCode.get(rec.course_code)?.recommendation_score ?? "—"}/100 · {recommendationByCode.get(rec.course_code)?.confidence ?? "LOW"} confidence</p> : null}
                        </div>

                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <span className="rounded-md bg-[#0B1210] px-2 py-0.5 text-xs text-[#C6B69C] border border-[#C9A45C]/30">
                            المجموعة: <strong className="font-mono" dir="ltr">{rec.requirement_group_code}</strong> (
                            {rec.requirement_type === "MANDATORY" ? "إجباري" : "اختياري"})
                          </span>

                          {rec.completes_requirement_group ? (
                            <Badge variant="success">تُتم استيفاء المجموعة بالكامل</Badge>
                          ) : null}

                          {rec.newly_eligible_count > 0 ? (
                            <Badge variant="gold">
                              تفتح {rec.newly_eligible_count} مواد لاحقة
                            </Badge>
                          ) : null}

                          {rec.previously_attempted ? (
                            <Badge variant="warning">إعادة لرفع المعدل</Badge>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <Link
                        href={`/student/eligibility`}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-[#C9A45C]/30 bg-[#0F1A17] px-3.5 py-2 text-xs font-bold text-[#E2B671] hover:bg-[#16362E] hover:border-[#D9884A] transition-all"
                      >
                        <EligibilityIcon className="h-4 w-4" />
                        <span>فحص الأهلية</span>
                      </Link>
                    </div>
                  </div>

                  {/* Unlocked Courses / Impact Grid */}
                  <div className="mt-5 rounded-2xl bg-[#0B1210] p-4 border border-[#C9A45C]/20 text-xs">
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <span className="text-[#C6B69C]">المساهمة في رصيد الخطة: </span>
                        <strong className="font-mono text-[#F3E9D8]">
                          {rec.effective_credit_contribution} ساعة
                        </strong>
                        <span className="text-[11px] text-[#C6B69C] mr-1">
                          (المتبقي للمجموعة: من {rec.group_remaining_credits_before} إلى {rec.group_remaining_credits_after} س)
                        </span>
                      </div>

                      {rec.newly_eligible_course_codes.length > 0 ? (
                        <div className="flex items-center gap-2">
                          <span className="text-[#C6B69C] shrink-0">المواد التي ستفتح بعدها:</span>
                          <div className="flex flex-wrap gap-1">
                            {rec.newly_eligible_course_codes.map((c) => (
                              <span
                                key={c}
                                className="rounded-md bg-[#14201B] px-2 py-0.5 font-mono text-[11px] font-bold text-[#D9884A] border border-[#C9A45C]/30"
                                dir="ltr"
                              >
                                <CourseIdentity courseCode={c} identities={identities} compact />
                              </span>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="text-[#C6B69C]">
                          لا تفتح متطلبات لاحقة مباشرة
                        </div>
                      )}
                    </div>
                  </div>
                  <button type="button" onClick={() => setExpandedCourse(expandedCourse === rec.course_code ? null : rec.course_code)}
                    aria-expanded={expandedCourse === rec.course_code}
                    className="mt-4 rounded-xl border border-[#C9A45C]/30 px-3 py-2 text-xs font-bold">
                    لماذا هذه النتيجة؟
                  </button>
                  {expandedCourse === rec.course_code ? <div className="mt-3">
                    <AcademicGraphExplanation graph={graph} identities={identities} focusId={`recommendation:${rec.rank}:${rec.course_code}`}
                      loading={graphLoading} error={graphError} onRetry={() => { void fetchGraph(); }} />
                  </div> : null}
                </div>
              ))}
            </div>
          )}

          {/* Review-Required Courses */}
          {data.review_required_courses.length > 0 ? (
            <div className="rounded-3xl border border-amber-300 bg-[#14201B] p-6 shadow-xs space-y-4">
              <div className="flex items-center gap-2">
                <AlertTriangleIcon className="h-5 w-5 text-amber-700" />
                <h3 className="text-sm font-bold text-[#F3E9D8]">
                  مواد تتطلب مراجعة وتنسيق مع المرشد الأكاديمي ({data.review_required_courses.length})
                </h3>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {data.review_required_courses.map((course: ReviewRequiredCourseResponse) => (
                  <div
                    key={course.course_code}
                    className="rounded-2xl border border-amber-200 bg-amber-50/50 p-4 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <CourseIdentity courseCode={course.course_code} nameAr={course.course_name_ar} nameEn={course.course_name_en} />
                      <Badge variant="review" size="sm">مراجعة مرشد</Badge>
                    </div>
                    <p className="text-[11px] text-amber-900">
                      <strong>سبب المراجعة: </strong>
                      {course.review_reason}
                    </p>
                    <AcademicGraphExplanation graph={graph} identities={identities} focusId={`recommendation:review:${course.course_code}`}
                      loading={graphLoading} error={graphError} onRetry={() => { void fetchGraph(); }} />
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Limitations and Governance */}
          <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-xs text-[#C6B69C] space-y-2">
            <div className="flex items-center gap-2 font-bold text-[#F3E9D8]">
              <InfoIcon className="h-4 w-4 text-[#D9884A]" />
              <span>محددات خوارزمية التوصية والمسؤولية الأكاديمية:</span>
            </div>
            <ul className="list-disc list-inside space-y-1 pr-2 text-[11px]">
              {data.limitations.map((lim, idx) => (
                <li key={idx}>{lim}</li>
              ))}
              <li>هذه التوصيات ذات طابع إرشادي وتخضع للشعب المطروحة في جدول الفصل الرسمي.</li>
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
}
