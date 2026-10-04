"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AuthenticatedApiError } from "@/lib/api/authenticated-client";
import { StudentApiService } from "@/lib/api/student-api";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import type { StudentPolicyDocumentDetail, StudentPolicyDocumentSummary, StudentPolicyPassage, StudentPolicySearchResult } from "@/lib/api/student-types";
import { Badge } from "@/components/ui/Badge";
import { AlertTriangleIcon, InfoIcon, PoliciesIcon, SearchIcon, CompassIcon } from "@/components/ui/Icons";
import { LoadingSkeletonGrid } from "@/components/ui/LoadingSkeleton";
import { PolicyAnswerPanel } from "./PolicyAnswerPanel";

const CATEGORY_LABELS: Record<string, string> = { academic_bylaws: "اللوائح الأكاديمية", disciplinary_rules: "الأنظمة التأديبية", examination_regulations: "تعليمات الامتحانات", registration_guidelines: "قواعد التسجيل والعبء" };
const AUTHORITY_LABELS: Record<string, string> = { university_council: "مجلس الجامعة", deans_council: "مجلس العمداء", board_of_trustees: "مجلس الأمناء", department_council: "مجلس القسم", faculty_council: "مجلس الكلية" };
type DetailState = "idle" | "loading" | "success" | "error";

function detailErrorMessage(error: unknown): string {
  if (error instanceof AuthenticatedApiError) {
    if (error.code === "FORBIDDEN") return "لا تملك صلاحية الوصول إلى هذه اللائحة.";
    if (error.code === "SERVICE_UNAVAILABLE") return "خدمة اللوائح والسياسات غير متاحة حالياً. يُرجى المحاولة لاحقاً.";
    if (error.code === "NETWORK_ERROR") return "تعذّر الاتصال بالخادم أثناء تحميل نص اللائحة.";
  }
  if (error instanceof Error && error.message === "NOT_FOUND") return "لم تعد هذه اللائحة متاحة ضمن اللوائح المعتمدة لجامعتك.";
  return "تعذّر تحميل تفاصيل اللائحة. يُرجى إعادة المحاولة.";
}
function isSafeUrl(value: string) { try { const url = new URL(value); return url.protocol === "http:" || url.protocol === "https:"; } catch { return false; } }
function shortHash(value: string) { return value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value; }
function Metadata({ label, value, mono = false }: { label: string; value: string | number; mono?: boolean }) {
  return <div className="min-w-0 rounded-lg bg-[#14201B]/70 px-2.5 py-2 text-[11px] text-[#C6B69C]"><dt className="font-semibold text-[#544D42]">{label}</dt><dd className={`mt-0.5 break-words text-[#F3E9D8] ${mono ? "font-mono" : ""}`}>{value}</dd></div>;
}
function PassageMetadata({ passage }: { passage: StudentPolicyPassage }) {
  return <><dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
    {passage.article_number ? <Metadata label="المادة" value={passage.article_number} /> : null}
    {passage.section_number ? <Metadata label="القسم" value={passage.section_number} /> : null}
    {passage.page_number !== null && passage.page_number !== undefined ? <Metadata label="الصفحة" value={passage.page_number} /> : null}
    {passage.heading ? <Metadata label="العنوان" value={passage.heading} /> : null}
    {passage.sequence_order ? <Metadata label="ترتيب الفقرة" value={passage.sequence_order} /> : null}
  </dl>{passage.passage_sha256 ? <dl className="mt-3"><Metadata label="بصمة الفقرة" value={shortHash(passage.passage_sha256)} mono /></dl> : null}</>;
}
function Provenance({ detail }: { detail: StudentPolicyDocumentDetail }) {
  const version = detail.active_version;
  return <section aria-label="مصدر وإصدار اللائحة" className="rounded-xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4"><h4 className="text-xs font-bold text-[#F3E9D8]">المصدر والإصدار</h4><dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
    {version.version_tag ? <Metadata label="الإصدار" value={version.version_tag} /> : null}{version.status ? <Metadata label="حالة الإصدار" value={version.status} /> : null}
    {version.effective_start_date ? <Metadata label="بداية السريان" value={version.effective_start_date} /> : null}{version.effective_end_date ? <Metadata label="نهاية السريان" value={version.effective_end_date} /> : null}
    {version.verified_at ? <Metadata label="وقت التحقق" value={version.verified_at} /> : null}{version.verified_by ? <Metadata label="تم التحقق بواسطة" value={version.verified_by} /> : null}
    {version.content_sha256 ? <Metadata label="بصمة المحتوى" value={shortHash(version.content_sha256)} mono /> : null}
    {version.source_url ? <div className="min-w-0 rounded-lg bg-[#14201B]/70 px-2.5 py-2 text-[11px] text-[#C6B69C]"><dt className="font-semibold text-[#544D42]">المصدر</dt><dd className="mt-0.5 break-all">{isSafeUrl(version.source_url) ? <a href={version.source_url} target="_blank" rel="noopener noreferrer" className="text-[#E2B671] underline underline-offset-2">مصدر خارجي ↗</a> : version.source_url}</dd></div> : null}
  </dl></section>;
}

