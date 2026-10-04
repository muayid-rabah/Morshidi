"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { CourseDifficulty } from "@/components/academic/CourseDifficulty";
import { CourseIdentity, CourseReferences } from "@/components/academic/CourseIdentity";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import type { AcademicRoadmapResponse, AdaptiveCourseResponse, RoadmapCourse, RoadmapState } from "@/lib/api/student-types";

type Locale = "ar" | "en";
const STATES: RoadmapState[] = ["COMPLETED", "IN_PROGRESS", "ELIGIBLE", "BLOCKED", "PLANNED", "REVIEW_REQUIRED"];
const LABELS: Record<RoadmapState, { ar: string; en: string }> = {
  COMPLETED: { ar: "منجزة", en: "Completed" },
  IN_PROGRESS: { ar: "قيد الدراسة", en: "In progress" },
  ELIGIBLE: { ar: "متاحة وفق المتطلبات", en: "Prerequisites met" },
  BLOCKED: { ar: "مقيّدة بمتطلبات", en: "Prerequisites missing" },
  PLANNED: { ar: "مخططة — نمذجة", en: "Planned — modeled" },
  REVIEW_REQUIRED: { ar: "تحتاج مراجعة", en: "Review required" },
};
const COPY = {
  ar: { title: "خارطتي الأكاديمية", intro: "عرض مُنمذج من سجلّك وخطتك. الأهلية الحتمية لا تؤكد الطرح أو التسجيل.",
    report: "عرض التقرير غير الرسمي", loading: "جارٍ تحميل الخارطة الأكاديمية", error: "تعذّر تحميل الخارطة.", retry: "إعادة المحاولة",
    empty: "لا توجد مواد في هذه الخطة أو لا توجد نتائج مطابقة.", all: "جميع الحالات", search: "ابحث برمز المادة أو اسمها",
    details: "تفاصيل المادة", select: "اختر مادة لعرض تفاصيلها.", credits: "ساعات", group: "مجموعة المتطلبات",
    missing: "المتطلبات غير المستوفاة", impact: "تأثير بنيوي مباشر", impactNote: "ليس تقديراً مضموناً لتأخر التخرج.",
    semester: "الفصل المُنمذج", generated: "تاريخ العرض", version: "رقم الخطة / سنة السريان", list: "قائمة المواد القابلة للتنقل بلوحة المفاتيح",
    noVersion: "غير متاح", legend: "دليل الحالات", next: "المتاح الآن", blocked: "المقيّدة", critical: "ذات تأثير بنيوي",
    source: "تاريخ تحديث مصدر الخطة", review: "بيانات المتطلبات تحتاج مراجعة بشرية.", noMissing: "لا توجد مجموعة متطلبات ناقصة مثبتة.",
  },
  en: { title: "My academic roadmap", intro: "Modeled from your record and study plan. Deterministic eligibility does not confirm offering or registration.",
    report: "View unofficial report", loading: "Loading academic roadmap", error: "Could not load the roadmap.", retry: "Try again",
    empty: "No plan courses or matching results.", all: "All states", search: "Search course code or name",
    details: "Course details", select: "Select a course to view its details.", credits: "Credits", group: "Requirement group",
    missing: "Unmet prerequisites", impact: "Direct structural impact", impactNote: "This is not a guaranteed graduation delay estimate.",
    semester: "Modeled semester", generated: "Generated", version: "Plan number / effective year", list: "Keyboard-accessible course list",
    noVersion: "Unavailable", legend: "State legend", next: "Available next", blocked: "Blocked", critical: "Structurally important",
    source: "Plan source updated", review: "Prerequisite data needs human review.", noMissing: "No verified missing prerequisite group.",
  },
};

