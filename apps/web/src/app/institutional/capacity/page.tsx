"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseIdentity, CourseOptions } from "@/components/academic/CourseIdentity";
import { P10OfferingsApi, type CapacityView, type ScenarioView, type SensitivityView } from "@/lib/api/p10-offerings";
import { InstitutionalAIQueryApi } from "@/lib/api/institutional-ai-query";

export default function CapacityPage() {
  const client = useAuthenticatedApi();
  const api = useMemo(() => new P10OfferingsApi(client), [client]);
  const accessApi = useMemo(() => new InstitutionalAIQueryApi(client), [client]);
  const [language, setLanguage] = useState<"ar" | "en">("ar");
  const [university, setUniversity] = useState("");
  const [period, setPeriod] = useState("");
  const [course, setCourse] = useState("");
  const [section, setSection] = useState("");
  const [capacity, setCapacity] = useState(30);
  const [result, setResult] = useState<CapacityView | null>(null);
  const [scenario, setScenario] = useState<ScenarioView | null>(null);
  const [sweep, setSweep] = useState<SensitivityView | null>(null);
  const [sweepSection, setSweepSection] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [access, setAccess] = useState<"checking" | "allowed" | "denied">("checking");
  const identities = useCourseIdentities(access === "allowed", university);
  const ar = language === "ar";

  useEffect(() => {
    let active = true;
    void accessApi.access().then(ids => {
      if (!active) return;
      setUniversity(ids[0] ?? "");
      setAccess(ids.length ? "allowed" : "denied");
    }).catch(() => { if (active) setAccess("denied"); });
    return () => { active = false; };
  }, [accessApi]);

  async function load(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setResult(null); setScenario(null); setSweep(null);
    try { setResult(await api.capacity(university.trim(), period.trim(), course.trim().toUpperCase())); }
    catch { setError(ar ? "تعذّر التحميل أو رُفضت الصلاحية." : "Unavailable or access denied."); }
    finally { setBusy(false); }
  }

  async function model() {
    setBusy(true); setError(""); setScenario(null);
    try { setScenario(await api.simulate({ university_id: university.trim(), target_period_id: period.trim(),
      kind: "ADD_SECTION", section_id: `MODELLED-${section.trim()}`, course_code: course.trim().toUpperCase(), capacity })); }
    catch { setError(ar ? "تعذّرت المحاكاة أو رُفضت الصلاحية." : "Simulation unavailable or access denied."); }
    finally { setBusy(false); }
  }

  async function runSweep() {
    setBusy(true); setError(""); setSweep(null);
    try {
      setSweep(await api.sensitivity({ university_id: university.trim(), target_period_id: period.trim(),
        course_code: course.trim().toUpperCase(), kind: "CAPACITY", section_id: sweepSection.trim(),
        start: 30, stop: 50, step: 10 }));
    } catch { setError(ar ? "تعذّر تحليل الحساسية أو رُفضت الصلاحية." : "Sensitivity unavailable or access denied."); }
    finally { setBusy(false); }
  }

  return <main dir={ar ? "rtl" : "ltr"} className="mx-auto max-w-4xl space-y-5 p-6 text-stone-900">
    <button type="button" onClick={() => setLanguage(ar ? "en" : "ar")}
      className="rounded border px-3 py-2 focus-visible:outline-2" aria-label="Switch language">
      {ar ? "English" : "العربية"}</button>
    <h1 className="text-2xl font-bold">{ar ? "ذكاء الطاقة الاستيعابية" : "Capacity Intelligence"}</h1>
    <p>{ar ? "الطلب المرصود ليس تسجيلاً مستقبلياً. بيانات المحاكاة افتراضية ولا تُكتب في نظام التسجيل." :
      "Observed intent is not future enrollment. Scenarios are modeled and never written to registration."}</p>
    {access === "checking" && <p role="status">{ar ? "جارٍ التحقق من الصلاحية…" : "Checking access…"}</p>}
    {access === "denied" && <p role="alert">{ar ? "مطلوبة عضوية محلل مؤسسي فعّالة." : "Active institutional analyst membership required."}</p>}
    {access === "allowed" && <>
    {course.trim() && <CourseIdentity courseCode={course.trim().toUpperCase()} identities={identities} locale={language} />}
    <form onSubmit={load} className="grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1">{ar ? "معرّف الجامعة" : "University ID"}<input required value={university} onChange={e => setUniversity(e.target.value)} className="rounded border p-2" /></label>
      <label className="grid gap-1">{ar ? "معرّف الفصل" : "Period ID"}<input required value={period} onChange={e => setPeriod(e.target.value)} className="rounded border p-2" /></label>
      <label className="grid gap-1">{ar ? "رمز المادة" : "Course code"}<input list="capacity-course-identities" required value={course} onChange={e => setCourse(e.target.value)} className="rounded border p-2" /></label>
      <CourseOptions id="capacity-course-identities" identities={identities} locale={language} />
      <button disabled={busy} className="self-end rounded bg-teal-700 p-2 text-white disabled:opacity-50">{ar ? "عرض المقارنة" : "Compare demand and supply"}</button>
    </form>
    {busy && <p role="status">{ar ? "جارٍ التحميل…" : "Loading…"}</p>}
    {error && <p role="alert">{error}</p>}
    {result && <section aria-live="polite" className="rounded border p-4">
      <h2 className="font-semibold">{ar ? "المقارنة الفعلية" : "Factual comparison"}</h2>
      {result.source_type === "SYNTHETIC" && <p className="rounded bg-amber-100 p-2 font-semibold">SANDBOX / SYNTHETIC DATA — {ar ? "غير رسمية" : "not official"}</p>}
      {result.freshness_status === "STALE" && <p role="alert">{ar ? "تحذير: مصدر المقاعد قديم." : "Warning: capacity source is stale."}</p>}
      {result.coverage_complete === false && <p role="status">{ar ? "تغطية العروض غير مكتملة." : "Offering coverage is incomplete."}</p>}
      <p>{result.status} · {result.source_version ?? (ar ? "المصدر غير متاح" : "Source unavailable")}</p>
      {result.observed_only && <p role="status">{ar ? "الطلب يشمل النوايا المرصودة فقط؛ تغطية جميع الطلاب غير مؤكدة." :
        "Demand reflects observed intents only; full population coverage is unverified."}</p>}
      <dl className="grid grid-cols-2 gap-2">
        <dt>{ar ? "الطلب المرصود" : "Observed demand"}</dt><dd>{result.observed_intent_demand ?? "UNKNOWN / SUPPRESSED"}</dd>
        <dt>{ar ? "المقاعد المقدّمة" : "Supplied seats"}</dt><dd>{result.supplied_section_capacity ?? "UNKNOWN"}</dd>
        <dt>{ar ? "الفجوة" : "Seat gap"}</dt><dd>{result.seat_gap ?? "UNKNOWN"}</dd>
        <dt>{ar ? "الشُعب الممتلئة" : "Full sections"}</dt><dd>{result.full_sections ?? "UNKNOWN"}</dd>
        <dt>{ar ? "طاقة غير معروفة" : "Unknown-capacity sections"}</dt><dd>{result.unknown_capacity_sections ?? "UNKNOWN"}</dd>
      </dl>
      {result.status === "SUPPRESSED" && <p role="status">{ar ? "الطلب محجوب لحماية الخصوصية." : "Demand suppressed for privacy."}</p>}
    </section>}
    <section className="space-y-3 rounded border p-4">
      <h2 className="font-semibold">{ar ? "إضافة شعبة افتراضية — افتراض فقط" : "Add modeled section — assumption only"}</h2>
      <label className="grid gap-1">{ar ? "رمز الشعبة الافتراضية" : "Modeled section ID"}<input value={section} onChange={e => setSection(e.target.value)} className="rounded border p-2" /></label>
      <label className="grid gap-1">{ar ? "طاقة افتراضية" : "Modeled capacity"}<input type="number" min="0" max="1000" value={capacity} onChange={e => setCapacity(Number(e.target.value))} className="rounded border p-2" /></label>
      <button type="button" disabled={busy || !university || !period || !course || !section} onClick={() => void model()}
        className="rounded bg-stone-800 px-4 py-2 text-white disabled:opacity-50">{ar ? "شغّل المحاكاة" : "Run simulation"}</button>
      {scenario && <div aria-live="polite"><p className="font-semibold">{scenario.label}</p>
        {scenario.source_type === "SYNTHETIC" && <p className="rounded bg-amber-100 p-2 font-semibold">SANDBOX / SYNTHETIC DATA — {ar ? "غير رسمية" : "not official"}</p>}
        {scenario.freshness_status === "STALE" && <p role="alert">{ar ? "أساس المحاكاة قديم." : "Scenario base snapshot is stale."}</p>}
        {scenario.observed_only && <p>{ar ? "افتراض الطلب مبني على النوايا المرصودة فقط." : "Demand assumption uses observed intents only."}</p>}
        <p>{ar ? "تغير مقاعد المادة" : "Course seat delta"}: {scenario.modeled_course_seat_delta ?? "UNKNOWN"}; {ar ? "تغير الشُعب" : "Section delta"}: {scenario.section_delta}</p>
        <p>{ar ? "فجوة الأساس ← فجوة الافتراض" : "Base gap → assumed gap"}: {scenario.base_observed_gap ?? "UNKNOWN"} → {scenario.modeled_assumed_gap ?? "UNKNOWN"}</p>
        <p className="break-all text-xs">{scenario.base_fingerprint} → {scenario.scenario_fingerprint}</p>
      </div>}
    </section>
    <section className="space-y-3 rounded border p-4">
      <h2 className="font-semibold">{ar ? "حساسية الطاقة الافتراضية" : "Modeled capacity sensitivity"}</h2>
      <p>{ar ? "ثلاث قيم افتراضية فقط: 30، 40، 50. لا توجد توصية أو تنبؤ." :
        "Three modeled capacities only: 30, 40, 50. No recommendation or prediction."}</p>
      <label className="grid gap-1">{ar ? "معرّف الشعبة الحالية" : "Existing section ID"}
        <input value={sweepSection} onChange={e => setSweepSection(e.target.value)} className="rounded border p-2" />
      </label>
      <button type="button" disabled={busy || !result || !sweepSection.trim()} onClick={() => void runSweep()}
        className="rounded bg-stone-800 px-4 py-2 text-white disabled:opacity-50">
        {ar ? "اعرض تغير الافتراض" : "Compare modeled capacities"}</button>
      {sweep && <div aria-live="polite" className="space-y-2">
        <p className="font-semibold">{sweep.label}</p>
        {sweep.source_type === "SYNTHETIC" && <p>SANDBOX / SYNTHETIC DATA</p>}
        {sweep.freshness_status === "STALE" && <p role="alert">{ar ? "المصدر قديم" : "Source snapshot is stale"}</p>}
        <ul className="list-disc ps-5">{sweep.points.map(point => <li key={point.assumption_value}>
          {ar ? "افتراض الطاقة" : "Capacity assumption"}: {point.assumption_value};
          {" "}{ar ? "المقاعد" : "seats"}: {point.modeled_course_supplied_seats ?? "UNKNOWN"};
          {" "}{ar ? "الفجوة" : "gap"}: {point.modeled_gap ?? "UNKNOWN / SUPPRESSED"}
        </li>)}</ul>
      </div>}
    </section>
    </>}
  </main>;
}
