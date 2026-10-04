"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { CourseIdentity } from "@/components/academic/CourseIdentity";
import type { ModeledAcademicReportResponse, RoadmapState } from "@/lib/api/student-types";

type Locale = "ar" | "en";
const STATES: RoadmapState[] = ["COMPLETED", "IN_PROGRESS", "ELIGIBLE", "BLOCKED", "PLANNED", "REVIEW_REQUIRED"];
const COPY = {
  ar: { title: "تقرير أكاديمي مُنمذج بواسطة مرشدي — غير رسمي", notice: "هذا التقرير ليس كشف علامات أو إفادة تخرج رسمية. يعرض حالة مُنمذجة من بيانات الخطة والسجل المتاحة وقت الإنشاء.",
    print: "طباعة / حفظ PDF", loading: "جارٍ إعداد التقرير", error: "تعذّر إعداد التقرير.", retry: "إعادة المحاولة",
    summary: "ملخص الخطة", plan: "رقم الخطة", year: "سنة السريان", updated: "آخر تحديث للخطة", generated: "تاريخ إنشاء العرض", unavailable: "غير متاح",
    total: "الساعات المطلوبة", completed: "الساعات المنجزة", current: "الساعات قيد الدراسة", remaining: "الساعات المتبقية", courses: "حالات المواد", limitations: "حدود التقرير",
    note: "الأهلية حسب المتطلبات السابقة فقط؛ لا تؤكد توفر الشعبة أو التسجيل. لا يوجد تاريخ تخرج مضمون.",
    states: ["منجزة", "قيد الدراسة", "متاحة وفق المتطلبات", "مقيّدة", "مخططة — نمذجة", "تحتاج مراجعة"],
  },
  en: { title: "Modeled Academic Report by Morshidi — Unofficial", notice: "This is not an official transcript or graduation certificate. It reflects available modeled plan and record data at generation time.",
    print: "Print / save PDF", loading: "Preparing report", error: "Could not prepare report.", retry: "Try again",
    summary: "Plan summary", plan: "Plan number", year: "Effective year", updated: "Plan last updated", generated: "View generated", unavailable: "Unavailable",
    total: "Required credits", completed: "Completed credits", current: "In-progress credits", remaining: "Remaining credits", courses: "Course states", limitations: "Report limitations",
    note: "Eligibility covers prerequisites only, not course offerings or registration. No graduation date is guaranteed.",
    states: ["Completed", "In progress", "Prerequisites met", "Blocked", "Planned — modeled", "Review required"],
  },
};

function dateLabel(value: string | null, locale: Locale) {
  if (!value) return COPY[locale].unavailable;
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? COPY[locale].unavailable : new Intl.DateTimeFormat(locale === "ar" ? "ar-JO" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function ModeledReportPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const [data, setData] = useState<ModeledAcademicReportResponse | null>(null);
  const [locale, setLocale] = useState<Locale>("ar");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const copy = COPY[locale];
  const load = useCallback(async () => {
    setLoading(true); setError(false);
    try { setData(await new StudentApiService(client).getModeledReport()); }
    catch { setData(null); setError(true); }
    finally { setLoading(false); }
  }, [client]);
  useEffect(() => {
    let active = true;
    if (auth.isAuthenticated) void Promise.resolve().then(() => { if (active) return load(); });
    return () => { active = false; };
  }, [auth.isAuthenticated, load]);

  return <article className="modeled-report mx-auto max-w-4xl space-y-6" lang={locale} dir={locale === "ar" ? "rtl" : "ltr"}>
    <div className="report-controls flex flex-wrap gap-3">
      <button type="button" onClick={() => setLocale(locale === "ar" ? "en" : "ar")} className="rounded-xl border border-[#14796B] px-4 py-2" aria-label={locale === "ar" ? "Switch to English" : "التبديل إلى العربية"}>{locale === "ar" ? "English" : "العربية"}</button>
      {data && <button type="button" onClick={() => window.print()} className="rounded-xl bg-[#14796B] px-4 py-2 font-bold text-white">{copy.print}</button>}
    </div>
    <header className="rounded-2xl border-2 border-[#14796B] p-6"><p className="text-sm font-bold">Morshidi · WC-047 · MODELED / UNOFFICIAL</p><h1 className="mt-2 text-2xl font-bold">{copy.title}</h1><p className="mt-3 leading-7">{copy.notice}</p></header>
    {loading && <p role="status" aria-live="polite">{copy.loading}</p>}
    {error && <div role="alert"><p>{copy.error}</p><button type="button" onClick={() => void load()} className="underline">{copy.retry}</button></div>}
    {data && !loading && <>
      <section className="break-inside-avoid rounded-2xl border border-[#C9A45C]/30 p-6"><h2 className="text-xl font-bold">{copy.summary}</h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {[[copy.plan, data.plan_number ?? copy.unavailable], [copy.year, data.effective_year ?? copy.unavailable], [copy.updated, dateLabel(data.plan_updated_at, locale)], [copy.generated, dateLabel(data.generated_at, locale)], [copy.total, data.plan_total_required_credits], [copy.completed, data.completed_plan_credits], [copy.current, data.in_progress_plan_credits], [copy.remaining, data.remaining_plan_credits], ["Source retrieved", dateLabel(data.source_retrieved_at, locale)], ["Source type", data.source_type ?? copy.unavailable], ["Report schema", data.report_schema_version], ["Model", data.snapshot_contract_version], ["Snapshot fingerprint", data.snapshot_fingerprint], ["Report fingerprint", data.content_fingerprint]].map(([label, value]) => <div key={label} className="border-b border-[#C9A45C]/30 pb-2"><dt className="text-xs font-semibold">{label}</dt><dd className="mt-1 break-all"><bdi>{value}</bdi></dd></div>)}
        </dl>
      </section>
      <section className="rounded-2xl border border-[#C9A45C]/30 p-6"><h2 className="text-xl font-bold">{copy.courses}</h2>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">{STATES.map((state, index) => <li key={state} className="break-inside-avoid rounded-lg border border-[#C9A45C]/30 p-3"><strong>{copy.states[index]}</strong>: {data.courses.filter((course) => course.state === state).length}</li>)}</ul>
        <table className="mt-5 w-full text-sm"><caption className="sr-only">{copy.courses}</caption><thead><tr><th scope="col" className="p-2 text-start">{locale === "ar" ? "المادة" : "Course"}</th><th scope="col" className="p-2 text-start">{locale === "ar" ? "الحالة" : "State"}</th></tr></thead><tbody>{data.courses.map((course) => <tr key={course.course_code} className="break-inside-avoid border-t border-[#C9A45C]/30"><th scope="row" className="p-2 text-start font-medium"><CourseIdentity courseCode={course.course_code} nameAr={course.name_ar} nameEn={course.name_en} locale={locale} /></th><td className="p-2">{copy.states[STATES.indexOf(course.state)]}</td></tr>)}</tbody></table>
      </section>
      <footer className="break-inside-avoid rounded-2xl border border-[#C9A45C]/30 p-6"><h2 className="font-bold">{copy.limitations}</h2><p className="mt-2 text-sm">{copy.note}</p><p className="mt-2 text-xs font-bold">MODELED / UNOFFICIAL · {copy.title}</p></footer>
    </>}
  </article>;
}
