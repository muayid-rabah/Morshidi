"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { DecisionHistoryIcon } from "@/components/ui/Icons";
import { StudentApiService } from "@/lib/api/student-api";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { useCourseIdentities, type CourseIdentityMap } from "@/lib/api/use-course-identities";
import { CourseIdentity } from "@/components/academic/CourseIdentity";
import type { StudentDecisionHistoryDetail, StudentDecisionHistoryItem } from "@/lib/api/student-types";

const PAGE_SIZE = 20;
type LoadState = "loading" | "success" | "error";
type DetailState = "idle" | "loading" | "success" | "error";

const DECISIONS: Record<string, string> = {
  MOCK_REGISTRATION_SUBMIT: "إرسال تسجيل تجريبي",
  MOCK_REGISTRATION_WITHDRAW: "سحب تسجيل تجريبي",
  MOCK_REGISTRATION_REVALIDATE: "إعادة التحقق من التسجيل التجريبي",
  ADVISOR_FORMAL_GUIDANCE: "إرشاد أكاديمي رسمي",
  FORMAL_POLICY_CONSULTATION: "استشارة لائحة أكاديمية",
};
const STATUSES: Record<string, string> = {
  EXECUTED: "نُفّذ", VALIDATED: "تم التحقق", REVALIDATED_VALID: "إعادة تحقق صالحة",
  REVALIDATED_INVALID: "إعادة تحقق غير صالحة", ABSTAINED: "تعذّر القرار",
  FLAGGED_REVIEW: "يتطلب مراجعة", SUPERSEDED: "استُبدل",
};
const REPLAY: Record<string, string> = {
  REPLAYABLE_EXACT: "قابل للتحقق بالإصدارات التاريخية",
  REPLAYABLE_CURRENT_ONLY: "قد تتاح إعادة التحقق بالحالة الحالية فقط مستقبلاً",
  NOT_REPLAYABLE: "غير قابل لإعادة التشغيل",
};

