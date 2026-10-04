"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseIdentity, CourseReferences } from "@/components/academic/CourseIdentity";
import { AuthenticatedApiError } from "@/lib/api/authenticated-client";
import { ChangeImpactApi, type ChangeDelta, type ChangeImpactReport, type ChangeType } from "@/lib/api/change-impact";

type FormState = {
  change_type: ChangeType; study_plan_id: string; target_course_code: string;
  group_number: string; dependency_type: "prerequisite" | "corequisite";
  old_option_course_codes: string; new_option_course_codes: string;
  requirement_group_code: string; old_required_credits: string; new_required_credits: string;
  course_code: string; old_credit_hours: string; new_credit_hours: string;
  document_code: string; affected_topic: string;
  old_version: string; new_version: string; provenance_reference: string;
};

const initial: FormState = {
  change_type: "PREREQUISITE_GROUP_CHANGE", study_plan_id: "", target_course_code: "",
  group_number: "1", dependency_type: "prerequisite", old_option_course_codes: "",
  new_option_course_codes: "", requirement_group_code: "", old_required_credits: "",
  new_required_credits: "", course_code: "", old_credit_hours: "", new_credit_hours: "",
  document_code: "", affected_topic: "", old_version: "", new_version: "",
  provenance_reference: "",
};

const changeLabels: Record<ChangeType, string> = {
  PREREQUISITE_GROUP_CHANGE: "تغيير مجموعة متطلبات سابقة",
  REQUIREMENT_GROUP_CREDIT_CHANGE: "تغيير ساعات مجموعة متطلبات",
  COURSE_CREDIT_HOURS_CHANGE: "تغيير ساعات مادة",
  POLICY_VERSION_CHANGE: "تغيير إصدار لائحة",
};
const statusLabels: Record<ChangeImpactReport["impact_status"], string> = {
  UNCHANGED: "لا تغيير في النتيجة المحسوبة",
  CHANGED: "تغيير محتمل محدد",
  REVIEW_REQUIRED: "تتطلب مراجعة بشرية",
  UNKNOWN: "الأثر غير معروف بسبب نقص البيانات",
};

function parseCodes(value: string): string[] {
  return value.split(",").map((code) => code.trim().toUpperCase()).filter(Boolean);
}

function buildDelta(form: FormState): ChangeDelta {
  const common = { old_version: form.old_version.trim(), new_version: form.new_version.trim(),
    provenance_reference: form.provenance_reference.trim() };
  switch (form.change_type) {
    case "PREREQUISITE_GROUP_CHANGE":
      return { ...common, change_type: form.change_type, study_plan_id: form.study_plan_id.trim(),
        target_course_code: form.target_course_code.trim().toUpperCase(),
        group_number: Number(form.group_number), dependency_type: form.dependency_type,
        old_option_course_codes: parseCodes(form.old_option_course_codes),
        new_option_course_codes: parseCodes(form.new_option_course_codes) };
    case "REQUIREMENT_GROUP_CREDIT_CHANGE":
      return { ...common, change_type: form.change_type, study_plan_id: form.study_plan_id.trim(),
        requirement_group_code: form.requirement_group_code.trim().toUpperCase(),
        old_required_credits: form.old_required_credits.trim(),
        new_required_credits: form.new_required_credits.trim() };
    case "COURSE_CREDIT_HOURS_CHANGE":
      return { ...common, change_type: form.change_type, study_plan_id: form.study_plan_id.trim(),
        course_code: form.course_code.trim().toUpperCase(),
        old_credit_hours: form.old_credit_hours.trim(),
        new_credit_hours: form.new_credit_hours.trim() };
    case "POLICY_VERSION_CHANGE":
      return { ...common, change_type: form.change_type, document_code: form.document_code.trim().toUpperCase(),
        affected_topic: form.affected_topic.trim() };
  }
}

