"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { CourseIdentity, CourseOptions } from "@/components/academic/CourseIdentity";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import type {
  AttemptCreateRequest,
  AttemptOutcome,
  AttemptUpdateRequest,
  CourseAttemptResponse,
  DashboardError,
  RecordSource,
} from "@/lib/api/student-types";
import { Badge, type BadgeVariant } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorAlert, isRetryableError } from "@/components/ui/ErrorAlert";
import { LoadingSkeletonCard } from "@/components/ui/LoadingSkeleton";
import { StatCard } from "@/components/ui/StatCard";
import {
  CheckCircleIcon,
  CloseIcon,
  CoursesIcon,
  EditIcon,
  PlusIcon,
  SearchIcon,
  TrashIcon,
} from "@/components/ui/Icons";

function getStatusDetails(status: AttemptOutcome): { label: string; variant: BadgeVariant } {
  switch (status) {
    case "PASSED":
      return { label: "ناجح / مستوفى", variant: "success" };
    case "IN_PROGRESS":
      return { label: "قيد الدراسة", variant: "gold" };
    case "FAILED":
      return { label: "غير مجتاز", variant: "error" };
    case "WITHDRAWN":
      return { label: "منسحب رسمياً", variant: "warning" };
    default:
      return { label: status, variant: "neutral" };
  }
}

function getSourceLabel(source: RecordSource): string {
  switch (source) {
    case "university_integration":
      return "ربط جامعي رسمي";
    case "transcript_import":
      return "استيراد كشف علامات";
    case "admin_correction":
      return "تدقيق وتصحيح إداري";
    case "manual_entry":
    default:
      return "إدخال يدوي";
  }
}

