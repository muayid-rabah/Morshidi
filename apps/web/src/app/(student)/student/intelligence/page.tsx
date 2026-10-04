"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseReferences } from "@/components/academic/CourseIdentity";
import { P11IntelligenceApi, type StudentIntelligenceView } from "@/lib/api/p11-intelligence";

const copy = {
  ar: {
    title: "استكشاف الذكاء الأكاديمي", demo: "بيانات تجريبية اصطناعية — ليست تقييماً رسمياً",
    validation: "غير متحقق للاستخدام مع طلاب حقيقيين", loading: "جارٍ تحميل الأدلة…",
    error: "تعذر تحميل أدلة الذكاء الأكاديمي.", unavailable: "لا تتوفر بيانات معتمدة لهذه الميزة حالياً.",
    strengths: "القوة والصعوبة", existing: "راجع أدلة التقدم والجاهزية الحالية؛ هذه الصفحة لا تغيّر أي قرار أكاديمي.",
    progress: "عرض التقدم الأكاديمي", noSignal: "لا تتوفر إشارة كافية من السجل الحالي", workload: "العبء الدراسي التقريبي", hours: "ساعات دراسة أسبوعياً (نطاق نمذجي)",
    unknown: "غير معروف بسبب نقص الأدلة", skills: "أدلة المهارات", careers: "مقارنة المسارات المهنية",
    internships: "معايير التدريب النموذجية", source: "المصدر / الإصدار", uncertainty: "عدم اليقين",
    gap: "فجوات", exposed: "تعرّض", evidenced: "دليل مقرر", none: "لا دليل", stale: "مصدر قديم أو غير متطابق",
    limitation: "إكمال المقرر لا يثبت إتقان المهارة. لا تعني المقارنة فرصة عمل أو أهلية تدريب.",
    risk: "لا تُعرض هنا إشارات خطر تنبؤية غير متحقق منها.",
  },
  en: {
    title: "Academic intelligence explorer", demo: "SYNTHETIC DEMO DATA — not an official assessment",
    validation: "Not validated for real students", loading: "Loading evidence…",
    error: "Intelligence evidence could not be loaded.", unavailable: "Approved evidence is unavailable for this feature.",
    strengths: "Strength and difficulty", existing: "See existing progress and readiness evidence; this view changes no academic decision.",
    progress: "View academic progress", noSignal: "Insufficient current record for a signal", workload: "Modeled workload", hours: "study hours/week (modeled range)",
    unknown: "Unknown due to insufficient evidence", skills: "Skill evidence", careers: "Career profile comparison",
    internships: "Modeled internship criteria", source: "Source / version", uncertainty: "Uncertainty",
    gap: "Gaps", exposed: "Exposed", evidenced: "Course evidence", none: "Not evidenced", stale: "Stale or mismatched source",
    limitation: "Course completion is not skill mastery. Comparison implies neither employment nor placement eligibility.",
    risk: "Unvalidated predictive risk signals are not shown here.",
  },
} as const;

const arabicSignals: Record<string, string> = {
  REQUIRED_COMPLETION: "إكمال مقرر مطلوب", RECOVERY_EVIDENCE: "تعافٍ بعد تعثر سابق",
  REPEATED_FAILURE: "تعثر متكرر في مقرر", REPEATED_WITHDRAWAL: "انسحاب متكرر",
  REQUIRED_BOTTLENECK: "عائق في مقرر مطلوب",
};

