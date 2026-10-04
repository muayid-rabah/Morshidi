"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseIdentity, CourseOptions } from "@/components/academic/CourseIdentity";
import type {
  DashboardError,
  StudentIntentResponse,
  SubmitIntentRequest,
  WithdrawIntentRequest,
} from "@/lib/api/student-types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorAlert, isRetryableError } from "@/components/ui/ErrorAlert";
import { LoadingSkeletonCard } from "@/components/ui/LoadingSkeleton";
import { StatCard } from "@/components/ui/StatCard";
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  CloseIcon,
  CoursesIcon,
  InfoIcon,
  MockRegistrationIcon,
  PlusIcon,
  CompassIcon,
  TrashIcon,
} from "@/components/ui/Icons";

const NOTICE_VERSION = "2026-v1";

export default function MockRegistrationPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const identities = useCourseIdentities(auth.isAuthenticated);

  const [targetPeriod, setTargetPeriod] = useState<string>("");
  const [periods, setPeriods] = useState<Array<{ id: string; code: string; label: string; is_current: boolean }>>([]);
  const [intent, setIntent] = useState<StudentIntentResponse | null>(null);
  const [error, setError] = useState<DashboardError | null>(null);
  const [loading, setLoading] = useState(true);

  // Form states for creating / editing revision
  const [isEditing, setIsEditing] = useState(false);
  const [courseList, setCourseList] = useState<string[]>([]);
  const [newCourseCode, setNewCourseCode] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [agreedTransparency, setAgreedTransparency] = useState(true);

  const fetchCurrentIntent = async (period: string) => {
    setLoading(true);
    setError(null);
    try {
      const api = new StudentApiService(client);
      const data = await api.getCurrentMockRegistration(period);
      setIntent(data);
      if (data && data.lifecycle_status !== "WITHDRAWN") {
        setCourseList(data.course_codes);
      } else {
        setCourseList([]);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.message === "NOT_FOUND") {
        setIntent(null);
        setCourseList([]);
      } else {
        setError("SERVER_ERROR");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (auth.isAuthenticated) {
      const api = new StudentApiService(client);
      void api.getAcademicPeriods().then((items) => {
        setPeriods(items);
        const current = items.find((period) => period.is_current) ?? items[0];
        if (current) setTargetPeriod(current.id);
        else { setError("SERVICE_UNAVAILABLE"); setLoading(false); }
      }).catch(() => { setError("SERVICE_UNAVAILABLE"); setLoading(false); });
    }
  }, [auth.isAuthenticated, client]);

  useEffect(() => {
    if (auth.isAuthenticated && targetPeriod) void fetchCurrentIntent(targetPeriod);
  }, [auth.isAuthenticated, targetPeriod]);

  const handleAddCourse = (e: React.FormEvent) => {
    e.preventDefault();
    const code = newCourseCode.trim().toUpperCase();
    if (!code) return;
    if (courseList.includes(code)) {
      setActionError("المادة مضافة بالفعل في قائمة الرغبات.");
      return;
    }
    setCourseList((prev) => [...prev, code]);
    setNewCourseCode("");
    setActionError(null);
  };

  const handleRemoveCourse = (code: string) => {
    setCourseList((prev) => prev.filter((c) => c !== code));
  };

  const handleSubmitRevision = async () => {
    if (courseList.length === 0) {
      setActionError("يرجى إضافة مادة واحدة على الأقل في رغبة التسجيل.");
      return;
    }
    if (!agreedTransparency) {
      setActionError("يجب الموافقة على إقرار الشفافية بأن التسجيل تجريبي وغير ملزم.");
      return;
    }

    setActionLoading(true);
    setActionError(null);
    try {
      const api = new StudentApiService(client);
      const req: SubmitIntentRequest = {
        target_period_id: targetPeriod,
        course_codes: courseList,
        expected_current_revision: intent?.revision ?? null,
        transparency_notice_version: NOTICE_VERSION,
      };
      const res = await api.submitMockRegistration(req);
      setIntent(res);
      setIsEditing(false);
    } catch {
      setActionError("تعذر حفظ رغبة التسجيل التجريبي. يرجى المحاولة مرة أخرى.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleWithdrawIntent = async () => {
    if (!intent) return;
    if (!confirm("هل أنت متأكد من رغبتك في سحب رغبة التسجيل التجريبي لهذا الفصل؟")) return;

    setActionLoading(true);
    setActionError(null);
    try {
      const api = new StudentApiService(client);
      const req: WithdrawIntentRequest = {
        target_period_id: targetPeriod,
        expected_current_revision: intent.revision,
        transparency_notice_version: NOTICE_VERSION,
      };
      const res = await api.withdrawMockRegistration(req);
      setIntent(res);
      setIsEditing(false);
      setCourseList([]);
    } catch {
      alert("تعذر سحب الرغبة. يرجى المحاولة لاحقاً.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-2 border-b border-[#C9A45C]/30 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">
              التسجيل التجريبي الذكي
            </span>
            <span className="text-xs text-[#C6B69C]">رغبات تسجيل غير ملزمة</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#F3E9D8]">
            التسجيل التجريبي والمحاكاة
          </h1>
          <p className="text-xs text-[#C6B69C]">
            حصر مبكر لرغبات تسجيل المواد لمساعدة قسمك الأكاديمي في تخطيط وتوزيع الشعب الدراسية.
          </p>
        </div>

        {/* Period Selector */}
        <div className="flex items-center gap-2 text-xs">
          <span className="font-bold text-[#C6B69C]">الفصل الدراسي المستهدف:</span>
          <select
            value={targetPeriod}
            onChange={(e) => setTargetPeriod(e.target.value)}
            className="rounded-xl border border-[#C9A45C]/30 bg-[#14201B] px-3 py-1.5 font-mono text-xs font-bold text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
            dir="ltr"
          >
            {periods.map((period) => <option key={period.id} value={period.id}>{period.label}</option>)}
          </select>
        </div>
      </div>

      {/* Non-binding Transparency Notice */}
      <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#0F1A17] p-5 text-xs text-[#C6B69C] shadow-xs">
        <div className="flex items-start gap-3">
          <InfoIcon className="h-5 w-5 text-[#D9884A] shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h3 className="font-bold text-[#F3E9D8]">إشعار الشفافية والمسؤولية الأكاديمية:</h3>
            <p className="leading-relaxed">
              هذا التسجيل استطلاعي وتجريبي (Non-binding Mock Registration). لا يُعد تسجيلاً رسمياً، ولا يمنح حقاً مكتسباً في الشعب، ولا تترتب عليه أي التزامات مالية. التسجيل الرسمي يتم حصراً عبر بوابة القبول والتسجيل الرسمية عند فتح فترات التسجيل.
            </p>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error ? (
        <ErrorAlert
          error={error}
          onRetry={isRetryableError(error) ? () => fetchCurrentIntent(targetPeriod) : undefined}
        />
      ) : null}

      {/* Loading Skeleton */}
      {loading ? (
        <div className="space-y-6">
          <LoadingSkeletonCard />
          <LoadingSkeletonCard />
        </div>
      ) : null}

      {/* Content */}
      {!loading && !error ? (
        <div className="space-y-6">
          {/* Active Intent View */}
          {intent && intent.lifecycle_status !== "WITHDRAWN" && !isEditing ? (
            <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xs space-y-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-[#C9A45C]/20 pb-5">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-[#D9884A]" dir="ltr">
                      الفصل {intent.target_period_id}
                    </span>
                    <span className="text-xs text-[#C6B69C]">
                      • المراجعة #{intent.revision}
                    </span>
                  </div>
                  <h2 className="text-lg font-bold text-[#F3E9D8] mt-1">
                    رغبة التسجيل التجريبي المسجلة
                  </h2>
                  <p className="text-xs text-[#C6B69C]">
                    تم توثيق الرغبة بنجاح وإدراجها في حسابات الاحتياج الفصلي.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={intent.lifecycle_status === "SUBMITTED" ? "success" : "gold"}>
                    {intent.lifecycle_status === "SUBMITTED" ? "مرسلة ومعتمدة" : intent.lifecycle_status}
                  </Badge>
                  <Badge
                    variant={
                      intent.submission_validation_status === "VALID"
                        ? "success"
                        : intent.submission_validation_status === "REVIEW_REQUIRED"
                        ? "review"
                        : "error"
                    }
                  >
                    حالة المطابقة: {intent.submission_validation_status}
                  </Badge>
                </div>
              </div>

              {/* Course Badges List */}
              <div className="space-y-2">
                <span className="text-xs font-bold text-[#F3E9D8]">
                  المواد المختارة في هذه الرغبة ({intent.course_codes.length} مواد):
                </span>
                <div className="flex flex-wrap gap-2 pt-1">
                  {intent.course_codes.map((code) => (
                    <span
                      key={code}
                      className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] px-4 py-2 font-mono text-xs font-bold text-[#F3E9D8] shadow-xs"
                      dir="ltr"
                    >
                      <CourseIdentity courseCode={code} identities={identities} />
                    </span>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#C9A45C]/20 pt-5">
                <button
                  type="button"
                  onClick={() => setIsEditing(true)}
                  className="rounded-2xl bg-[#D9884A] px-6 py-2.5 text-xs font-bold text-[#F3E9D8] hover:bg-[#0E5A4F] hover:text-white transition-all shadow-xs"
                >
                  تعديل الرغبات وإرسال مراجعة جديدة
                </button>

                <button
                  type="button"
                  onClick={() => void handleWithdrawIntent()}
                  disabled={actionLoading}
                  className="rounded-2xl border border-[#F07869]/40 bg-[#351B17] px-5 py-2.5 text-xs font-bold text-[#F07869] hover:bg-[#47231D] transition-colors disabled:opacity-50"
                >
                  سحب رغبة التسجيل
                </button>
              </div>
            </div>
          ) : null}

          {/* Form to Create or Edit Intent */}
          {(!intent || intent.lifecycle_status === "WITHDRAWN" || isEditing) ? (
            <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xs space-y-6">
              <div className="border-b border-[#C9A45C]/30 pb-4">
                <h2 className="text-base font-bold text-[#F3E9D8]">
                  {intent && intent.lifecycle_status !== "WITHDRAWN"
                    ? `تعديل رغبة التسجيل (المراجعة القادمة #${intent.revision + 1})`
                    : `تسجيل رغبة فصلية تجريبية جديدة (${targetPeriod})`}
                </h2>
                <p className="text-xs text-[#C6B69C]">
                  أضف رموز المواد التي ترغب في دراستها خلال الفصل القادم.
                </p>
              </div>

              {actionError ? (
                <div className="rounded-xl border border-[#F07869]/40 bg-[#351B17] p-3 text-xs text-[#F07869]">
                  {actionError}
                </div>
              ) : null}

              {/* Add Course Input Form */}
              <form onSubmit={handleAddCourse} className="space-y-2">
                <label className="block text-xs font-bold text-[#F3E9D8]">
                  إضافة مادة إلى قائمة الرغبات:
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newCourseCode}
                    list="registration-course-identities"
                    onChange={(e) => setNewCourseCode(e.target.value.toUpperCase())}
                    placeholder="أدخل رمز المادة (مثل: CS101 أو AI201)..."
                    className="flex-1 rounded-2xl border border-[#C9A45C]/30 bg-[#0B1210] px-4 py-2.5 font-mono text-xs uppercase text-[#F3E9D8] focus:border-[#D9884A] focus:bg-[#14201B] focus:outline-hidden"
                    dir="ltr"
                  />
                  <CourseOptions id="registration-course-identities" identities={identities} />
                  <button
                    type="submit"
                    className="inline-flex items-center gap-1.5 rounded-2xl bg-[#0F1A17] border border-[#C9A45C]/30 px-5 py-2.5 text-xs font-bold text-[#E2B671] hover:bg-[#16362E] hover:border-[#D9884A] transition-all"
                  >
                    <PlusIcon className="h-4 w-4" />
                    <span>إضافة</span>
                  </button>
                </div>
              </form>

              {/* Current List in Draft */}
              <div className="space-y-3">
                <span className="text-xs font-bold text-[#F3E9D8]">
                  المواد المضافة في القائمة الحالية ({courseList.length}):
                </span>
                {courseList.length === 0 ? (
                  <p className="rounded-2xl border border-dashed border-[#C9A45C]/30 p-5 text-center text-xs text-[#C6B69C]">
                    لم تقم بإضافة أي مواد بعد. أضف المواد من الحقل أعلاه.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {courseList.map((code) => (
                      <span
                        key={code}
                        className="inline-flex items-center gap-2 rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] px-3.5 py-1.5 font-mono text-xs font-bold text-[#F3E9D8]"
                        dir="ltr"
                      >
                        <CourseIdentity courseCode={code} identities={identities} />
                        <button
                          type="button"
                          onClick={() => handleRemoveCourse(code)}
                          className="rounded-full p-0.5 text-stone-400 hover:bg-stone-200 hover:text-stone-700 transition-colors"
                        >
                          <CloseIcon className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Transparency Agreement */}
              <div className="rounded-2xl bg-[#0B1210] p-4 border border-[#C9A45C]/20 text-xs text-[#C6B69C]">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={agreedTransparency}
                    onChange={(e) => setAgreedTransparency(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-[#C9A45C]/30 text-[#D9884A] focus:ring-[#D9884A]"
                  />
                  <span>
                    أقر بأن هذا التسجيل تجريبي وغير ملزم ومخصص لأغراض دراسة الاحتياج الفصلي والتخطيط الأكاديمي، ولا يغني عن التسجيل الرسمي.
                  </span>
                </label>
              </div>

              {/* Submit Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-[#C9A45C]/20">
                {isEditing ? (
                  <button
                    type="button"
                    onClick={() => {
                      setIsEditing(false);
                      if (intent) setCourseList(intent.course_codes);
                    }}
                    className="rounded-2xl border border-[#C9A45C]/30 px-5 py-2.5 text-xs font-bold text-[#C6B69C] hover:bg-[#0F1A17]"
                  >
                    إلغاء التعديل
                  </button>
                ) : null}

                <button
                  type="button"
                  onClick={() => void handleSubmitRevision()}
                  disabled={actionLoading || courseList.length === 0}
                  className="rounded-2xl bg-[#D9884A] px-7 py-2.5 text-xs font-bold text-[#F3E9D8] hover:bg-[#0E5A4F] hover:text-white transition-all shadow-xs disabled:opacity-50"
                >
                  {actionLoading ? "جاري الإرسال..." : "إرسال رغبة التسجيل التجريبي"}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
