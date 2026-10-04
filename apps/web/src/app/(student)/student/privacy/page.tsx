"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { PrivacyP14Api, type PrivacySummary, type StudyView } from "@/lib/api/privacy-p14";
import { StudentApiService } from "@/lib/api/student-api";
import type { ConversationThread } from "@/lib/api/student-types";

const copy = {
  ar: { title: "الخصوصية والتحكم بالبيانات", local: "نموذج محلي فقط — لا توجد دراسة بمشاركين حقيقيين أو سياسة احتفاظ معتمدة.",
    language: "English", loading: "جارٍ التحميل…", unavailable: "خدمة الخصوصية غير مهيأة حالياً. لم تُغيَّر بياناتك.",
    consent: "موافقات التقييم الاختيارية", study: "دراسة اصطناعية — بلا مشاركين حقيقيين", grant: "الموافقة على دراسة اصطناعية",
    withdraw: "سحب الموافقة", join: "الانضمام للدراسة", export: "طلب تصدير بيانات الخصوصية المحلية",
    correction: "طلب تصحيح", deletion: "طلب حذف", reason: "سبب الطلب", submit: "إرسال الطلب للمراجعة",
    feedback: "ملاحظات منظمة", send: "إرسال الملاحظات", requests: "طلباتك", retention: "ملخص الاحتفاظ النموذجي",
    noRetention: "لا توجد سياسة احتفاظ معتمدة", error: "تعذّر إكمال العملية. لم تتغير السجلات الأكاديمية.",
    success: "تم استلام الطلب المحلي", noAcademic: "لا يغيّر هذا المسار الدرجات أو السجلات الأكاديمية الرسمية.",
    clarity: "وضوح الشرح", usefulness: "فائدة الشرح", understanding: "فهم الدليل", workload: "عبء الاستخدام",
    accessibility: "واجهت مشكلة وصول", authoritative: "سجل مؤسسي رسمي", optional: "بيانات اختيارية قابلة للحذف",
    purposes: "أغراض المعالجة", categories: "فئات البيانات المحلية: الموافقة، المشاركة، قياسات المهمة، الملاحظات والطلبات.",
    consentNote: "الموافقة اختيارية ومحددة بهذه الدراسة ويمكن سحبها. لا تمنح حق الوصول إلى السجل الأكاديمي.",
    tasks: "مهام الدراسة" },
  en: { title: "Privacy & Data Controls", local: "Local model only — no real participants or approved retention policy.",
    language: "العربية", loading: "Loading…", unavailable: "The privacy provider is not configured. Your data was not changed.",
    consent: "Optional evaluation consent", study: "Synthetic study — no real participants", grant: "Consent to synthetic study",
    withdraw: "Withdraw consent", join: "Join study", export: "Request local privacy-data export",
    correction: "Correction request", deletion: "Deletion request", reason: "Reason for request", submit: "Submit for review",
    feedback: "Structured feedback", send: "Submit feedback", requests: "Your requests", retention: "Modeled retention summary",
    noRetention: "No approved retention policy", error: "The action could not be completed. Academic records were not changed.",
    success: "Local request received", noAcademic: "This flow does not change grades or authoritative academic records.",
    clarity: "Explanation clarity", usefulness: "Usefulness", understanding: "Evidence comprehension", workload: "Usage workload",
    accessibility: "I encountered an accessibility issue", authoritative: "Authoritative institutional record",
    optional: "Deletable optional data", purposes: "Processing purposes",
    categories: "Local data categories: consent, participation, task measures, feedback, and requests.",
    consentNote: "Consent is optional, limited to this study, and withdrawable. It does not authorize academic-record access.",
    tasks: "Study tasks" },
} as const;

