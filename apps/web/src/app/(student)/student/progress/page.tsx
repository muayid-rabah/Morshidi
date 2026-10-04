"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { CourseIdentity } from "@/components/academic/CourseIdentity";
import type {
  AcademicProgressResponse,
  CourseProgressResponse,
  CourseProgressState,
  DashboardError,
  RequirementGroupProgressResponse,
} from "@/lib/api/student-types";
import { Badge } from "@/components/ui/Badge";
import { CircularProgress } from "@/components/ui/CircularProgress";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorAlert, isRetryableError } from "@/components/ui/ErrorAlert";
import { LoadingSkeletonCard } from "@/components/ui/LoadingSkeleton";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatCard } from "@/components/ui/StatCard";
import {
  CheckCircleIcon,
  ClockIcon,
  CoursesIcon,
  ProgressIcon,
  SearchIcon,
  CompassIcon,
} from "@/components/ui/Icons";

import type { BadgeVariant } from "@/components/ui/Badge";

function getCourseStateLabel(state: string): { label: string; variant: BadgeVariant } {
  switch (state as CourseProgressState) {
    case "COMPLETED":
      return { label: "منجزة بنجاح", variant: "success" };
    case "IN_PROGRESS":
      return { label: "قيد الدراسة", variant: "gold" };
    case "ATTEMPTED_NOT_COMPLETED":
      return { label: "محاولة غير مكتملة", variant: "error" };
    case "NOT_ATTEMPTED":
    default:
      return { label: "لم تبدأ بعد", variant: "neutral" };
  }
}