function decisionLabel(value: string) { return DECISIONS[value] ?? "سجل قرار أكاديمي"; }
function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "تاريخ غير متاح" : new Intl.DateTimeFormat("ar-JO", {
    dateStyle: "medium", timeStyle: "short",
  }).format(date);
}
function safeUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return (url.protocol === "https:" || url.protocol === "http:") &&
      !url.username && !url.password ? value : null;
  } catch { return null; }
}
function Information({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0 rounded-xl border border-[#C9A45C]/30 bg-[#14201B] px-3 py-2">
    <dt className="text-[11px] font-semibold text-[#C6B69C]">{label}</dt>
    <dd className="mt-1 break-words text-xs text-[#F3E9D8]">{children}</dd>
  </div>;
}

function EvidenceIdentity({ source, identifier, identities }: {
  source: string; identifier: string; identities: CourseIdentityMap;
}) {
  return /course|catalog/i.test(source) && identities.has(identifier)
    ? <span title="اسم العرض من الكتالوج الحالي؛ دليل القرار التاريخي محفوظ"><CourseIdentity courseCode={identifier} identities={identities} compact /></span>
    : <>{identifier}</>;
}

export default function DecisionHistoryPage() {
  const client = useAuthenticatedApi();
  const [items, setItems] = useState<StudentDecisionHistoryItem[]>([]);
  const [listState, setListState] = useState<LoadState>("loading");
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [listError, setListError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<StudentDecisionHistoryDetail | null>(null);
  const identities = useCourseIdentities(Boolean(detail?.evidence.some(item => /course|catalog/i.test(item.source))));
  const [detailState, setDetailState] = useState<DetailState>("idle");
  const detailRequest = useRef(0);

  const loadHistory = useCallback(async () => {
    setListState("loading"); setListError(false); setItems([]); setHasMore(false);
    try {
      const page = await new StudentApiService(client).listDecisionHistory(PAGE_SIZE);
      setItems(page); setHasMore(page.length === PAGE_SIZE); setListState("success");
    } catch { setListError(true); setListState("error"); }
  }, [client]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadHistory(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadHistory]);

  const loadMore = async () => {
    if (loadingMore || !hasMore || items.length === 0) return;
    setLoadingMore(true); setListError(false);
    try {
      const page = await new StudentApiService(client).listDecisionHistory(PAGE_SIZE, items[items.length - 1]);
      setItems((previous) => [...previous, ...page]); setHasMore(page.length === PAGE_SIZE);
    } catch { setListError(true); } finally { setLoadingMore(false); }
  };
  const openDetail = async (id: string) => {
    const requestId = ++detailRequest.current;
    setSelectedId(id); setDetail(null); setDetailState("loading");
    try {
      const result = await new StudentApiService(client).getDecisionHistoryEntry(id);
      if (requestId !== detailRequest.current) return;
      if (result.integrity_status !== "VERIFIED" || result.ledger_entry_id !== id) throw new Error("unsafe detail");
      setDetail(result); setDetailState("success");
    } catch {
      if (requestId !== detailRequest.current) return;
      setDetail(null); setDetailState("error");
    }
  };
  const closeDetail = () => {
    detailRequest.current += 1;
    setSelectedId(null); setDetail(null); setDetailState("idle");
  };

  return <div className="space-y-6" dir="rtl">
    <header className="border-b border-[#C9A45C]/30 pb-5">
      <div className="flex items-center gap-2 text-[#D9884A]"><DecisionHistoryIcon className="h-5 w-5" /><span className="text-xs font-bold">سجل القرارات والتدقيق</span></div>
      <h1 className="mt-2 text-2xl font-bold tracking-tight text-[#F3E9D8]">سجل القرارات الأكاديمية</h1>
      <p className="mt-2 max-w-3xl text-xs leading-relaxed text-[#C6B69C]">سجل قراءة فقط لقراراتك الموثقة المتاحة لك. سلامة السجل لا تعني توقيعاً رسمياً أو قراراً جديداً؛ الذكاء الاصطناعي يشرح والقواعد الحتمية تقرر.</p>
    </header>

    {listState === "loading" ? <p role="status" className="rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-5 text-sm text-[#C6B69C]">جارٍ تحميل سجل القرارات...</p> : null}
    {listState === "error" ? <div role="alert" className="rounded-2xl border border-[#F07869]/40 bg-[#351B17] p-5 text-sm text-[#F6A094]"><p>تعذّر تحميل سجل القرارات حالياً.</p><button type="button" onClick={() => void loadHistory()} className="mt-3 font-semibold underline">إعادة المحاولة</button></div> : null}
    {listState === "success" && items.length === 0 ? <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-8 text-center text-sm text-[#544D42]">لا توجد قرارات موثقة متاحة للعرض في سجلك حالياً.</div> : null}
    {listState === "success" && items.length > 0 ? <section aria-label="الخط الزمني للقرارات" className="space-y-4 border-r-2 border-[#C9A45C]/30 pr-4 sm:pr-6">
      {items.map((item) => <article key={item.ledger_entry_id} className="relative min-w-0 rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-4 shadow-2xs sm:p-5">
        <span aria-hidden="true" className="absolute -right-[1.39rem] top-5 h-3 w-3 rounded-full border-2 border-white bg-[#0E5A4F] sm:-right-[1.89rem]" />
        <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="text-sm font-bold text-[#F3E9D8]">{decisionLabel(item.decision_type)}</h2><span className="rounded-full bg-[#16362E] px-2 py-1 text-[11px] font-semibold text-[#E2B671]">{STATUSES[item.decision_status] ?? "حالة موثقة"}</span></div>
        <p className="mt-2 text-xs text-[#C6B69C]">{dateLabel(item.created_at)} · {item.source_engine} ({item.source_engine_version})</p>
        <div className="mt-3 flex flex-wrap gap-2 text-[11px]"><span className="rounded-lg bg-[#F3F9F0] px-2 py-1 text-[#31633A]">سلامة السجل: {item.integrity_status === "VERIFIED" ? "تم التحقق" : "تعذّر التحقق"}</span><span className="rounded-lg bg-[#0F1A17] px-2 py-1 text-[#E2B671]">{REPLAY[item.replay_status] ?? "حالة إعادة التحقق غير معروفة"}</span></div>
        {item.is_superseded ? <p className="mt-3 text-xs text-[#E2B671]">هذا السجل لم يعد الأحدث.</p> : null}
        <button type="button" onClick={() => void openDetail(item.ledger_entry_id)} className="mt-4 rounded-lg border border-[#14796B] px-3 py-2 text-xs font-semibold text-[#E2B671] hover:bg-[#0F1A17]">عرض التفاصيل</button>
      </article>)}
      {hasMore ? <button type="button" disabled={loadingMore} onClick={() => void loadMore()} className="rounded-xl border border-[#C9A45C]/30 bg-[#14201B] px-4 py-2 text-xs font-semibold text-[#E2B671] disabled:opacity-60">{loadingMore ? "جارٍ تحميل المزيد..." : "عرض المزيد"}</button> : null}
      {listError ? <p role="alert" className="text-xs text-[#F07869]">تعذّر تحميل المزيد. <button type="button" onClick={() => void loadMore()} className="underline">إعادة المحاولة</button></p> : null}
    </section> : null}

    {selectedId ? <div role="dialog" aria-modal="true" aria-labelledby="history-detail-title" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3" onClick={closeDetail}>
      <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] shadow-xl" onClick={(event) => event.stopPropagation()}>
        <header className="flex items-center justify-between gap-3 border-b border-[#C9A45C]/30 p-4"><h2 id="history-detail-title" className="text-base font-bold text-[#F3E9D8]">تفاصيل سجل القرار</h2><button type="button" onClick={closeDetail} aria-label="إغلاق التفاصيل" className="rounded-lg border border-[#C9A45C]/30 px-3 py-1 text-sm">×</button></header>
        <div className="space-y-4 overflow-y-auto p-4 text-sm">
          {detailState === "loading" ? <p role="status">جارٍ تحميل التفاصيل...</p> : null}
          {detailState === "error" ? <div role="alert" className="rounded-xl bg-[#351B17] p-4 text-[#F6A094]"><p>تعذّر تحميل تفاصيل هذا السجل أو التحقق من سلامته.</p><button type="button" onClick={() => void openDetail(selectedId)} className="mt-2 underline">إعادة المحاولة</button></div> : null}
          {detailState === "success" && detail ? <>
            <section aria-label="القرار"><h3 className="mb-2 font-bold">القرار</h3><dl className="grid grid-cols-1 gap-2 sm:grid-cols-2"><Information label="النوع">{decisionLabel(detail.decision_type)}</Information><Information label="الحالة">{STATUSES[detail.decision_status] ?? "حالة موثقة"}</Information><Information label="التاريخ">{dateLabel(detail.created_at)}</Information><Information label="فئة المصدر">{detail.provenance_class}</Information></dl></section>
            <section aria-label="المصدر والإصدارات"><h3 className="mb-2 font-bold">المصدر والإصدارات</h3><dl className="grid grid-cols-1 gap-2 sm:grid-cols-2"><Information label="المحرك">{detail.source_engine} · {detail.source_engine_version}</Information><Information label="إصدار السياسة">{detail.policy_version}</Information></dl><ul className="mt-2 list-inside list-disc text-xs text-[#544D42]">{detail.source_versions.map((version) => <li key={version}>{version}</li>)}</ul></section>
            <section aria-label="الأدلة"><h3 className="mb-2 font-bold">الأدلة</h3>{detail.evidence.length ? <div className="space-y-2">{detail.evidence.map((evidence, index) => { const uri = safeUrl(evidence.uri); return <article key={`${index}-${evidence.source}-${evidence.identifier}`} className="rounded-xl border border-[#C9A45C]/30 bg-[#192720] p-3 text-xs"><p className="font-semibold">{evidence.source} · <EvidenceIdentity source={evidence.source} identifier={evidence.identifier} identities={identities} /></p><p className="mt-1 text-[#C6B69C]">الإصدار: {evidence.version}{evidence.locator ? ` · الموضع: ${evidence.locator}` : ""}</p>{uri ? <a href={uri} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-[#E2B671] underline">فتح المصدر ↗</a> : null}</article>; })}</div> : <p className="text-xs text-[#C6B69C]">لا توجد مراجع أدلة إضافية لهذا السجل.</p>}</section>
            <section aria-label="سلامة السجل"><h3 className="mb-2 font-bold">سلامة السجل</h3><p className="text-xs text-[#31633A]">تم التحقق من سلامة السجل. هذا فحص سلامة بيانات، وليس توقيعاً رقمياً رسمياً.</p></section>
            <section aria-label="قابلية إعادة التحقق"><h3 className="mb-2 font-bold">قابلية إعادة التحقق</h3><p className="text-xs text-[#544D42]">{REPLAY[detail.replay_status] ?? "حالة إعادة التحقق غير معروفة"}. لم تُشغَّل إعادة تحقق أو إعادة حساب في هذه الصفحة.</p></section>
            <section aria-label="القيود"><h3 className="mb-2 font-bold">القيود</h3>{detail.limitations.length ? <ul className="list-inside list-disc text-xs text-[#544D42]">{detail.limitations.map((value) => <li key={value}>{value}</li>)}</ul> : <p className="text-xs text-[#C6B69C]">لا توجد قيود إضافية مسجلة.</p>}</section>
            {(detail.supersedes_entry_id || detail.is_superseded) ? <section aria-label="سجل الاستبدال"><h3 className="mb-2 font-bold">سجل الاستبدال</h3>{detail.supersedes_entry_id ? <p className="text-xs">هذا السجل يصحح أو يستبدل سجلاً سابقاً.</p> : null}{detail.is_superseded ? <p className="mt-1 text-xs">هذا السجل لم يعد الأحدث.</p> : null}</section> : null}
          </> : null}
        </div>
      </div>
    </div> : null}
  </div>;
}
