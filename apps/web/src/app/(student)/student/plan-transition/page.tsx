"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseIdentity, CourseReferences } from "@/components/academic/CourseIdentity";
import { PlanTransitionsApi, type TargetList, type TransitionView } from "@/lib/api/plan-transitions";

const words = {
  ar: {
    title: "مقارنة الخطط الأكاديمية", warning: "مقارنة نموذجية غير رسمية. لا تغيّر خطتك أو تسجيلك ولا تعني موافقة دائرة القبول والتسجيل.",
    loading: "جارٍ تحميل الخطط المتاحة…", unavailable: "لا تتوفر خطط مستهدفة معتمدة للنمذجة حالياً.",
    current: "الخطة الحالية", target: "الخطة المستهدفة النموذجية", compare: "عرض المقارنة النموذجية",
    recognized: "الساعات المعترف بها في النموذج", unresolved: "الساعات غير المحسومة", remaining: "الساعات المتبقية في الخطة المستهدفة",
    new: "متطلبات جديدة", removed: "متطلبات أزيلت", changes: "تغيّرات المتطلبات", evidence: "دليل قاعدة المعادلة",
    source: "المصدر", version: "الإصدار", major: "التخصص", review: "هذه النتيجة تتطلب مراجعة بشرية؛ لا تعني اعتماد المعادلة.",
    transfer: "إسقاط انتقال تخصص نموذجي، وليس قرار قبول رسمي.", noWrite: "للقراءة فقط — لم يتغير السجل الأكاديمي.",
    error: "تعذر تحميل المقارنة النموذجية.", select: "اختر الخطة المستهدفة", noItems: "لا يوجد", provenance: "مرجع المصدر",
  },
  en: {
    title: "Academic plan comparison", warning: "MODELED / UNOFFICIAL. This changes neither your plan nor enrollment and is not registrar approval.",
    loading: "Loading available plans…", unavailable: "No approved modeled target plan is available.",
    current: "Current plan", target: "Modeled target plan", compare: "View modeled comparison",
    recognized: "Modeled recognized credits", unresolved: "Unresolved credits", remaining: "Remaining target-plan credits",
    new: "New requirements", removed: "Removed requirements", changes: "Requirement changes", evidence: "Equivalency rule evidence",
    source: "Source", version: "Version", major: "Major", review: "This result requires human review; it does not grant equivalency.",
    transfer: "Modeled cross-major projection, not official transfer admission.", noWrite: "Read-only — academic records were not changed.",
    error: "The modeled comparison could not be loaded.", select: "Select target plan", noItems: "None", provenance: "Source reference",
  },
} as const;

