"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { InstitutionalAIQueryApi } from "@/lib/api/institutional-ai-query";
import { P11IntelligenceApi, type CohortView } from "@/lib/api/p11-intelligence";

export default function CohortsPage() {
  const client = useAuthenticatedApi();
  const accessApi = useMemo(() => new InstitutionalAIQueryApi(client), [client]);
  const api = useMemo(() => new P11IntelligenceApi(client), [client]);
  const [language, setLanguage] = useState<"ar" | "en">("ar");
  const [access, setAccess] = useState<"checking" | "allowed" | "denied">("checking");
  const [university, setUniversity] = useState("");
  const [plan, setPlan] = useState("");
  const [entry, setEntry] = useState("");
  const [period, setPeriod] = useState("");
  const [comparisonPeriod, setComparisonPeriod] = useState("");
  const [view, setView] = useState<CohortView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const ar = language === "ar";
  useEffect(() => {
    let live = true;
    void accessApi.access().then(ids => {
      if (!live) return;
      setUniversity(ids[0] ?? ""); setAccess(ids.length ? "allowed" : "denied");
    }).catch(() => { if (live) setAccess("denied"); });
    return () => { live = false; };
  }, [accessApi]);
  async function load(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(false); setView(null);
    try { setView(await api.cohort({ university_id: university, study_plan_id: plan,
      entry_period: entry, period, ...(comparisonPeriod ? { comparison_period: comparisonPeriod } : {}) })); }
    catch { setError(true); }
    finally { setBusy(false); }
  }
  return <main dir={ar ? "rtl" : "ltr"} className="mx-auto max-w-4xl space-y-5 p-6 text-stone-900">
    <button type="button" onClick={() => setLanguage(ar ? "en" : "ar")}
      aria-label="Switch language" className="rounded border px-3 py-2 focus-visible:outline-2">{ar ? "English" : "العربية"}</button>
    <h1 className="text-2xl font-bold">{ar ? "استكشاف المجموعات التجريبية" : "Synthetic cohort explorer"}</h1>
    <p>{ar ? "المقارنات وصفية فقط؛ ليست سببية وقد تتأثر بعوامل مربكة." :
      "Descriptive only, not causal; comparisons may be confounded."}</p>
    {access === "checking" && <p role="status">{ar ? "جارٍ التحقق من الصلاحية…" : "Checking access…"}</p>}
    {access === "denied" && <p role="alert">{ar ? "عضوية محلل مؤسسي فعّالة مطلوبة." : "Active institutional analyst membership required."}</p>}
    {access === "allowed" && <>
      <form onSubmit={load} className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1">{ar ? "الجامعة" : "University"}<input value={university} readOnly className="rounded border p-2" /></label>
        <label className="grid gap-1">{ar ? "معرّف الخطة" : "Study plan ID"}<input required value={plan} onChange={e => setPlan(e.target.value)} className="rounded border p-2" /></label>
        <label className="grid gap-1">{ar ? "فترة الالتحاق" : "Entry period"}<input required pattern="[A-Za-z0-9-]+" value={entry} onChange={e => setEntry(e.target.value)} className="rounded border p-2" /></label>
        <label className="grid gap-1">{ar ? "فترة الرصد" : "Observation period"}<input required pattern="[A-Za-z0-9-]+" value={period} onChange={e => setPeriod(e.target.value)} className="rounded border p-2" /></label>
        <label className="grid gap-1">{ar ? "فترة المقارنة (اختياري)" : "Comparison period (optional)"}<input pattern="[A-Za-z0-9-]+" value={comparisonPeriod} onChange={e => setComparisonPeriod(e.target.value)} className="rounded border p-2" /></label>
        <button disabled={busy} className="rounded bg-teal-700 px-3 py-2 text-white disabled:opacity-50">{ar ? "عرض الإجماليات" : "Load aggregates"}</button>
      </form>
      {busy && <p role="status">{ar ? "جارٍ التحميل…" : "Loading…"}</p>}
      {error && <p role="alert">{ar ? "تعذر تحميل الإجماليات أو رُفضت الصلاحية." : "Aggregates unavailable or access denied."}</p>}
      {view && <section aria-live="polite" className="space-y-2 rounded border p-4">
        {view.synthetic && <p className="rounded bg-amber-100 p-2 font-semibold">{ar ? "بيانات اصطناعية تجريبية — غير رسمية" : "SYNTHETIC DEMO DATA — not official"}</p>}
        <h2 className="font-semibold">{view.status}</h2>
        {view.status === "SUPPRESSED" && <p role="status">{ar ? "حُجبت الخلية لحماية الخصوصية." : "Small cell suppressed for privacy."}</p>}
        {view.status === "UNAVAILABLE" && <p role="status">{ar ? "لا تتوفر بيانات لهذه المجموعة." : "No cohort data available."}</p>}
        {view.status === "AVAILABLE" && view.metrics && <dl className="grid grid-cols-2 gap-2">
          <dt>{ar ? "حجم المجموعة" : "Cohort size"}</dt><dd>{view.size}</dd>
          <dt>{ar ? "متوسط التقدم المرصود" : "Observed mean completion"}</dt><dd>{view.metrics.mean_completion_ratio ?? "UNKNOWN"}</dd>
          <dt>{ar ? "تكرار المقررات" : "Repeated courses"}</dt><dd>{view.metrics.repeated_course_count ?? "SUPPRESSED"}</dd>
          <dt>{ar ? "تغطية الأدلة" : "Evidence coverage"}</dt><dd>{view.metrics.completion_evidence_count}/{view.size}</dd>
        </dl>}
        <p>{ar ? "الإصدار" : "Version"}: {view.source_version ?? "UNKNOWN"}</p>
        <p>{view.causal_limits.join(" · ")}</p>
        {view.comparison && <p>{ar ? "فرق وصفي في متوسط التقدم" : "Descriptive difference in mean completion"}: {view.comparison.status === "DESCRIPTIVE" ? view.comparison.difference ?? "UNKNOWN" : "UNAVAILABLE / SUPPRESSED"} · {view.comparison_period} · NOT_CAUSAL</p>}
      </section>}
    </>}
  </main>;
}