function formatDate(value: string | null, locale: Locale): string {
  if (!value) return COPY[locale].noVersion;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? COPY[locale].noVersion : new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function RoadmapPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const [data, setData] = useState<AcademicRoadmapResponse | null>(null);
  const identities = useCourseIdentities(Boolean(data));
  const [adaptive, setAdaptive] = useState<AdaptiveCourseResponse | null>(null);
  const [locale, setLocale] = useState<Locale>("ar");
  const [filter, setFilter] = useState<RoadmapState | "ALL" | "CRITICAL">("ALL");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [modeling, setModeling] = useState(false);
  const [modelError, setModelError] = useState(false);
  const copy = COPY[locale];
  const load = useCallback(async () => {
    setLoading(true); setError(false);
    try {
      const api = new StudentApiService(client);
      const [roadmap, intelligence] = await Promise.all([
        api.getRoadmap(), api.getAdaptiveCourseIntelligence().catch(() => null),
      ]);
      setData(roadmap); setAdaptive(intelligence);
    }
    catch { setError(true); setData(null); }
    finally { setLoading(false); }
  }, [client]);
  useEffect(() => {
    let active = true;
    if (auth.isAuthenticated) void Promise.resolve().then(() => { if (active) return load(); });
    return () => { active = false; };
  }, [auth.isAuthenticated, load]);
  const generatePath = useCallback(async () => {
    setModeling(true); setModelError(false);
    try {
      const modeled = await new StudentApiService(client).generateModeledRoadmap(
        { max_credit_hours_per_semester: 18, max_semesters_ahead: 8, max_paths: 1 },
        AbortSignal.timeout(60_000),
      );
      setData(modeled);
    } catch { setModelError(true); }
    finally { setModeling(false); }
  }, [client]);
  const courses = useMemo(() => data?.courses.filter((course) =>
    (filter === "ALL" || (filter === "CRITICAL" ? course.critical_path : course.state === filter)) &&
    `${course.course_code} ${course.name_ar} ${course.name_en ?? ""}`.toLowerCase().includes(query.trim().toLowerCase())) ?? [],
  [data, filter, query]);
  const detail = data?.courses.find((course) => course.course_code === selected) ?? null;
  const difficultyByCode = useMemo(() => new Map(adaptive?.courses.map((course) => [course.course_code, course]) ?? []), [adaptive]);
  const count = (state: RoadmapState) => data?.courses.filter((course) => course.state === state).length ?? 0;

  return <section lang={locale} dir={locale === "ar" ? "rtl" : "ltr"} className="space-y-6">
    <header className="rounded-3xl border border-[#C9A45C]/30 bg-[#0F1A17] p-5 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-sm font-semibold text-[#E2B671]">Morshidi · WC-006</p><h1 className="mt-2 text-3xl font-bold">{copy.title}</h1><p className="mt-2 max-w-3xl text-sm leading-7">{copy.intro}</p></div>
        <button type="button" onClick={() => setLocale(locale === "ar" ? "en" : "ar")} className="rounded-xl border border-[#14796B] px-4 py-2 text-sm font-bold" aria-label={locale === "ar" ? "Switch to English" : "التبديل إلى العربية"}>{locale === "ar" ? "English" : "العربية"}</button>
      </div>
      <Link href="/student/report" className="mt-5 inline-flex rounded-xl bg-[#14796B] px-4 py-2 text-sm font-semibold text-white">{copy.report}</Link>
    </header>
    {loading && <p role="status" aria-live="polite">{copy.loading}</p>}
    {error && <div role="alert" className="rounded-xl border border-[#F07869]/50 p-4"><p>{copy.error}</p><button type="button" onClick={() => void load()} className="mt-2 underline">{copy.retry}</button></div>}
    {data && !loading && <>
      <div className="rounded-xl border border-[#C9A45C]/30 p-4">
        <p>{data.modeling_status === "NOT_REQUESTED" ? (locale === "ar" ? "لم تُنشأ خطة دراسية مُنمذجة بعد؛ لا تظهر مواد مخططة حتى تطلب إنشاءها." : "No modeled path has been generated; planned courses are absent until you request one.") : data.modeling_status === "NO_VALID_PATH" ? (locale === "ar" ? "لم يُعثر على مسار مُنمذج صالح ضمن الحدود المختارة." : "No valid modeled path was found within the selected limits.") : (locale === "ar" ? "المواد المخططة تقدير مُنمذج وليست تسجيلاً أو جدولاً رسمياً." : "Planned courses are modeled, not registered or officially scheduled.")}</p>
        <button type="button" disabled={modeling} onClick={() => void generatePath()} className="mt-3 rounded-xl bg-[#14796B] px-4 py-2 font-semibold text-white disabled:opacity-60">{modeling ? (locale === "ar" ? "جارٍ إنشاء المسار المُنمذج…" : "Generating modeled path…") : (locale === "ar" ? "إنشاء مسار دراسي مُنمذج" : "Generate modeled path")}</button>
        {modeling && <p role="status" aria-live="polite">{locale === "ar" ? "جارٍ حساب المسار؛ قد يستغرق حتى دقيقة واحدة." : "Calculating the path; this may take up to one minute."}</p>}
        {modelError && <p role="alert" className="mt-2">{locale === "ar" ? "تعذر إنشاء المسار أو انتهت المهلة. لا تزال الخارطة الأساسية متاحة؛ يمكنك المحاولة لاحقاً." : "The path could not be generated or timed out. The base roadmap remains available; try again later."}</p>}
      </div>
      <div className="grid gap-3 sm:grid-cols-3" aria-label={copy.legend}>
        <div className="rounded-2xl border border-[#C9A45C]/30 p-4"><strong>{count("COMPLETED")}</strong> {LABELS.COMPLETED[locale]}</div>
        <div className="rounded-2xl border border-[#C9A45C]/30 p-4"><strong>{count("IN_PROGRESS")}</strong> {LABELS.IN_PROGRESS[locale]}</div>
        <div className="rounded-2xl border border-[#C9A45C]/30 p-4"><strong>{count("ELIGIBLE")}</strong> {LABELS.ELIGIBLE[locale]}</div>
      </div>
      <dl className="flex flex-wrap gap-x-8 gap-y-2 text-xs"><div><dt className="font-bold">{copy.version}</dt><dd><bdi>{data.plan_number ?? copy.noVersion}</bdi> / {data.effective_year ?? copy.noVersion}</dd></div><div><dt className="font-bold">{copy.source}</dt><dd>{formatDate(data.plan_updated_at, locale)}</dd></div><div><dt className="font-bold">{copy.generated}</dt><dd>{formatDate(data.generated_at, locale)}</dd></div></dl>
      <div className="flex flex-wrap gap-2" role="group" aria-label={copy.legend}>
        {(["ALL", ...STATES, "CRITICAL"] as const).map((state) => <button key={state} type="button" aria-pressed={filter === state} onClick={() => setFilter(state)} className={`rounded-full border px-3 py-2 text-xs font-semibold ${filter === state ? "border-[#14796B] bg-[#16362E]" : "border-[#C9A45C]/30"}`}>{state === "ALL" ? copy.all : state === "CRITICAL" ? copy.critical : `${LABELS[state][locale]} (${count(state)})`}</button>)}
      </div>
      <label className="block max-w-xl text-sm font-semibold">{copy.search}<input value={query} onChange={(event) => setQuery(event.target.value)} type="search" className="mt-2 block w-full rounded-xl border border-[#8B806B] bg-[#14201B] p-3" /></label>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,22rem)]">
        <section aria-label={copy.list} className="grid max-h-[70vh] gap-3 overflow-y-auto rounded-2xl border border-[#C9A45C]/30 p-3 sm:grid-cols-2">
          {courses.length === 0 && <p className="p-4">{copy.empty}</p>}
          {courses.map((course: RoadmapCourse) => <button key={course.course_code} type="button" aria-pressed={selected === course.course_code} onClick={() => setSelected(course.course_code)} className="rounded-xl border border-[#CBBE9E] bg-[#14201B] p-4 text-start focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#14796B]">
            <CourseIdentity courseCode={course.course_code} nameAr={course.name_ar} nameEn={course.name_en} locale={locale} /><span className="mt-2 block text-xs">{LABELS[course.state][locale]}{course.critical_path ? ` · ${copy.critical}` : ""}{course.planned_semester ? ` · ${copy.semester} ${course.planned_semester}` : ""}</span>
            <CourseDifficulty course={difficultyByCode.get(course.course_code)} locale={locale} />
          </button>)}
        </section>
        <aside aria-label={copy.details} aria-live="polite" className="rounded-2xl border border-[#C9A45C]/30 bg-[#192720] p-5 lg:sticky lg:top-20">
          <h2 className="text-lg font-bold">{copy.details}</h2>{!detail && <p className="mt-3 text-sm">{copy.select}</p>}
          {detail && <><h3 className="mt-3 text-xl font-bold"><CourseIdentity courseCode={detail.course_code} nameAr={detail.name_ar} nameEn={detail.name_en} locale={locale} /></h3>
            <p className="mt-3 font-semibold">{LABELS[detail.state][locale]}</p><CourseDifficulty course={difficultyByCode.get(detail.course_code)} locale={locale} /><dl className="mt-3 space-y-2 text-sm"><div><dt>{copy.credits}</dt><dd>{detail.credit_hours}</dd></div><div><dt>{copy.group}</dt><dd><bdi>{detail.requirement_group_code}</bdi></dd></div>{detail.planned_semester && <div><dt>{copy.semester}</dt><dd>{detail.planned_semester} · {locale === "ar" ? "الترتيب" : "order"} {detail.planned_order}</dd></div>}</dl>
            <h4 className="mt-4 font-bold">{copy.missing}</h4>{detail.missing_prerequisite_groups.length ? <ul className="mt-1 list-inside list-disc text-sm">{detail.missing_prerequisite_groups.map((group, index) => <li key={index}>{group.map((code, option) => <span key={code}>{option > 0 ? (locale === "ar" ? " أو " : " OR ") : ""}<CourseIdentity courseCode={code} identities={identities} locale={locale} compact /></span>)}</li>)}</ul> : <p className="text-sm">{copy.noMissing}</p>}
            {detail.state === "REVIEW_REQUIRED" && <p className="mt-3 text-sm">{copy.review}</p>}
            {detail.structural_criticality && <p className="mt-3 text-sm">{copy.impact}: {detail.structural_impact_count}. {copy.impactNote}</p>}
            {detail.critical_path && <div className="mt-3 text-sm"><p className="font-semibold">{locale === "ar" ? "مسار حرج بنيوي (غير مضمون زمنياً)" : "Structural critical path (not a time guarantee)"}</p><p>{locale === "ar" ? "عدد روابط المتطلبات في أطول سلسلة" : "Prerequisite edges in longest chain"}: {detail.critical_path_length}</p><p>{locale === "ar" ? "مواد مطلوبة لاحقة متأثرة" : "Affected downstream required courses"}: <CourseReferences codes={detail.critical_path_downstream_codes} identities={identities} locale={locale} /></p><p>{locale === "ar" ? "سلسلة الدليل" : "Evidence chain"}: {detail.critical_path_evidence_chain.map((code, index) => <span key={code}>{index > 0 ? " → " : ""}<CourseIdentity courseCode={code} identities={identities} locale={locale} compact /></span>)}</p><p>{copy.impactNote}</p></div>}
          </>}
        </aside>
      </div>
      <p className="rounded-xl border border-[#C9A45C]/30 p-4 text-xs">{copy.intro}</p>
    </>}
  </section>;
}