export default function ProgressPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const [progress, setProgress] = useState<AcademicProgressResponse | null>(null);
  const [error, setError] = useState<DashboardError | null>(null);
  const [loading, setLoading] = useState(true);

  // Filters for course list
  const [selectedStateFilter, setSelectedStateFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const fetchProgress = async () => {
    setLoading(true);
    setError(null);
    try {
      const api = new StudentApiService(client);
      const data = await api.getProgress();
      setProgress(data);
    } catch (err: unknown) {
      if (err instanceof Error && err.message === "NOT_FOUND") {
        setError("NOT_FOUND");
      } else {
        setError("SERVER_ERROR");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (auth.isAuthenticated) {
      void fetchProgress();
    }
  }, [auth.isAuthenticated]);

  const completionPercentage = useMemo(() => {
    if (!progress || progress.plan_total_required_credits <= 0) return 0;
    return Math.min(
      100,
      Math.round((progress.completed_plan_credits / progress.plan_total_required_credits) * 100),
    );
  }, [progress]);

  const filteredCourses = useMemo(() => {
    if (!progress?.courses) return [];
    return progress.courses.filter((c: CourseProgressResponse) => {
      const matchesState =
        selectedStateFilter === "ALL" || c.state === selectedStateFilter;
      const matchesSearch =
        searchQuery.trim() === "" ||
        c.course_code.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
        (c.requirement_group_code &&
          c.requirement_group_code.toLowerCase().includes(searchQuery.trim().toLowerCase()));
      return matchesState && matchesSearch;
    });
  }, [progress, selectedStateFilter, searchQuery]);

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col gap-2 border-b border-[#C9A45C]/30 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">
              الخطة والتقدم
            </span>
            <span className="text-xs text-[#C6B69C]">حساب معياري دقيق</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#F3E9D8]">
            التقدم الأكاديمي
          </h1>
          <p className="text-xs text-[#C6B69C]">
            متابعة دقيقة لاستيفاء متطلبات الخطة الدراسية، الساعات المعتمدة، وحالة كل مادة.
          </p>
        </div>

        {progress ? (
          <div className="flex items-center gap-2">
            {progress.all_modeled_plan_requirements_satisfied ? (
              <Badge variant="success">جميع المتطلبات مستوفاة</Badge>
            ) : (
              <Badge variant="gold">الخطة قيد الإنجاز</Badge>
            )}
          </div>
        ) : null}
      </div>

      {/* Error state */}
      {error ? (
        <ErrorAlert
          error={error}
          onRetry={isRetryableError(error) ? fetchProgress : undefined}
        />
      ) : null}

      {/* Loading state */}
      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
          </div>
          <LoadingSkeletonCard />
        </div>
      ) : null}

      {/* Content */}
      {!loading && !error && progress ? (
        <div className="space-y-8">
          {/* Top Progress Overview Card */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xs">
            <div className="grid grid-cols-1 items-center gap-8 md:grid-cols-12">
              <div className="flex flex-col items-center justify-center text-center md:col-span-4 md:border-l md:border-[#C9A45C]/20 md:pl-8">
                <CircularProgress
                  value={progress.completed_plan_credits}
                  max={progress.plan_total_required_credits}
                  size={140}
                  strokeWidth={12}
                  label="نسبة الإنجاز"
                />
                <p className="mt-4 text-xs font-semibold text-[#C6B69C]">
                  تم إنجاز {progress.completed_plan_credits} من أصل {progress.plan_total_required_credits} ساعة
                </p>
              </div>

              <div className="space-y-5 md:col-span-8">
                <div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-[#F3E9D8]">مستوى التقدم التراكمي الإجمالي</span>
                    <span className="font-mono font-bold text-[#D9884A]">{completionPercentage}%</span>
                  </div>
                  <div className="mt-2">
                    <ProgressBar
                      completed={progress.completed_plan_credits}
                      total={progress.plan_total_required_credits}
                      showPercent={false}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 pt-2">
                  <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-center">
                    <span className="block text-[11px] font-semibold text-[#C6B69C]">إجمالي الخطة</span>
                    <span className="mt-1 block font-mono text-xl font-bold text-[#F3E9D8]">
                      {progress.plan_total_required_credits}
                    </span>
                    <span className="text-[10px] text-[#C6B69C]">ساعة مطلوبة</span>
                  </div>

                  <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-center">
                    <span className="block text-[11px] font-semibold text-[#C6B69C]">ساعات منجزة</span>
                    <span className="mt-1 block font-mono text-xl font-bold text-[#9DCEA9]">
                      {progress.completed_plan_credits}
                    </span>
                    <span className="text-[10px] text-[#C6B69C]">ساعة محتسبة</span>
                  </div>

                  <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-center">
                    <span className="block text-[11px] font-semibold text-[#C6B69C]">قيد الدراسة</span>
                    <span className="mt-1 block font-mono text-xl font-bold text-[#E2B671]">
                      {progress.in_progress_plan_credits}
                    </span>
                    <span className="text-[10px] text-[#C6B69C]">ساعة حالية</span>
                  </div>

                  <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-center">
                    <span className="block text-[11px] font-semibold text-[#C6B69C]">ساعات متبقية</span>
                    <span className="mt-1 block font-mono text-xl font-bold text-[#D9884A]">
                      {progress.remaining_plan_credits}
                    </span>
                    <span className="text-[10px] text-[#C6B69C]">ساعة مطلوبة للتخرج</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Requirement Groups Breakdown */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-[#F3E9D8]">مجموعات متطلبات الخطة الدراسية</h2>
                <p className="text-xs text-[#C6B69C]">
                  استيفاء متطلبات التخرج يقتضي إنجاز الساعات المحددة لكل مجموعة بصورة كاملة.
                </p>
              </div>
              <div className="text-xs font-semibold text-[#C6B69C]">
                المستوفاة:{" "}
                <span className="font-mono font-bold text-[#F3E9D8]">
                  {progress.satisfied_requirement_group_count}
                </span>{" "}
                /{" "}
                <span className="font-mono text-[#C6B69C]">
                  {progress.total_requirement_group_count}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
              {progress.requirement_groups.map((group: RequirementGroupProgressResponse) => {
                const groupPercentage =
                  group.required_credits > 0
                    ? Math.min(
                        100,
                        Math.round(
                          (group.credited_toward_requirement / group.required_credits) * 100,
                        ),
                      )
                    : 100;

                return (
                  <div
                    key={group.group_id}
                    className="flex flex-col justify-between rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-xs"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-[#D9884A]" dir="ltr">
                              {group.group_code}
                            </span>
                            <span className="rounded-md bg-[#16362E] px-2 py-0.5 text-[10px] font-semibold text-[#E2B671]">
                              {group.requirement_type === "MANDATORY" || group.requirement_type === "required"
                                ? "إجباري"
                                : "اختياري"}
                            </span>
                          </div>
                          <h3 className="mt-1 truncate text-base font-bold text-[#F3E9D8]">
                            {group.name_ar}
                          </h3>
                        </div>

                        {group.is_satisfied ? (
                          <Badge variant="success">مستوفاة بالكامل</Badge>
                        ) : (
                          <Badge variant="gold">قيد الاستيفاء</Badge>
                        )}
                      </div>

                      <div className="mt-5 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-[#C6B69C]">
                            المحتسب:{" "}
                            <span className="font-mono font-bold text-[#F3E9D8]">
                              {group.credited_toward_requirement}
                            </span>{" "}
                            من أصل{" "}
                            <span className="font-mono font-bold text-[#F3E9D8]">
                              {group.required_credits}
                            </span>{" "}
                            ساعة
                          </span>
                          <span className="font-mono font-bold text-[#D9884A]">
                            {groupPercentage}%
                          </span>
                        </div>
                        <ProgressBar
                          completed={group.credited_toward_requirement}
                          total={group.required_credits}
                          showPercent={false}
                        />
                      </div>
                    </div>

                    <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-[#C9A45C]/20 pt-4 text-xs text-[#C6B69C]">
                      <span className="inline-flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-[#16362E]0" />
                        منجزة: <strong className="font-mono text-[#F3E9D8]">{group.completed_course_count}</strong>
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-amber-500" />
                        قيد الدراسة: <strong className="font-mono text-[#F3E9D8]">{group.in_progress_course_count}</strong>
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-stone-300" />
                        لم تسجل: <strong className="font-mono text-[#F3E9D8]">{group.not_attempted_count}</strong>
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* All Plan Courses Detailed Breakdown */}
          <div className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-bold text-[#F3E9D8]">تفاصيل مواد الخطة الدراسية</h2>
                <p className="text-xs text-[#C6B69C]">
                  قائمة كاملة بمواد الخطة وحالة إنجازها الموثقة في السجل.
                </p>
              </div>

              {/* State Filter Tabs */}
              <div className="flex flex-wrap items-center gap-1 rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-1 text-xs">
                {[
                  { key: "ALL", label: "الكل" },
                  { key: "COMPLETED", label: "المنجزة" },
                  { key: "IN_PROGRESS", label: "قيد الدراسة" },
                  { key: "NOT_ATTEMPTED", label: "لم تبدأ بعد" },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setSelectedStateFilter(tab.key)}
                    className={`rounded-xl px-3 py-1.5 font-semibold transition-colors ${
                      selectedStateFilter === tab.key
                        ? "bg-[#14201B] text-[#E2B671] shadow-xs"
                        : "text-[#C6B69C] hover:text-[#F3E9D8]"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Search Input */}
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#C6B69C]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="ابحث برمز المادة أو رمز المجموعة..."
                className="w-full rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] py-2.5 pr-11 pl-4 text-xs text-[#F3E9D8] placeholder-[#C6B69C]/60 focus:border-[#D9884A] focus:outline-hidden focus:ring-2 focus:ring-[#D9884A]/20"
              />
            </div>

            {/* Course Table */}
            {filteredCourses.length === 0 ? (
              <EmptyState
                title="لا توجد مواد مطابقة"
                description="لم يتم العثور على أي مادة تطابق معايير التصفية والبحث الحالية."
              />
            ) : (
              <div className="overflow-hidden rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] shadow-xs">
                <div className="overflow-x-auto">
                  <table className="w-full text-right text-xs">
                    <thead>
                      <tr className="border-b border-[#C9A45C]/30 bg-[#0F1A17]/70 text-[#C6B69C]">
                        <th className="px-6 py-4 font-bold">رمز المادة</th>
                        <th className="px-6 py-4 font-bold">الساعات المعتمدة</th>
                        <th className="px-6 py-4 font-bold">المجموعة التابعة</th>
                        <th className="px-6 py-4 font-bold">الحالة الأكاديمية</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#C9A45C]/10">
                      {filteredCourses.map((c: CourseProgressResponse) => {
                        const status = getCourseStateLabel(c.state);
                        return (
                          <tr key={c.course_code} className="hover:bg-[#192720] transition-colors">
                            <td className="px-6 py-4 text-[#F3E9D8]">
                              <CourseIdentity courseCode={c.course_code} nameAr={c.course_name_ar} nameEn={c.course_name_en} />
                            </td>
                            <td className="px-6 py-4 font-mono text-[#F3E9D8]">
                              {c.credit_hours} ساعة
                            </td>
                            <td className="px-6 py-4">
                              <span className="font-mono text-xs font-semibold text-[#C6B69C]" dir="ltr">
                                {c.requirement_group_code ?? "—"}
                              </span>
                            </td>
                            <td className="px-6 py-4">
                              <Badge variant={status.variant}>{status.label}</Badge>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
