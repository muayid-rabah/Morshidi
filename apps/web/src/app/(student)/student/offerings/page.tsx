"use client";

import { useMemo, useState, type FormEvent } from "react";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseIdentity, CourseReferences } from "@/components/academic/CourseIdentity";
import { P10OfferingsApi, type OfferingPlannerView, type OfferingView } from "@/lib/api/p10-offerings";

const messages = {
  ar: {
    title: "العروض والجدول الدراسي", intro: "التحقق الأكاديمي مستقل عن توفر الشُعب والمقاعد.",
    course: "رمز المادة", period: "الفصل", submit: "عرض الشُعب", loading: "جارٍ التحميل…",
    error: "تعذّر تحميل بيانات العروض. لا يعني ذلك عدم طرح المادة.",
    empty: "لا توجد شُعب مطابقة في اللقطة المتاحة. هذا ليس تأكيداً رسمياً بعدم طرح المادة.",
    unavailable: "مزود العروض غير متاح. لا يمكن تأكيد توفر المادة.",
    synthetic: "SANDBOX / SYNTHETIC DATA — بيانات تجريبية غير رسمية",
    academic: "الأهلية الأكاديمية", operational: "الحالة التشغيلية", capacity: "المقاعد",
    campus: "الحرم / الموقع", unknown: "غير معروف", stale: "تحذير: بيانات العروض قديمة.",
    planner: "مقارنة الخطة الأكاديمية بالعروض", credits: "الحد الأقصى للساعات",
  },
  en: {
    title: "Offerings / Schedule", intro: "Academic eligibility is separate from section and seat availability.",
    course: "Course code", period: "Period", submit: "Show sections", loading: "Loading…",
    error: "Offering data could not be loaded. This does not mean the course is not offered.",
    empty: "No matching sections in the supplied snapshot; this is not an official non-offering claim.",
    unavailable: "Offering provider unavailable; availability cannot be confirmed.",
    synthetic: "SANDBOX / SYNTHETIC DATA — not official",
    academic: "Academic eligibility", operational: "Operational state", capacity: "Seats",
    campus: "Campus / location", unknown: "Unknown", stale: "Warning: offering snapshot is stale.",
    planner: "Overlay offerings on academic plan", credits: "Maximum credits",
  },
} as const;

export default function OfferingsPage() {
  const client = useAuthenticatedApi();
  const api = useMemo(() => new P10OfferingsApi(client), [client]);
  const [language, setLanguage] = useState<"ar" | "en">("ar");
  const [course, setCourse] = useState("");
  const [period, setPeriod] = useState("");
  const [result, setResult] = useState<OfferingView | null>(null);
  const [planner, setPlanner] = useState<OfferingPlannerView | null>(null);
  const identities = useCourseIdentities(Boolean(result || planner));
  const [maxCredits, setMaxCredits] = useState(15);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const t = messages[language];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null); setError(false); setBusy(true);
    try { setResult(await api.student(course.trim().toUpperCase(), period.trim())); }
    catch { setError(true); }
    finally { setBusy(false); }
  }

  async function plan() {
    setPlanner(null); setError(false); setBusy(true);
    try { setPlanner(await api.planner(period.trim(), maxCredits)); }
    catch { setError(true); }
    finally { setBusy(false); }
  }

  return <main dir={language === "ar" ? "rtl" : "ltr"} className="mx-auto max-w-4xl space-y-5 p-6 text-stone-900">
    <button type="button" onClick={() => setLanguage(language === "ar" ? "en" : "ar")}
      className="rounded border px-3 py-2 focus-visible:outline-2" aria-label="Switch language">
      {language === "ar" ? "English" : "العربية"}
    </button>
    <h1 className="text-2xl font-bold">{t.title}</h1><p>{t.intro}</p>
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
      <label className="grid gap-1">{t.course}<input required maxLength={50} value={course}
        onChange={event => setCourse(event.target.value)} className="rounded border p-2" /></label>
      <label className="grid gap-1">{t.period}<input required maxLength={80} value={period}
        onChange={event => setPeriod(event.target.value)} className="rounded border p-2" /></label>
      <button disabled={busy} className="self-end rounded bg-teal-700 p-2 text-white disabled:opacity-50">{t.submit}</button>
    </form>
    {busy && <p role="status">{t.loading}</p>}
    {error && <p role="alert">{t.error}</p>}
    {result && <section aria-live="polite" className="space-y-3">
      <CourseIdentity courseCode={result.course_code} identities={identities} locale={language} />
      {result.source_type === "SYNTHETIC" && <p className="rounded bg-amber-100 p-2 font-semibold">{t.synthetic}</p>}
      <p>{t.academic}: {result.academic_decision} · {t.operational}: {result.operational_state}</p>
      <p>{result.source_version ?? t.unknown} · {result.fresh_until ?? t.unknown}</p>
      {result.operational_state === "SNAPSHOT_STALE" && <p role="alert">{t.stale}</p>}
      {result.operational_state === "PROVIDER_UNAVAILABLE" && <p role="status">{t.unavailable}</p>}
      {result.sections.length === 0 && result.operational_state !== "PROVIDER_UNAVAILABLE" && <p>{t.empty}</p>}
      <ul className="grid gap-3">{result.sections.map(section => <li key={section.section_id} className="rounded border p-3">
        <h2 className="font-semibold">{section.section_id} · {section.modality}</h2>
        <p>{t.campus}: {section.campus ?? t.unknown} / {section.location ?? t.unknown}</p>
        <p>{t.capacity}: {section.capacity_state} ({section.capacity ?? t.unknown})</p>
        <ul>{section.meetings.map((block, index) => <li key={index}>
          {block.day}: {block.starts_at}–{block.ends_at} ({block.timezone})
        </li>)}</ul>
      </li>)}</ul>
    </section>}
    <section className="space-y-3 rounded border p-4">
      <h2 className="font-semibold">{t.planner}</h2>
      <p>{t.intro}</p>
      <label className="grid gap-1">{t.credits}<input type="number" min="0" max="30" value={maxCredits}
        onChange={event => setMaxCredits(Number(event.target.value))} className="rounded border p-2" /></label>
      <button type="button" disabled={busy || !period.trim()} onClick={() => void plan()}
        className="rounded bg-stone-800 px-4 py-2 text-white disabled:opacity-50">{t.planner}</button>
      {planner && <div aria-live="polite" className="space-y-2">
        {planner.source_type === "SYNTHETIC" && <p className="rounded bg-amber-100 p-2 font-semibold">{t.synthetic}</p>}
        {planner.offering_overlay.map(option => <div key={option.academic_rank} className="rounded border p-2">
          <p>#{option.academic_rank} · <CourseReferences codes={option.course_codes} identities={identities} locale={language} /></p>
          <p>{option.operational_status}</p>
          <p>{option.selected_section_ids?.join(", ") ?? t.unknown}</p>
          {option.possible_pair_conflicts?.map((item, index) => <p key={index}>
            {item.reason}: {item.first_section_id} / {item.second_section_id} · {item.day} ·
            {item.starts_at ?? t.unknown}–{item.ends_at ?? t.unknown} ({item.timezone ?? t.unknown})
          </p>)}
        </div>)}
      </div>}
    </section>
  </main>;
}