export default function PoliciesPage() {
  const client = useAuthenticatedApi();
  const [policies, setPolicies] = useState<StudentPolicyDocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");
  const [selectedDoc, setSelectedDoc] = useState<StudentPolicyDocumentSummary | null>(null);
  const [detail, setDetail] = useState<StudentPolicyDocumentDetail | null>(null);
  const [detailState, setDetailState] = useState<DetailState>("idle");
  const [detailError, setDetailError] = useState<string | null>(null);
  const [policySearch, setPolicySearch] = useState("");
  const [searchResults, setSearchResults] = useState<StudentPolicySearchResult[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const loadPolicies = useCallback(async () => {
    setLoading(true); try { setPolicies(await new StudentApiService(client).listPolicies()); setListError(null); } catch { setListError("تعذّر تحميل اللوائح والسياسات الجامعية."); } finally { setLoading(false); }
  }, [client]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void loadPolicies(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadPolicies]);
  const loadDetail = useCallback(async (policy: StudentPolicyDocumentSummary) => {
    setSelectedDoc(policy); setDetail(null); setDetailError(null); setDetailState("loading");
    try { setDetail(await new StudentApiService(client).getPolicyDetail(policy.id)); setDetailState("success"); } catch (error) { setDetail(null); setDetailError(detailErrorMessage(error)); setDetailState("error"); }
  }, [client]);
  const closeDetail = () => { setSelectedDoc(null); setDetail(null); setDetailError(null); setDetailState("idle"); };
  const submitPolicySearch = async () => {
    const query = policySearch.trim();
    if (!query || searchLoading) return;
    setSearchLoading(true); setSearchError(null);
    try { setSearchResults(await new StudentApiService(client).searchPolicies(query, 10, "hybrid")); }
    catch { setSearchError("تعذّر البحث داخل نصوص اللوائح والسياسات."); }
    finally { setSearchLoading(false); }
  };
  const categories = useMemo(() => Array.from(new Set(policies.map((policy) => policy.category).filter(Boolean))), [policies]);
  const filtered = useMemo(() => { const query = searchQuery.trim().toLowerCase(); return policies.filter((policy) => (selectedCategory === "ALL" || policy.category === selectedCategory) && (!query || policy.title.toLowerCase().includes(query) || policy.document_code.toLowerCase().includes(query))); }, [policies, searchQuery, selectedCategory]);
  return <div className="space-y-6">
    <header className="border-b border-[#C9A45C]/30 pb-5"><div className="flex items-center gap-2"><span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">اللوائح والسياسات</span><span className="text-xs text-[#C6B69C]">المكتبة التشريعية الأكاديمية</span></div><div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div><h1 className="text-2xl font-bold tracking-tight text-[#F3E9D8]">اللوائح والسياسات الجامعية</h1><p className="mt-1 text-xs text-[#C6B69C]">استرجاع موثق ومفهرس للأنظمة وتعليمات منح درجة البكالوريوس وقواعد العبء الدراسي والإنذارات.</p></div><p className="inline-flex items-center gap-1.5 self-start rounded-full border border-[#C9A45C]/30 bg-[#192720] px-3 py-1 text-[11px] text-[#C6B69C]"><CompassIcon className="h-3.5 w-3.5 shrink-0 text-[#D9884A]" />مرشدي يستخدم اللوائح لشرح السياسات الأكاديمية، بينما تبقى قرارات الأهلية والتقدم والتخطيط لدى محركات القواعد الأكاديمية.</p></div></header>
    <PolicyAnswerPanel />
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div className="relative max-w-md flex-1"><SearchIcon className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#C6B69C]" /><input type="text" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="البحث في اللوائح والتعليمات..." className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] py-2 pr-9 pl-4 text-xs text-[#F3E9D8]" /></div>{categories.length ? <div className="flex flex-wrap gap-1.5"><button type="button" onClick={() => setSelectedCategory("ALL")} className="rounded-lg border border-[#C9A45C]/30 px-3 py-1 text-xs">الكل ({policies.length})</button>{categories.map((category) => <button type="button" key={category} onClick={() => setSelectedCategory(category)} className="rounded-lg border border-[#C9A45C]/30 px-3 py-1 text-xs">{CATEGORY_LABELS[category] || category}</button>)}</div> : null}</div>
    <form onSubmit={(event) => { event.preventDefault(); void submitPolicySearch(); }} className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4"><label htmlFor="policy-text-search" className="text-sm font-bold text-[#F3E9D8]">ابحث داخل اللوائح</label><p className="mt-1 text-xs text-[#C6B69C]">يعرض البحث نصوصاً موثقة؛ القرارات الأكاديمية تحسبها محركات القواعد.</p><div className="mt-3 flex gap-2"><input id="policy-text-search" value={policySearch} onChange={(event) => setPolicySearch(event.target.value)} placeholder="ابحث داخل نصوص اللوائح والسياسات..." className="min-w-0 flex-1 rounded-xl border border-[#C9A45C]/30 bg-[#14201B] px-3 py-2 text-sm" /><button type="submit" disabled={searchLoading || !policySearch.trim()} className="rounded-xl bg-[#0E5A4F] px-4 py-2 text-xs font-semibold text-[#F3E9D8] disabled:opacity-60">{searchLoading ? "جارٍ البحث..." : "بحث"}</button></div>
      {searchError ? <div role="alert" className="mt-3 text-sm text-[#F07869]">{searchError} <button type="button" onClick={() => void submitPolicySearch()} disabled={searchLoading} className="underline">إعادة المحاولة</button></div> : null}
      {searchResults !== null && !searchLoading && !searchError ? <div className="mt-4 space-y-3">{searchResults.length === 0 ? <p className="text-sm text-[#C6B69C]">لم يتم العثور على نص موثق يطابق بحثك.</p> : searchResults.map((result) => <article key={result.passage_id} className="rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-3"><strong className="text-xs text-[#D9884A]">{result.document_code} — {result.locator_text}</strong><p className="mt-2 whitespace-pre-wrap text-sm text-[#F3E9D8]">{result.passage_text}</p><p className="mt-2 text-xs text-[#C6B69C]">{result.heading || ""} {result.article_number ? "• المادة " + result.article_number : ""} {result.page_number ? "• ص " + result.page_number : ""} • إصدار {result.version_tag}</p><button type="button" onClick={() => { const policy = policies.find((item) => item.id === result.document_id); if (policy) void loadDetail(policy); }} className="mt-2 text-xs font-semibold text-[#E2B671] underline">فتح اللائحة كاملة</button></article>)}</div> : null}
    </form>
    {loading && !listError ? <LoadingSkeletonGrid count={3} /> : null}
    {listError ? <div role="alert" className="flex flex-col gap-3 rounded-2xl border border-[#F07869]/40 bg-[#351B17] p-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-3 text-[#F6A094]"><AlertTriangleIcon className="h-5 w-5 shrink-0" /><p className="text-sm font-medium">{listError}</p></div><button type="button" onClick={() => void loadPolicies()} disabled={loading} className="min-h-10 rounded-xl border border-[#F07869]/50 bg-[#14201B] px-4 py-2 text-xs font-semibold text-[#F07869] disabled:cursor-not-allowed disabled:opacity-60">{loading ? "جارٍ إعادة المحاولة..." : "إعادة المحاولة"}</button></div> : null}
    {!loading && !listError && !filtered.length ? <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#0F1A17] p-8 text-center sm:p-12"><PoliciesIcon className="mx-auto h-8 w-8 text-[#D9884A]" /><h2 className="mt-4 text-lg font-bold text-[#F3E9D8]">{searchQuery ? "لا توجد نتائج مطابقة لبحثك" : "لا توجد لوائح معتمدة منشورة حالياً لجامعتك"}</h2><p className="mt-2 text-xs text-[#C6B69C]">{searchQuery ? "جرّب تغيير كلمات البحث أو اختيار تصنيف آخر." : "لا يتم عرض أي تعليمات أو لوائح إلا بعد اعتمادها وفهرستها رسمياً."}</p></div> : null}
    {!loading && !listError && filtered.length ? <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">{filtered.map((policy) => <button type="button" key={policy.id} onClick={() => { if (detailState !== "loading") void loadDetail(policy); }} className="group flex min-w-0 flex-col justify-between rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-5 text-right shadow-2xs hover:border-[#14796B] focus-visible:outline-2 focus-visible:outline-[#14796B]"><div><div className="flex items-center justify-between gap-2"><span className="rounded-md bg-[#16362E] px-2 py-0.5 font-mono text-[11px] font-bold text-[#D9884A]">{policy.document_code}</span><Badge variant="neutral" className="text-[10px]">{CATEGORY_LABELS[policy.category] || policy.category}</Badge></div><h2 className="mt-3 text-base font-bold leading-snug text-[#F3E9D8]">{policy.title}</h2><p className="mt-3 text-xs text-[#C6B69C]">{AUTHORITY_LABELS[policy.authority_level] || policy.authority_level} • إصدار {policy.active_version_tag}</p></div><p className="mt-4 border-t border-[#C9A45C]/20 pt-3 text-xs text-[#D9884A]">{policy.passage_count} مادة / فقرة مفهرسة — استعراض النصوص</p></button>)}</div> : null}
    {selectedDoc ? <div role="dialog" aria-modal="true" aria-labelledby="policy-detail-title" onClick={closeDetail} className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4"><div onClick={(event) => event.stopPropagation()} className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] shadow-xl"><header className="flex items-start justify-between gap-4 border-b border-[#C9A45C]/30 p-4 sm:p-5"><div className="min-w-0"><span className="rounded-md bg-[#16362E] px-2 py-0.5 font-mono text-xs font-bold text-[#D9884A]">{selectedDoc.document_code}</span><h2 id="policy-detail-title" className="mt-2 break-words text-lg font-bold text-[#F3E9D8]">{selectedDoc.title}</h2></div><button type="button" onClick={closeDetail} aria-label="إغلاق تفاصيل اللائحة" className="shrink-0 rounded-xl border border-[#C9A45C]/30 px-3 py-2">✕</button></header><div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
      {detailState === "loading" ? <div role="status" className="py-12 text-center"><div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-[#14796B] border-t-transparent" /><p className="mt-2 text-xs text-[#C6B69C]">جارٍ تحميل نصوص اللائحة...</p></div> : null}
      {detailState === "error" && detailError ? <div role="alert" className="rounded-xl border border-[#F07869]/40 bg-[#351B17] p-5 text-center"><AlertTriangleIcon className="mx-auto h-6 w-6 text-[#F07869]" /><p className="mt-2 text-sm font-medium text-[#F6A094]">{detailError}</p><div className="mt-4 flex flex-wrap justify-center gap-2"><button type="button" onClick={() => void loadDetail(selectedDoc)} className="rounded-xl border border-[#F07869]/50 bg-[#14201B] px-4 py-2 text-xs font-semibold text-[#F07869]">إعادة المحاولة</button><button type="button" onClick={closeDetail} className="rounded-xl bg-[#0E5A4F] px-4 py-2 text-xs font-semibold text-[#F3E9D8]">العودة إلى القائمة</button></div></div> : null}
      {detailState === "success" && detail ? <><Provenance detail={detail} />{detail.passages.length ? detail.passages.map((passage) => <article key={passage.id} className="min-w-0 rounded-xl border border-[#C9A45C]/30 bg-[#192720] p-4"><div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#C9A45C]/20 pb-2"><strong className="text-xs text-[#D9884A]">{passage.locator_text}</strong>{passage.article_number ? <span className="text-[11px] text-[#C6B69C]">المادة رقم {passage.article_number}</span> : null}</div><p className="mt-3 whitespace-pre-wrap text-xs leading-relaxed text-[#F3E9D8]">{passage.passage_text}</p><PassageMetadata passage={passage} /></article>) : <p className="rounded-xl border border-[#C9A45C]/30 p-6 text-center text-xs text-[#C6B69C]">لا توجد فقرات أو نصوص مفهرسة لهذا الإصدار حالياً.</p>}</> : null}
    </div><footer className="flex items-center justify-between gap-3 border-t border-[#C9A45C]/30 bg-[#192720] p-4"><p className="flex min-w-0 items-center gap-1.5 text-[11px] text-[#C6B69C]"><InfoIcon className="h-3.5 w-3.5 shrink-0 text-[#D9884A]" />يُعرض المحتوى الموثق ولا يغيّر قرارات القواعد الأكاديمية.</p><button type="button" onClick={closeDetail} className="shrink-0 rounded-xl bg-[#0E5A4F] px-4 py-1.5 text-xs font-semibold text-[#F3E9D8]">إغلاق</button></footer></div></div> : null}
  </div>;
}
