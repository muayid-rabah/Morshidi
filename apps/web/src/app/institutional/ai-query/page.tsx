"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { AuthenticatedApiError } from "@/lib/api/authenticated-client";
import { InstitutionalAIQueryApi, type QueryRequest, type QueryResponse } from "@/lib/api/institutional-ai-query";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseIdentity, CourseOptions } from "@/components/academic/CourseIdentity";

const statusLabels: Record<NonNullable<QueryResponse["result"]>["status"], string> = {
  AVAILABLE: "النتيجة متاحة",
  SUPPRESSED: "النتيجة محجوبة لحماية الخصوصية",
  INSUFFICIENT_DATA: "البيانات غير كافية",
  REVIEW_REQUIRED: "تتطلب مراجعة بشرية",
  NOT_APPLICABLE: "المؤشر غير منطبق",
};

const fieldClass = "min-h-12 w-full rounded-xl border border-amber-300 bg-[#14201B] px-3 text-sm text-stone-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700";

export default function InstitutionalAIQueryPage() {
  const client = useAuthenticatedApi();
  const api = useMemo(() => new InstitutionalAIQueryApi(client), [client]);
  const [universities, setUniversities] = useState<string[] | null>(null);
  const [accessError, setAccessError] = useState<string | null>(null);
  const [universityId, setUniversityId] = useState("");
  const identities = useCourseIdentities(Boolean(universities?.includes(universityId)), universityId);
  const [periodId, setPeriodId] = useState("");
  const [planId, setPlanId] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    void api.access().then((ids) => {
      if (!active) return;
      setUniversities(ids);
      setUniversityId(ids[0] ?? "");
    }).catch((cause: unknown) => {
      if (!active) return;
      setAccessError(cause instanceof AuthenticatedApiError && cause.code === "FORBIDDEN"
        ? "هذه الصفحة متاحة للمحلل المؤسسي صاحب العضوية الفعالة فقط."
        : "تعذّر التحقق من صلاحية المحلل المؤسسي. أعد المحاولة لاحقاً.");
    });
    return () => { active = false; };
  }, [api]);

  function clearResult() {
    setResult(null);
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearResult();
    const normalizedQuestion = question.trim().replace(/\s+/g, " ");
    if (!universityId || normalizedQuestion.length < 8 || normalizedQuestion.length > 300) {
      setError("اختر الجامعة وأدخل سؤالاً واضحاً لا يتجاوز 300 حرف.");
      return;
    }
    const request: QueryRequest = {
      university_id: universityId, target_period_id: periodId.trim(),
      study_plan_id: planId.trim(), course_code: courseCode.trim().toUpperCase(),
      question: normalizedQuestion,
    };
    setSubmitting(true);
    try {
      setResult(await api.evaluate(request));
    } catch (cause: unknown) {
      setError(cause instanceof AuthenticatedApiError && cause.code === "FORBIDDEN"
        ? "رُفض نطاق الاستعلام أو العضوية المؤسسية."
        : "تعذّر تنفيذ الاستعلام المؤسسي حالياً. يمكنك إعادة المحاولة.");
    } finally {
      setSubmitting(false);
    }
  }

  return <main dir="rtl" className="mx-auto w-full max-w-4xl space-y-7 px-4 py-8 text-stone-900 sm:px-6">
    <header className="space-y-2">
      <p className="text-sm font-semibold text-amber-800">الاستعلامات المؤسسية · WC-039</p>
      <h1 className="text-3xl font-bold">اسأل عن مؤشر مؤسسي معتمد</h1>
      <p className="text-sm leading-7 text-stone-700">يختار مرشدي مؤشراً واحداً فقط من قائمة محددة. القيمة تُحسب بالخدمة الحتمية، ولا يُنفَّذ أي استعلام SQL من السؤال.</p>
    </header>

    {accessError ? <p role="alert" className="rounded-xl border border-[#F07869]/50 bg-[#351B17] p-4 text-sm">{accessError}</p> : null}
    {!accessError && universities === null ? <p role="status">جارٍ التحقق من الصلاحية…</p> : null}
    {!accessError && universities ? <form onSubmit={submit} className="space-y-6" aria-busy={submitting}>
      <section aria-labelledby="scope-heading" className="space-y-4 rounded-2xl border border-amber-200 bg-amber-50/50 p-4 sm:p-6">
        <h2 id="scope-heading" className="text-xl font-bold">١. النطاق المعتمد</h2>
        {universities.length > 1 ? <div className="space-y-1">
          <label htmlFor="university-id" className="block text-sm font-semibold">الجامعة</label>
          <select id="university-id" required value={universityId} onChange={(event) => { setUniversityId(event.target.value); clearResult(); }} className={fieldClass}>
            {universities.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </div> : <p className="break-all text-sm">الجامعة المصرّح بها: <span dir="ltr">{universityId}</span></p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1"><label htmlFor="target-period-id" className="block text-sm font-semibold">معرّف الفترة المستهدفة</label>
            <input id="target-period-id" required value={periodId} onChange={(event) => { setPeriodId(event.target.value); clearResult(); }} className={fieldClass} dir="ltr" /></div>
          <div className="space-y-1"><label htmlFor="study-plan-id" className="block text-sm font-semibold">معرّف الخطة الدراسية</label>
            <input id="study-plan-id" required value={planId} onChange={(event) => { setPlanId(event.target.value); clearResult(); }} className={fieldClass} dir="ltr" /></div>
          <div className="space-y-1"><label htmlFor="course-code" className="block text-sm font-semibold">رمز المادة</label>
            <input id="course-code" list="query-course-identities" required maxLength={50} value={courseCode} onChange={(event) => { setCourseCode(event.target.value); clearResult(); }} className={fieldClass} dir="ltr" />
            <CourseOptions id="query-course-identities" identities={identities} />
            {courseCode.trim() && <CourseIdentity courseCode={courseCode.trim().toUpperCase()} identities={identities} />}</div>
        </div>
      </section>
      <section aria-labelledby="question-heading" className="space-y-3 rounded-2xl border border-amber-200 p-4 sm:p-6">
        <h2 id="question-heading" className="text-xl font-bold">٢. السؤال</h2>
        <label htmlFor="institutional-question" className="block text-sm font-semibold">سؤالك عن مؤشر واحد</label>
        <textarea id="institutional-question" required minLength={8} maxLength={300} rows={3} value={question}
          onChange={(event) => { setQuestion(event.target.value); clearResult(); }}
          placeholder="كم الطلب المعلن على هذه المادة؟" className={`${fieldClass} py-3`} />
        <p className="text-xs text-stone-600">{question.length} / 300 حرف · لا تطلب سجلات طلاب فردية.</p>
        <button type="submit" disabled={submitting || !universityId}
          className="min-h-12 rounded-xl bg-teal-700 px-6 py-3 font-semibold text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:opacity-60">
          {submitting ? "جارٍ تحليل السؤال…" : "تحليل السؤال"}
        </button>
      </section>
    </form> : null}

    {error ? <p role="alert" className="rounded-xl border border-[#F07869]/50 bg-[#351B17] p-4 text-sm">{error}</p> : null}
    <div aria-live="polite" className="space-y-5">
      {result?.status === "ABSTAINED" ? <section className="rounded-2xl border border-stone-300 bg-stone-50 p-5" role="status">
        <h2 className="text-lg font-bold">لم تتم الإجابة</h2>
        <p className="mt-2">لم يتمكن مرشدي من ربط السؤال بمؤشر مؤسسي معتمد.</p>
        <p className="mt-2 text-sm">هذا النوع من البيانات غير متاح عبر الاستعلامات المؤسسية المجمعة إذا كان يتعلق بأفراد.</p>
        <p className="mt-2 text-xs text-stone-600">السبب: {result.abstention_reason}</p>
      </section> : null}
      {result?.status === "ANSWERED" && result.interpretation && result.result && result.provenance ? <>
        <section className="rounded-2xl border border-amber-200 p-5">
          <h2 className="text-lg font-bold">٣. كيف فهم مرشدي السؤال</h2>
          <p className="mt-2">فهم مرشدي السؤال على أنه: {result.interpretation.metric_label}</p>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div><dt className="font-semibold">المادة</dt><dd><CourseIdentity courseCode={result.interpretation.course_code} identities={identities} /></dd></div>
            <div><dt className="font-semibold">الفترة</dt><dd>{result.interpretation.target_period_key}</dd>
              <dd className="break-all text-xs" dir="ltr">{result.interpretation.target_period_id}</dd></div>
            <div><dt className="font-semibold">الخطة</dt><dd className="break-all" dir="ltr">{result.interpretation.study_plan_id}</dd></div>
            <div><dt className="font-semibold">إصدار القائمة</dt><dd>{result.interpretation.metric_catalog_version}</dd></div>
          </dl>
          <details className="mt-3 text-xs"><summary>المعرّف التقني للمؤشر</summary><code dir="ltr">{result.interpretation.metric_id}</code></details>
        </section>
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5" role="status">
          <h2 className="text-lg font-bold">٤. النتيجة · {statusLabels[result.result.status]}</h2>
          <p className="mt-3 text-base leading-7">{result.result.status === "SUPPRESSED"
            ? "النتيجة محجوبة وفق سياسة الإفصاح المؤسسي."
            : result.result.answer_text}</p>
          {result.result.status === "AVAILABLE" ? <p className="mt-2 font-semibold" dir="auto">{result.result.value} {result.result.unit}</p> : null}
          {result.result.status !== "SUPPRESSED" && result.result.quality_flags.length ?
            <p className="mt-2 text-xs">مؤشرات الجودة: {result.result.quality_flags.join("، ")}</p> : null}
        </section>
        <section className="rounded-2xl border border-stone-200 p-5 text-sm">
          <h2 className="text-lg font-bold">٥. المصدر وقابلية التكرار</h2>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            <div><dt>إصدار الكتالوج</dt><dd>{result.provenance.catalog_version}</dd></div>
            <div><dt>إصدار المتطلبات</dt><dd>{result.provenance.prerequisite_version}</dd></div>
            <div><dt>إصدار الطلب</dt><dd>{result.provenance.demand_source_version}</dd></div>
            <div><dt>إصدار السياسة</dt><dd>{result.provenance.policy_version}</dd></div>
            <div><dt>وقت الحساب</dt><dd dir="ltr">{result.provenance.computed_at ?? "غير متاح"}</dd></div>
          </dl>
          <p className="mt-3 break-all text-xs">بصمة الاستعلام: <code dir="ltr">{result.query_fingerprint}</code></p>
        </section>
        <section className="rounded-2xl border border-stone-200 p-5 text-sm">
          <h2 className="text-lg font-bold">٦. الحدود</h2>
          {result.limitations.length ? <ul className="mt-2 list-inside list-disc">{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            : <p className="mt-2">لا توجد حدود إضافية لهذا المؤشر ضمن البيانات المتاحة.</p>}
          <p className="mt-3">هذا الاستعلام مؤقت وغير محفوظ كسجل قرار أكاديمي.</p>
        </section>
      </> : null}
    </div>
  </main>;
}