function Field({ id, label, value, onChange, type = "text", min, max, hint }: {
  id: string; label: string; value: string; onChange(value: string): void;
  type?: string; min?: string; max?: string; hint?: string;
}) {
  return <div className="space-y-1.5">
    <label htmlFor={id} className="block text-sm font-semibold text-stone-900">{label}</label>
    <input id={id} name={id} type={type} min={min} max={max} step={type === "number" ? "any" : undefined}
      required value={value} onChange={(event) => onChange(event.target.value)}
      aria-describedby={hint ? `${id}-hint` : undefined}
      className="min-h-11 w-full rounded-xl border border-amber-300 bg-[#14201B] px-3 text-sm text-stone-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700" />
    {hint && <p id={`${id}-hint`} className="text-xs text-stone-600">{hint}</p>}
  </div>;
}

export default function InstitutionalChangeImpactPage() {
  const client = useAuthenticatedApi();
  const api = useMemo(() => new ChangeImpactApi(client), [client]);
  const [universities, setUniversities] = useState<string[] | null>(null);
  const [universityId, setUniversityId] = useState("");
  const identities = useCourseIdentities(Boolean(universities?.includes(universityId)), universityId);
  const [accessError, setAccessError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(initial);
  const [result, setResult] = useState<ChangeImpactReport | null>(null);
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
        ? "لا تملك عضوية محلل مؤسسي فعالة لهذه الصفحة."
        : "تعذّر التحقق من صلاحية المحلل المؤسسي. أعد المحاولة لاحقًا.");
    });
    return () => { active = false; };
  }, [api]);

  const set = (key: keyof FormState) => (value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    setResult(null);
    setError(null);
  };

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);
    if (!universityId || form.old_version.trim() === form.new_version.trim()) {
      setError("اختر الجامعة وأدخل إصدارين مختلفين.");
      return;
    }
    const delta = buildDelta(form);
    if (delta.change_type === "PREREQUISITE_GROUP_CHANGE" &&
      (!delta.old_option_course_codes.length || !delta.new_option_course_codes.length ||
       new Set(delta.old_option_course_codes).size !== delta.old_option_course_codes.length ||
       new Set(delta.new_option_course_codes).size !== delta.new_option_course_codes.length)) {
      setError("أدخل قائمة مواد صالحة بلا تكرار لكل مجموعة.");
      return;
    }
    setSubmitting(true);
    try {
      setResult(await api.evaluate(universityId, delta));
    } catch (cause: unknown) {
      setError(cause instanceof AuthenticatedApiError
        ? (cause.code === "FORBIDDEN" ? "رُفض نطاق التحليل أو العضوية المؤسسية."
          : cause.code === "VALIDATION_ERROR" ? "المدخلات أو نطاق الخطة غير صالحين."
          : "تعذّر إكمال التحليل وتسجيل أثره في سجل التدقيق؛ لم يُعتمد تقرير.")
        : "تعذّر إكمال التحليل. أعد المحاولة عند توفر الخدمة.");
    } finally {
      setSubmitting(false);
    }
  }

  return <main dir="rtl" className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8 sm:px-6">
    <header className="space-y-2">
      <h1 className="text-2xl font-bold text-stone-900">تحليل أثر تغيير مقترح</h1>
      <p className="text-sm font-semibold text-amber-900">تحليل مقترح — لا يطبق أي تغيير</p>
      <p className="text-sm text-stone-700">لم يتم تعديل أي سجل أكاديمي. النتائج للمراجعة البشرية ولا تُعد تغييرًا منشورًا.</p>
    </header>
    {accessError && <p role="alert" className="rounded-xl border border-[#F07869]/50 bg-[#351B17] p-4 text-sm">{accessError}</p>}
    {!universities && !accessError && <p role="status">جارٍ التحقق من صلاحية المحلل…</p>}
    {universities && <form onSubmit={submit} aria-busy={submitting}
      className="space-y-5 rounded-2xl border border-amber-200 bg-[#14201B] p-4 shadow-sm sm:p-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label htmlFor="university" className="block text-sm font-semibold">الجامعة المصرّح بها</label>
          <select id="university" required value={universityId}
            onChange={(event) => setUniversityId(event.target.value)}
            className="min-h-11 w-full rounded-xl border border-amber-300 bg-[#14201B] px-3 focus-visible:outline-2 focus-visible:outline-teal-700">
            {universities.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="change-type" className="block text-sm font-semibold">نوع التغيير المقترح</label>
          <select id="change-type" value={form.change_type}
            onChange={(event) => set("change_type")(event.target.value)}
            className="min-h-11 w-full rounded-xl border border-amber-300 bg-[#14201B] px-3 focus-visible:outline-2 focus-visible:outline-teal-700">
            {Object.entries(changeLabels).map(([code, label]) =>
              <option key={code} value={code}>{label}</option>)}
          </select>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {form.change_type !== "POLICY_VERSION_CHANGE" &&
          <Field id="study-plan" label="معرّف الخطة الدراسية" value={form.study_plan_id} onChange={set("study_plan_id")} />}
        {form.change_type === "PREREQUISITE_GROUP_CHANGE" && <>
          <Field id="target-course" label="المادة المستهدفة" value={form.target_course_code} onChange={set("target_course_code")} />
          <CourseIdentity courseCode={form.target_course_code.trim().toUpperCase()} identities={identities} />
          <Field id="group-number" label="رقم مجموعة المتطلب" value={form.group_number} onChange={set("group_number")}
            type="number" min="1" max="100" />
          <div className="space-y-1.5"><label htmlFor="dependency-type" className="block text-sm font-semibold">النوع</label>
            <select id="dependency-type" value={form.dependency_type}
              onChange={(event) => set("dependency_type")(event.target.value)}
              className="min-h-11 w-full rounded-xl border border-amber-300 bg-[#14201B] px-3">
              <option value="prerequisite">متطلب سابق</option><option value="corequisite">متطلب متزامن</option>
            </select></div>
          <Field id="old-options" label="المتطلبات الحالية" value={form.old_option_course_codes}
            onChange={set("old_option_course_codes")} hint="افصل رموز المواد بفاصلة؛ كل مجموعة بدائل OR." />
          <Field id="new-options" label="المتطلبات المقترحة" value={form.new_option_course_codes}
            onChange={set("new_option_course_codes")} hint="افصل رموز المواد بفاصلة." />
          <CourseReferences codes={parseCodes(form.old_option_course_codes)} identities={identities} />
          <CourseReferences codes={parseCodes(form.new_option_course_codes)} identities={identities} />
        </>}
        {form.change_type === "REQUIREMENT_GROUP_CREDIT_CHANGE" && <>
          <Field id="requirement-group" label="مجموعة المتطلبات" value={form.requirement_group_code}
            onChange={set("requirement_group_code")} />
          <Field id="old-required" label="الساعات الحالية" value={form.old_required_credits}
            onChange={set("old_required_credits")} type="number" min="0" max="300" />
          <Field id="new-required" label="الساعات المقترحة" value={form.new_required_credits}
            onChange={set("new_required_credits")} type="number" min="0" max="300" />
        </>}
        {form.change_type === "COURSE_CREDIT_HOURS_CHANGE" && <>
          <Field id="course-code" label="المادة" value={form.course_code} onChange={set("course_code")} />
          <CourseIdentity courseCode={form.course_code.trim().toUpperCase()} identities={identities} />
          <Field id="old-hours" label="الساعات الحالية" value={form.old_credit_hours}
            onChange={set("old_credit_hours")} type="number" min="0.01" max="30" />
          <Field id="new-hours" label="الساعات المقترحة" value={form.new_credit_hours}
            onChange={set("new_credit_hours")} type="number" min="0.01" max="30" />
        </>}
        {form.change_type === "POLICY_VERSION_CHANGE" && <>
          <Field id="document-code" label="الوثيقة" value={form.document_code} onChange={set("document_code")} />
          <Field id="affected-topic" label="الموضوع المعلن" value={form.affected_topic}
            onChange={set("affected_topic")} />
        </>}
        <Field id="old-version" label="الإصدار الحالي المعلن" value={form.old_version} onChange={set("old_version")} />
        <Field id="new-version" label="الإصدار المقترح" value={form.new_version} onChange={set("new_version")} />
        <Field id="provenance" label="مرجع مصدر المقترح" value={form.provenance_reference}
          onChange={set("provenance_reference")} hint="مرجع موجز؛ لا تدخل بيانات طلاب أو أسرارًا." />
      </div>
      <button type="submit" disabled={submitting}
        className="min-h-11 rounded-xl bg-teal-700 px-5 py-2 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-800 disabled:opacity-60">
        {submitting ? "جارٍ التحليل والتدقيق…" : "تحليل الأثر المقترح"}
      </button>
    </form>}
    {error && <p role="alert" className="rounded-xl border border-[#F07869]/50 bg-[#351B17] p-4 text-sm">{error}</p>}
    {result && <section aria-live="polite" className="space-y-4 rounded-2xl border border-amber-200 bg-[#14201B] p-4 sm:p-6">
      <h2 className="text-xl font-bold">ملخص الأثر</h2>
      <p className="font-semibold">{statusLabels[result.impact_status]}</p>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="font-semibold">نوع التغيير</dt><dd>{changeLabels[result.change_type]}</dd></div>
        <div><dt className="font-semibold">الإصدار</dt><dd dir="ltr">{result.old_version} → {result.new_version}</dd></div>
        <div><dt className="font-semibold">تدقيق الأثر</dt><dd>{result.audit_status === "LEDGER_PERSISTED" ? "سُجل أثر التحليل" : "غير متاح"}</dd></div>
        <div><dt className="font-semibold">مراجعة بشرية</dt><dd>{result.requires_human_review ? "مطلوبة" : "غير مطلوبة لهذه النتيجة"}</dd></div>
      </dl>
      {result.change_type === "POLICY_VERSION_CHANGE" && result.impact_status === "REVIEW_REQUIRED" &&
        <p>يتطلب مراجعة بشرية لأن تغيير نص اللائحة غير مربوط بقاعدة حتمية.</p>}
      <div><h3 className="font-semibold">المواد المتأثرة بنيويًا</h3>
        {result.structurally_affected_courses.length ? <ul className="list-inside list-disc">
          {result.structurally_affected_courses.map((code) => <li key={code}><CourseIdentity courseCode={code} identities={identities} /></li>)}
        </ul> : <p className="text-sm text-stone-600">لا توجد مواد محددة.</p>}</div>
      <div><h3 className="font-semibold">مجموعات المتطلبات</h3>
        <p className="text-sm">{result.affected_requirement_groups.join("، ") || "لا توجد مجموعات محددة."}</p></div>
      <div><h3 className="font-semibold">النتائج الحتمية التي قد تتأثر</h3>
        <p className="text-sm">{result.affected_decision_types.join("، ") || "لم تُحدّد نتائج حتمية."}</p></div>
      {result.comparisons.length > 0 && <div><h3 className="font-semibold">مقارنات محسوبة فعليًا</h3>
        <ul className="space-y-1 text-sm">{result.comparisons.map((item) =>
          <li key={`${item.decision_class}:${item.reference}`}>{item.decision_class} — {identities.has(item.reference) ? <CourseIdentity courseCode={item.reference} identities={identities} compact /> : item.reference}: {item.before} → {item.after}</li>)}</ul>
      </div>}
      {result.limitations.length > 0 && <div><h3 className="font-semibold">القيود</h3>
        <ul className="list-inside list-disc text-sm">{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      <p className="text-sm font-semibold text-amber-900">هذا تقرير مقترح غير قابل لإعادة التشغيل التاريخي. لم يتم تعديل أي سجل أكاديمي.</p>
    </section>}
  </main>;
}