export default function PrivacyPage() {
  const client = useAuthenticatedApi();
  const api = useMemo(() => new PrivacyP14Api(client), [client]);
  const [lang, setLang] = useState<"ar" | "en">("ar");
  const [summary, setSummary] = useState<PrivacySummary | null>(null);
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [chatId, setChatId] = useState("");
  const [chatReason, setChatReason] = useState("");
  const [chatUnavailable, setChatUnavailable] = useState(false);
  const [studies, setStudies] = useState<StudyView[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState(false);
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState("AUTHORITATIVE_INSTITUTIONAL_RECORD");
  const [ratings, setRatings] = useState({ clarity: 3, usefulness: 3, understanding: 3, workload: 3 });
  const [accessibilityIssue, setAccessibilityIssue] = useState(false);
  const t = copy[lang];
  const privacyAvailable = summary !== null;

  async function reload() {
    const [next, available] = await Promise.all([api.summary(), api.studies()]);
    setSummary(next); setStudies(available.studies);
  }
  useEffect(() => {
    let live = true;
    void Promise.all([api.summary(), api.studies()])
      .then(([next, available]) => { if (live) { setSummary(next); setStudies(available.studies); } })
      .catch(() => { if (live) setError(true); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [api]);
  useEffect(() => {
    if (!privacyAvailable) return;
    let live = true;
    void new StudentApiService(client).listConversations().then(rows => {
      if (live && Array.isArray(rows)) setThreads(rows);
    }).catch(() => { if (live) setChatUnavailable(true); });
    return () => { live = false; };
  }, [client, privacyAvailable]);
  async function act(work: () => Promise<unknown>) {
    setBusy(true); setError(false); setNotice(false);
    try { await work(); await reload(); setNotice(true); }
    catch { setError(true); }
    finally { setBusy(false); }
  }
  async function exportLocal() {
    await act(async () => {
      const result = await api.export();
      const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = "morshidi-local-privacy-export.json";
      link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  const activeStudy = studies[0];
  const activeConsent = summary?.consents.find(item => item.status === "GRANTED"
    && item.scopes.includes(`study:${activeStudy?.study_id}`));
  const joined = summary?.participation.some(item => item.study_id === activeStudy?.study_id && item.status === "ACTIVE");
  return <main dir={lang === "ar" ? "rtl" : "ltr"} className="mx-auto max-w-3xl space-y-5 p-6 text-stone-900">
    <button type="button" onClick={() => setLang(lang === "ar" ? "en" : "ar")}
      aria-label="Switch language" className="rounded border px-3 py-2">{t.language}</button>
    <h1 className="text-2xl font-bold">{t.title}</h1>
    <p className="rounded bg-amber-100 p-3">{t.local}</p>
    <p>{t.noAcademic}</p>
    {loading && <p role="status">{t.loading}</p>}
    {error && <p role="alert">{summary ? t.error : t.unavailable}</p>}
    {notice && <p role="status">{t.success}</p>}
    {summary && <>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.purposes}</h2>
        <p>{summary.purposes.join(" · ")}</p><p>{t.categories}</p>
      </section>
      <section className="space-y-3 rounded border p-4" aria-label={t.consent}>
        <h2 className="font-semibold">{t.consent}</h2>
        {summary.consents.map(item => <div key={item.consent_id} className="rounded border p-2">
          <p>{item.purpose} · {item.status} · {item.consent_version}</p>
          {item.status === "GRANTED" && <button type="button" disabled={busy}
            onClick={() => void act(() => api.withdraw(item.consent_id))}
            className="rounded border px-3 py-2 disabled:opacity-50">{t.withdraw}</button>}
        </div>)}
        {activeStudy && <div className="space-y-2">
          <p>{t.study}: {lang === "ar" ? activeStudy.title_ar : activeStudy.title_en}</p>
          <p>{t.consentNote} · {activeStudy.consent_version}</p>
          <h3 className="font-semibold">{t.tasks}</h3>
          <ul>{activeStudy.tasks.map(task => <li key={task.task_id}>
            {lang === "ar" ? task.instruction_ar : task.instruction_en} · {task.accessibility_note}
          </li>)}</ul>
          {!activeConsent && <button type="button" disabled={busy}
            onClick={() => void act(() => api.grant(activeStudy))}
            className="rounded border px-3 py-2 disabled:opacity-50">{t.grant}</button>}
          {activeConsent && !joined && <button type="button" disabled={busy}
            onClick={() => void act(() => api.join(activeStudy.study_id))}
            className="rounded border px-3 py-2 disabled:opacity-50">{t.join}</button>}
          {joined && <form onSubmit={event => { event.preventDefault(); void act(() => api.feedback(activeStudy.study_id,
            { ...ratings, accessibility_issue: accessibilityIssue })); }} className="space-y-2">
            <h3 className="font-semibold">{t.feedback}</h3>
            {(["clarity", "usefulness", "understanding", "workload"] as const).map(key =>
              <label key={key} className="block">{t[key]}
                <select value={ratings[key]} onChange={event => setRatings({ ...ratings, [key]: Number(event.target.value) })}
                  className="ms-2 rounded border p-2">{[1, 2, 3, 4, 5].map(value => <option key={value}>{value}</option>)}</select>
              </label>)}
            <label className="block"><input type="checkbox" checked={accessibilityIssue}
              onChange={event => setAccessibilityIssue(event.target.checked)} /> {t.accessibility}</label>
            <button type="submit" disabled={busy} className="rounded border px-3 py-2 disabled:opacity-50">{t.send}</button>
          </form>}
        </div>}
      </section>
      <section className="space-y-3 rounded border p-4">
        <h2 className="font-semibold">{t.export}</h2>
        <p className="text-sm">{lang === "ar" ? "يشمل التصدير محادثاتك وملخصاتها وتفضيلات التخطيط عند توفر المخزن؛ يوضح الملف حدود التصدير وأي بيانات لم تُضمّن." : "When storage is available, export includes your chats, summaries and planning preferences. The file declares bounds and omitted sources."}</p>
        <button type="button" disabled={busy} onClick={() => void exportLocal()}
          className="rounded border px-3 py-2 disabled:opacity-50">{t.export}</button>
      </section>
      <form onSubmit={event => { event.preventDefault(); void act(async () => {
        await api.request("CORRECTION", category, reason); setReason("");
      }); }} className="space-y-2 rounded border p-4">
        <h2 className="font-semibold">{t.correction}</h2>
        <label className="block">{t.reason}<textarea required maxLength={500} value={reason}
          onChange={event => setReason(event.target.value)} className="block w-full rounded border p-2" /></label>
        <label className="block">{t.deletion}<select value={category} onChange={event => setCategory(event.target.value)}
          className="ms-2 rounded border p-2"><option value="AUTHORITATIVE_INSTITUTIONAL_RECORD">{t.authoritative}</option>
          <option value="DELETABLE_OPTIONAL_DATA">{t.optional}</option></select></label>
        <button type="submit" disabled={busy} className="rounded border px-3 py-2 disabled:opacity-50">{t.submit} · {t.correction}</button>
        <button type="button" disabled={busy || !reason.trim()} onClick={() => void act(async () => {
          await api.request("DELETION", category, reason); setReason("");
        })} className="rounded border px-3 py-2 disabled:opacity-50">{t.submit} · {t.deletion}</button>
      </form>
      <form className="space-y-3 rounded border p-4" onSubmit={event => {
        event.preventDefault(); void act(async () => { await api.requestChatDeletion(chatId, chatReason); setChatReason(""); });
      }}>
        <h2 className="font-semibold">{lang === "ar" ? "طلب مراجعة حذف محادثة" : "Request review of chat deletion"}</h2>
        <p className="text-sm">{lang === "ar" ? "الأرشفة لا تحذف المحادثة. تبقى المحادثات بعد الخروج أو عدم النشاط. سياسة الاحتفاظ غير معتمدة؛ الطلب للمراجعة البشرية ولا ينفّذ حذفاً." : "Archive does not delete. Chats survive logout and inactivity. Retention policy is unverified; this request is for human review and performs no deletion."}</p>
        {chatUnavailable && <p role="status">{lang === "ar" ? "مخزن المحادثات غير متاح حالياً." : "Conversation storage is currently unavailable."}</p>}
        <label className="block">{lang === "ar" ? "محادثتك" : "Your conversation"}
          <select required value={chatId} onChange={event => setChatId(event.target.value)} className="block w-full rounded border p-2">
            <option value="">{lang === "ar" ? "اختر محادثة" : "Choose a conversation"}</option>
            {threads.map(thread => <option key={thread.id} value={thread.id}>{thread.title} · {thread.status}</option>)}
          </select>
        </label>
        <label className="block">{lang === "ar" ? "سبب طلب حذف المحادثة" : "Reason for chat deletion request"}
          <textarea required maxLength={500} value={chatReason} onChange={event => setChatReason(event.target.value)} className="block w-full rounded border p-2" />
        </label>
        <button disabled={busy || !chatId || !chatReason.trim()} className="rounded border px-3 py-2 disabled:opacity-50">{lang === "ar" ? "إرسال طلب مراجعة المحادثة" : "Submit chat review request"}</button>
      </form>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.requests}</h2>
        <ul>{summary.requests.map(item => <li key={item.request_id}>
          {item.kind} · {item.status} · {item.category} {item.retained_reason && `· ${item.retained_reason}`}
        </li>)}</ul>
      </section>
      <section className="rounded border p-4"><h2 className="font-semibold">{t.retention}</h2>
        {summary.retention.length === 0 ? <p>{t.noRetention}</p> : <ul>{summary.retention.map((item, index) =>
          <li key={`${item.category}-${index}`}>{item.category} · {item.period} · {item.status}</li>)}</ul>}
      </section>
    </>}
  </main>;
}