export default function PlanTransitionPage() {
  const client = useAuthenticatedApi();
  const api = useMemo(() => new PlanTransitionsApi(client), [client]);
  const [lang, setLang] = useState<"ar" | "en">("ar");
  const [list, setList] = useState<TargetList | null>(null);
  const [selected, setSelected] = useState(0);
  const [result, setResult] = useState<TransitionView | null>(null);
  const identities = useCourseIdentities(Boolean(result));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const t = words[lang];
  useEffect(() => {
    let live = true;
    void api.targets().then(data => { if (live) setList(data); })
      .catch(() => { if (live) setError("TARGET_PLAN_UNAVAILABLE"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [api]);
  async function compare() {
    const target = list?.targets[selected];
    if (!target) return;
    setBusy(true); setError(null); setResult(null);
    try { setResult(await api.evaluate(target.plan_key)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "TARGET_PLAN_UNAVAILABLE"); }
    finally { setBusy(false); }
  }
  return <main dir={lang === "ar" ? "rtl" : "ltr"} className="mx-auto max-w-4xl space-y-5 p-6 text-stone-900">
    <button type="button" onClick={() => setLang(lang === "ar" ? "en" : "ar")}
      aria-label="Switch language" className="rounded border px-3 py-2">{lang === "ar" ? "English" : "العربية"}</button>
    <h1 className="text-2xl font-bold">{t.title}</h1>
    <p className="rounded bg-amber-100 p-3 font-semibold">{t.warning}</p>
    {loading && <p role="status">{t.loading}</p>}
    {error && <p role="alert">{t.error} ({error})</p>}
    {list && <>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.current}</h2>
        <p dir="ltr">{list.current.plan_id} / {list.current.version_id}</p>
        <p>{t.major}: <span dir="ltr">{list.current.major_id}</span></p>
        <p>{t.source}: {list.current.source} · {t.version}: {list.current.source_version}</p>
      </section>
      {list.targets.length === 0 ? <p role="status">{t.unavailable}</p> : <section className="rounded border p-4">
        <label className="block font-semibold" htmlFor="p12-target">{t.select}</label>
        <select id="p12-target" value={selected} onChange={event => { setSelected(Number(event.target.value)); setResult(null); }}
          className="mt-2 rounded border p-2">
          {list.targets.map((target, index) => <option key={target.plan_key.join("/")} value={index}>
            {target.major_id} / {target.plan_id} / {target.version_id}
          </option>)}
        </select>
        <button type="button" disabled={busy} onClick={() => void compare()}
          className="ms-3 rounded bg-teal-700 px-3 py-2 text-white disabled:opacity-50">{t.compare}</button>
      </section>}
    </>}
    {busy && <p role="status">{t.loading}</p>}
    {result && <section className="space-y-3 rounded border p-4">
      <h2 className="font-semibold">{t.target}</h2>
      <p dir="ltr">{result.target.plan_id} / {result.target.version_id} / {result.target.major_id}</p>
      {result.kind === "CROSS_MAJOR_PROJECTION" && <p role="status">{t.transfer}</p>}
      {result.status !== "MODELED" && <p role="alert">{t.review} ({result.status})</p>}
      <dl className="grid gap-2 sm:grid-cols-3">
        <div><dt>{t.recognized}</dt><dd>{result.projection.recognized_credits}</dd></div>
        <div><dt>{t.unresolved}</dt><dd>{result.projection.unresolved_credits}</dd></div>
        <div><dt>{t.remaining}</dt><dd>{result.projection.remaining_target_credits}</dd></div>
      </dl>
      <p>{t.new}: <CourseReferences codes={result.projection.new_requirements.map(id => result.target.display_course_codes?.[id] ?? id)} identities={identities} locale={lang} /></p>
      <p>{t.removed}: <CourseReferences codes={result.projection.removed_requirements.map(id => result.current.display_course_codes?.[id] ?? id)} identities={identities} locale={lang} /></p>
      <p>{t.changes}: {result.projection.changed_groups.join(", ") || t.noItems}</p>
      <ul className="space-y-2">{result.projection.lines.map((line, index) => <li key={`${index}-${line.source_course_id}-${line.target_course_id}`} className="rounded border p-2">
        <span><CourseIdentity courseCode={result.current.display_course_codes?.[line.source_course_id ?? ""] ?? line.source_course_id ?? "—"} identities={identities} locale={lang} compact /> → <CourseIdentity courseCode={result.target.display_course_codes?.[line.target_course_id ?? ""] ?? line.target_course_id ?? "—"} identities={identities} locale={lang} compact /></span> · {line.status}
        {line.rule_evidence.map(rule => <p key={rule.rule_id} className="text-sm">
          {t.evidence}: <span dir="ltr">{rule.rule_id} / {rule.rule_version}</span> · {rule.authority} · {t.provenance}: {rule.provenance} · {rule.effective_from}–{rule.effective_to ?? "∞"}
        </p>)}
      </li>)}</ul>
      <p className="text-sm">{t.source}: {result.target.source} · {t.version}: {result.target.source_version}</p>
      <p dir="ltr" className="text-sm">{result.evaluated_on} · {result.projection.fingerprint}</p>
      <p role="status">{t.noWrite}</p>
    </section>}
  </main>;
}