export default function StudentIntelligencePage() {
  const client = useAuthenticatedApi();
  const api = useMemo(() => new P11IntelligenceApi(client), [client]);
  const [language, setLanguage] = useState<"ar" | "en">("ar");
  const [view, setView] = useState<StudentIntelligenceView | null>(null);
  const identities = useCourseIdentities(Boolean(view));
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const ar = language === "ar";
  const t = copy[language];
  useEffect(() => {
    let live = true;
    void api.student().then(result => { if (live) { setView(result); setState("ready"); } })
      .catch(() => { if (live) setState("error"); });
    return () => { live = false; };
  }, [api]);
  return <main dir={ar ? "rtl" : "ltr"} className="mx-auto max-w-4xl space-y-5 p-6 text-stone-900">
    <button type="button" onClick={() => setLanguage(ar ? "en" : "ar")}
      className="rounded border px-3 py-2 focus-visible:outline-2" aria-label="Switch language">{ar ? "English" : "العربية"}</button>
    <h1 className="text-2xl font-bold">{t.title}</h1>
    {state === "loading" && <p role="status">{t.loading}</p>}
    {state === "error" && <p role="alert">{t.error}</p>}
    {view && <>
      {view.source_type === "SYNTHETIC" && <p className="rounded bg-amber-100 p-3 font-semibold">{t.demo}</p>}
      <p role="status">{t.validation}</p>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.strengths}</h2>
        <p>{t.existing}</p>
        <h3 className="mt-2 font-medium">{ar ? "أدلة القوة" : "Strength evidence"}</h3>
        {view.strength_difficulty.strengths.signals.length === 0 && <p>{t.noSignal}</p>}
        <ul>{view.strength_difficulty.strengths.signals.map(item => <li key={item.rule_id}>{ar ? arabicSignals[item.value] ?? item.value : item.value}: <CourseReferences codes={item.course_codes} identities={identities} locale={language} /></li>)}</ul>
        <h3 className="mt-2 font-medium">{ar ? "إشارات الصعوبة" : "Difficulty signals"}</h3>
        {view.strength_difficulty.difficulty.signals.length === 0 && <p>{t.noSignal}</p>}
        <ul>{view.strength_difficulty.difficulty.signals.map(item => <li key={item.rule_id}>{ar ? arabicSignals[item.value] ?? item.value : item.value}: <CourseReferences codes={item.course_codes} identities={identities} locale={language} /></li>)}</ul>
        <p>{ar ? "الإشارات تصف أدلة موثقة، ولا تصنف القدرة أو السبب أو الشخصية." :
          `${view.strength_difficulty.strengths.limitations.join(" ")} ${view.strength_difficulty.difficulty.limitations.join(" ")}`}</p>
        <Link className="underline" href="/student/progress">{t.progress}</Link></section>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.workload}</h2>
        <p>{view.workload.status === "RANGE" ? `${view.workload.low_hours_per_week}–${view.workload.high_hours_per_week} ${t.hours}` : t.unknown}</p>
        <p>{t.source}: {view.workload.source_version ?? t.unknown}</p><p>{t.uncertainty}: {view.workload.uncertainty}</p></section>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.skills}</h2>
        {view.skills.status !== "AVAILABLE" && <p role="status">{t.unavailable}</p>}
        <p>{t.source}: {view.skills.taxonomy_version ?? t.unknown}</p>
        <ul className="list-disc ps-5">{view.skills.items.map(item => <li key={item.skill_id}>
          {ar ? item.name_ar : item.name_en}: {item.state === "EVIDENCED" ? t.evidenced : item.state === "EXPOSED" ? t.exposed : t.none}
          {item.source_courses.length > 0 && ` (${item.source_courses.join(", ")})`}
          {item.source_courses.length > 0 && <span className="block text-xs">{t.source}: {item.mapping_provenance.join(", ")} · {item.source_courses.map(code => item.evidence_dates?.[code] ?? t.unknown).join(", ")}</span>}
        </li>)}</ul></section>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.careers}</h2>
        {view.careers.length === 0 && <p>{t.unavailable}</p>}
        {view.careers.map(career => <article key={career.career_id} className="mt-2 rounded border p-3">
          <h3 className="font-medium">{ar ? career.title_ar : career.title_en}</h3>
          {career.stale && <p role="status">{t.stale}</p>}
          <p>{t.evidenced}: {career.evidenced.join(", ") || t.none}</p><p>{t.exposed}: {career.exposed.join(", ") || t.none}</p>
          <p>{t.gap}: {career.gaps.join(", ") || t.none}</p>
          <p>{t.source}: {career.source_version} / {career.source_at}</p><p>{t.uncertainty}: {career.uncertainty}</p>
        </article>)}</section>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.internships}</h2>
        {view.internships.length === 0 && <p>{t.unavailable}</p>}
        {view.internships.map(program => <article key={program.partner_id} className="mt-2 rounded border p-3">
          <h3 className="font-medium">{ar ? program.title_ar : program.title_en}: {program.status}</h3>
          <p>{t.source}: {program.source_version} / {program.expires_at}</p>
          <ul>{program.criteria.map(criterion => <li key={criterion.criterion_id}>
            {ar ? criterion.requirement_ar : criterion.requirement_en}: {criterion.status}
          </li>)}</ul>
        </article>)}</section>
      <p className="rounded bg-stone-100 p-3">{t.limitation} {t.risk}</p>
    </>}
  </main>;
}