export default function CoursesPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const identities = useCourseIdentities(auth.isAuthenticated);
  const [attempts, setAttempts] = useState<CourseAttemptResponse[]>([]);
  const [error, setError] = useState<DashboardError | null>(null);
  const [loading, setLoading] = useState(true);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>("ALL");

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingAttempt, setEditingAttempt] = useState<CourseAttemptResponse | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Form states for Add / Edit
  const [formCourseCode, setFormCourseCode] = useState("");
  const [formTermLabel, setFormTermLabel] = useState("");
  const [formStatus, setFormStatus] = useState<AttemptOutcome>("PASSED");
  const [formGrade, setFormGrade] = useState("");
  const [formSource, setFormSource] = useState<RecordSource>("manual_entry");

  const fetchAttempts = async () => {
    setLoading(true);
    setError(null);
    try {
      const api = new StudentApiService(client);
      const data = await api.listAttempts();
      setAttempts(data);
    } catch {
      setError("SERVER_ERROR");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (auth.isAuthenticated) {
      void fetchAttempts();
    }
  }, [auth.isAuthenticated]);

  const openAddModal = () => {
    setFormCourseCode("");
    setFormTermLabel("2024-1");
    setFormStatus("PASSED");
    setFormGrade("");
    setFormSource("manual_entry");
    setActionError(null);
    setIsAddModalOpen(true);
  };

  const openEditModal = (attempt: CourseAttemptResponse) => {
    setEditingAttempt(attempt);
    setFormStatus(attempt.status);
    setFormGrade(attempt.raw_grade_text ?? "");
    setFormTermLabel(attempt.term_label ?? "");
    setActionError(null);
  };

  const handleCreateAttempt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formCourseCode.trim()) {
      setActionError("يرجى إدخال رمز المادة.");
      return;
    }

    setActionLoading(true);
    setActionError(null);
    try {
      const api = new StudentApiService(client);
      const req: AttemptCreateRequest = {
        course_code: formCourseCode.trim().toUpperCase(),
        status: formStatus,
        term_label: formTermLabel.trim() || null,
        raw_grade_text: formGrade.trim() || null,
        record_source: formSource,
      };
      await api.createAttempt(req);
      setIsAddModalOpen(false);
      await fetchAttempts();
    } catch {
      setActionError("تعذر حفظ المحاولة. تأكد من صحة البيانات وعدم تكرار القيد.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateAttempt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAttempt) return;

    setActionLoading(true);
    setActionError(null);
    try {
      const api = new StudentApiService(client);
      const req: AttemptUpdateRequest = {
        status: formStatus,
        term_label: formTermLabel.trim() || null,
        raw_grade_text: formGrade.trim() || null,
      };
      await api.updateAttempt(editingAttempt.id, req);
      setEditingAttempt(null);
      await fetchAttempts();
    } catch {
      setActionError("تعذر تحديث المحاولة. يرجى المحاولة لاحقاً.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteAttempt = async (id: string) => {
    if (!confirm("هل أنت متأكد من رغبتك في حذف هذا القيد؟")) return;
    setDeletingId(id);
    try {
      const api = new StudentApiService(client);
      await api.deleteAttempt(id);
      await fetchAttempts();
    } catch {
      alert("تعذر حذف المحاولة.");
    } finally {
      setDeletingId(null);
    }
  };

  // Stats calculation
  const stats = useMemo(() => {
    const total = attempts.length;
    const passed = attempts.filter((a) => a.status === "PASSED").length;
    const inProgress = attempts.filter((a) => a.status === "IN_PROGRESS").length;
    const notCompleted = attempts.filter((a) => a.status === "FAILED" || a.status === "WITHDRAWN").length;
    return { total, passed, inProgress, notCompleted };
  }, [attempts]);

  // Filtered list
  const filteredAttempts = useMemo(() => {
    return attempts.filter((attempt) => {
      const matchesStatus =
        selectedStatusFilter === "ALL" || attempt.status === selectedStatusFilter;
      const matchesSearch =
        searchQuery.trim() === "" ||
        attempt.course_code.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
        (attempt.term_label && attempt.term_label.toLowerCase().includes(searchQuery.trim().toLowerCase()));
      return matchesStatus && matchesSearch;
    });
  }, [attempts, selectedStatusFilter, searchQuery]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 border-b border-[#C9A45C]/30 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">
              سجل المحاولات
            </span>
            <span className="text-xs text-[#C6B69C]">السجل الأكاديمي</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#F3E9D8]">
            المواد وسجل المحاولات
          </h1>
          <p className="text-xs text-[#C6B69C]">
            استعراض وتوثيق كافة المحاولات الدراسية وحساب المتطلبات السابقة للمواد.
          </p>
        </div>

        <button
          type="button"
          onClick={openAddModal}
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#D9884A] px-5 py-2.5 text-xs font-bold text-[#F3E9D8] shadow-xs hover:bg-[#0E5A4F] hover:text-white transition-all focus:outline-hidden focus:ring-2 focus:ring-[#D9884A]/50"
        >
          <PlusIcon className="h-4 w-4" />
          <span>إضافة محاولة دراسية</span>
        </button>
      </div>

      {/* Error State */}
      {error ? (
        <ErrorAlert
          error={error}
          onRetry={isRetryableError(error) ? fetchAttempts : undefined}
        />
      ) : null}

      {/* Loading Skeleton */}
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
      {!loading && !error ? (
        <div className="space-y-6">
          {/* Summary Stat Cards */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              title="إجمالي المحاولات"
              value={stats.total}
              subtitle="سجل المحاولات التراكمي"
              icon={<CoursesIcon className="h-5 w-5" />}
            />
            <StatCard
              title="المواد المجتازة"
              value={stats.passed}
              subtitle="تم استيفاء متطلباتها بنجاح"
              icon={<CheckCircleIcon className="h-5 w-5" />}
            />
            <StatCard
              title="قيد الدراسة حالياً"
              value={stats.inProgress}
              subtitle="مسجلة في الفصل الجاري"
              icon={<CoursesIcon className="h-5 w-5" />}
            />
            <StatCard
              title="محاولات غير مكتملة"
              value={stats.notCompleted}
              subtitle="رسوب أو انسحاب رسمي"
              icon={<CoursesIcon className="h-5 w-5" />}
            />
          </div>

          {/* Search and Filters */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-1 rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-1 text-xs">
              {[
                { key: "ALL", label: "كافة المحاولات" },
                { key: "PASSED", label: "ناجح" },
                { key: "IN_PROGRESS", label: "قيد الدراسة" },
                { key: "FAILED", label: "راسب" },
                { key: "WITHDRAWN", label: "منسحب" },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setSelectedStatusFilter(tab.key)}
                  className={`rounded-xl px-3 py-1.5 font-semibold transition-colors ${
                    selectedStatusFilter === tab.key
                      ? "bg-[#14201B] text-[#E2B671] shadow-xs"
                      : "text-[#C6B69C] hover:text-[#F3E9D8]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="relative min-w-[240px]">
              <SearchIcon className="pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#C6B69C]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="بحث برمز المادة أو الفصل..."
                className="w-full rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] py-2 pr-11 pl-4 text-xs text-[#F3E9D8] placeholder-[#C6B69C]/60 focus:border-[#D9884A] focus:outline-hidden focus:ring-2 focus:ring-[#D9884A]/20"
              />
            </div>
          </div>

          {/* Attempts Table */}
          {filteredAttempts.length === 0 ? (
            <EmptyState
              title="لا توجد محاولات مسجلة"
              description="لم يتم العثور على أي محاولة دراسية مسجلة تطابق التصفية الحالية. يمكنك إضافة مادة جديدة من الزر أعلاه."
              action={
                <button
                  type="button"
                  onClick={openAddModal}
                  className="rounded-xl bg-[#D9884A] px-4 py-2 text-xs font-bold text-[#F3E9D8] hover:bg-[#0E5A4F] hover:text-white transition-colors"
                >
                  إضافة محاولة دراسية
                </button>
              }
            />
          ) : (
            <div className="overflow-hidden rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] shadow-xs">
              <div className="overflow-x-auto">
                <table className="w-full text-right text-xs">
                  <thead>
                    <tr className="border-b border-[#C9A45C]/30 bg-[#0F1A17]/70 text-[#C6B69C]">
                      <th className="px-6 py-4 font-bold">رمز المادة</th>
                      <th className="px-6 py-4 font-bold">الفصل الدراسي</th>
                      <th className="px-6 py-4 font-bold">العلامة</th>
                      <th className="px-6 py-4 font-bold">الحالة الأكاديمية</th>
                      <th className="px-6 py-4 font-bold">مصدر القيد</th>
                      <th className="px-6 py-4 font-bold text-center">الإجراءات</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#C9A45C]/10">
                    {filteredAttempts.map((attempt) => {
                      const statusDetails = getStatusDetails(attempt.status);
                      return (
                        <tr key={attempt.id} className="hover:bg-[#192720] transition-colors">
                          <td className="px-6 py-4 text-[#F3E9D8]">
                            <CourseIdentity courseCode={attempt.course_code} nameAr={attempt.course_name_ar} nameEn={attempt.course_name_en} />
                          </td>
                          <td className="px-6 py-4 font-mono text-[#C6B69C]" dir="ltr">
                            {attempt.term_label ?? "—"}
                          </td>
                          <td className="px-6 py-4 font-mono font-bold text-[#F3E9D8]">
                            {attempt.raw_grade_text ?? "—"}
                          </td>
                          <td className="px-6 py-4">
                            <Badge variant={statusDetails.variant}>
                              {statusDetails.label}
                            </Badge>
                          </td>
                          <td className="px-6 py-4 text-[#C6B69C]">
                            <span className="rounded-md bg-[#0F1A17] px-2 py-0.5 text-[10px] border border-[#C9A45C]/30">
                              {getSourceLabel(attempt.record_source)}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-center">
                            <div className="flex items-center justify-center gap-2">
                              <button
                                type="button"
                                onClick={() => openEditModal(attempt)}
                                className="rounded-lg p-1.5 text-[#C6B69C] hover:bg-[#16362E] hover:text-[#E2B671] transition-colors"
                                title="تعديل المحاولة"
                              >
                                <EditIcon className="h-4 w-4" />
                              </button>
                              <button
                                type="button"
                                onClick={() => void handleDeleteAttempt(attempt.id)}
                                disabled={deletingId === attempt.id}
                                className="rounded-lg p-1.5 text-stone-400 hover:bg-[#351B17] hover:text-[#F07869] transition-colors disabled:opacity-50"
                                title="حذف المحاولة"
                              >
                                <TrashIcon className="h-4 w-4" />
                              </button>
                            </div>
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
      ) : null}

      {/* Add Modal */}
      {isAddModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xl">
            <div className="flex items-center justify-between border-b border-[#C9A45C]/30 pb-4">
              <h2 className="text-base font-bold text-[#F3E9D8]">إضافة محاولة دراسية جديدة</h2>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="rounded-lg p-1 text-[#C6B69C] hover:bg-[#0F1A17]"
              >
                <CloseIcon className="h-5 w-5" />
              </button>
            </div>

            {actionError ? (
              <div className="mt-4 rounded-xl border border-[#F07869]/40 bg-[#351B17] p-3 text-xs text-[#F07869]">
                {actionError}
              </div>
            ) : null}

            <form onSubmit={handleCreateAttempt} className="mt-4 space-y-4 text-xs">
              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  رمز المادة (Course Code) *
                </label>
                <input
                  type="text"
                  required
                  placeholder="مثال: CS101 أو MATH101"
                  value={formCourseCode}
                  list="attempt-course-identities"
                  onChange={(e) => setFormCourseCode(e.target.value.toUpperCase())}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 font-mono uppercase text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                  dir="ltr"
                />
                <CourseOptions id="attempt-course-identities" identities={identities} />
                {formCourseCode && <CourseIdentity courseCode={formCourseCode} identities={identities} />}
              </div>

              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  الفصل الدراسي (Term Label)
                </label>
                <input
                  type="text"
                  placeholder="مثال: 2024-1 أو 2023-2"
                  value={formTermLabel}
                  onChange={(e) => setFormTermLabel(e.target.value)}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 font-mono text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                  dir="ltr"
                />
              </div>

              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  الحالة الأكاديمية *
                </label>
                <select
                  value={formStatus}
                  onChange={(e) => setFormStatus(e.target.value as AttemptOutcome)}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                >
                  <option value="PASSED">ناجح / مستوفى (PASSED)</option>
                  <option value="IN_PROGRESS">قيد الدراسة (IN_PROGRESS)</option>
                  <option value="FAILED">راسب (FAILED)</option>
                  <option value="WITHDRAWN">منسحب (WITHDRAWN)</option>
                </select>
              </div>

              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  العلامة المسجلة (اختياري)
                </label>
                <input
                  type="text"
                  placeholder="مثال: A أو 85 أو Pass"
                  value={formGrade}
                  onChange={(e) => setFormGrade(e.target.value)}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 font-mono text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  مصدر القيد
                </label>
                <select
                  value={formSource}
                  onChange={(e) => setFormSource(e.target.value as RecordSource)}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                >
                  <option value="manual_entry">إدخال يدوي للطالب</option>
                  <option value="transcript_import">استيراد كشف علامات</option>
                  <option value="university_integration">ربط جامعي</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-[#C9A45C]/30">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="rounded-xl border border-[#C9A45C]/30 px-4 py-2 font-bold text-[#C6B69C] hover:bg-[#0F1A17]"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="rounded-xl bg-[#D9884A] px-5 py-2 font-bold text-[#F3E9D8] hover:bg-[#0E5A4F] hover:text-white transition-all disabled:opacity-50"
                >
                  {actionLoading ? "جاري الحفظ..." : "حفظ المحاولة"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {/* Edit Modal */}
      {editingAttempt ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xl">
            <div className="flex items-center justify-between border-b border-[#C9A45C]/30 pb-4">
              <div>
                <h2 className="text-base font-bold text-[#F3E9D8]">تعديل المحاولة الدراسية</h2>
                <p className="font-mono text-xs text-[#D9884A] font-bold" dir="ltr">
                  <CourseIdentity courseCode={editingAttempt.course_code} nameAr={editingAttempt.course_name_ar} nameEn={editingAttempt.course_name_en} /> {editingAttempt.term_label ? `(${editingAttempt.term_label})` : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingAttempt(null)}
                className="rounded-lg p-1 text-[#C6B69C] hover:bg-[#0F1A17]"
              >
                <CloseIcon className="h-5 w-5" />
              </button>
            </div>

            {actionError ? (
              <div className="mt-4 rounded-xl border border-[#F07869]/40 bg-[#351B17] p-3 text-xs text-[#F07869]">
                {actionError}
              </div>
            ) : null}

            <form onSubmit={handleUpdateAttempt} className="mt-4 space-y-4 text-xs">
              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  الفصل الدراسي (Term Label)
                </label>
                <input
                  type="text"
                  value={formTermLabel}
                  onChange={(e) => setFormTermLabel(e.target.value)}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 font-mono text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                  dir="ltr"
                />
              </div>

              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  الحالة الأكاديمية *
                </label>
                <select
                  value={formStatus}
                  onChange={(e) => setFormStatus(e.target.value as AttemptOutcome)}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                >
                  <option value="PASSED">ناجح / مستوفى (PASSED)</option>
                  <option value="IN_PROGRESS">قيد الدراسة (IN_PROGRESS)</option>
                  <option value="FAILED">راسب (FAILED)</option>
                  <option value="WITHDRAWN">منسحب (WITHDRAWN)</option>
                </select>
              </div>

              <div>
                <label className="block font-bold text-[#F3E9D8] mb-1">
                  العلامة المسجلة
                </label>
                <input
                  type="text"
                  placeholder="مثال: A أو 85 أو Pass"
                  value={formGrade}
                  onChange={(e) => setFormGrade(e.target.value)}
                  className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 font-mono text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-[#C9A45C]/30">
                <button
                  type="button"
                  onClick={() => setEditingAttempt(null)}
                  className="rounded-xl border border-[#C9A45C]/30 px-4 py-2 font-bold text-[#C6B69C] hover:bg-[#0F1A17]"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="rounded-xl bg-[#D9884A] px-5 py-2 font-bold text-[#F3E9D8] hover:bg-[#0E5A4F] hover:text-white transition-all disabled:opacity-50"
                >
                  {actionLoading ? "جاري الحفظ..." : "تحديث المحاولة"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
