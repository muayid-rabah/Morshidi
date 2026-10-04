"use client";

import { useState } from "react";
import Link from "next/link";
import { StudentApiService } from "@/lib/api/student-api";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import type { StudentPolicyAnswerResponse } from "@/lib/api/student-types";

type AnswerState = "idle" | "loading" | "answered" | "abstained" | "handoff" | "error";

const HANDOFF_PAGES: Record<string, { href: string; label: string }> = {
  ELIGIBILITY_ENGINE: { href: "/student/eligibility", label: "التحقق من أهلية المساق" },
  PROGRESS_ENGINE: { href: "/student/progress", label: "عرض التقدم الأكاديمي" },
  SEMESTER_PLANNER_ENGINE: { href: "/student/planner", label: "فتح مخطط الفصل" },
  DEGREE_PATH_ENGINE: { href: "/student/degree-path", label: "عرض مسارات التخرج" },
  MOCK_REGISTRATION_ENGINE: { href: "/student/mock-registration", label: "فتح التسجيل التجريبي" },
};

function safeSourceUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? value : null;
  } catch {
    return null;
  }
}

export function PolicyAnswerPanel() {
  const client = useAuthenticatedApi();
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<AnswerState>("idle");
  const [result, setResult] = useState<StudentPolicyAnswerResponse | null>(null);

  const submit = async () => {
    const cleaned = question.trim();
    if (cleaned.length < 3 || state === "loading") return;
    setState("loading");
    setResult(null);
    try {
      const response = await new StudentApiService(client).answerPolicyQuestion(cleaned);
      setResult(response);
      if (response.status === "ANSWERED" && response.answer && response.citations.length) {
        setState("answered");
      } else if (response.status === "HANDOFF_REQUIRED" && response.handoff) {
        setState("handoff");
      } else {
        setState("abstained");
      }
    } catch {
      setState("error");
    }
  };

  const handoffPage = result?.handoff ? HANDOFF_PAGES[result.handoff.target_engine] : undefined;

  return <section aria-labelledby="policy-answer-title" className="rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-4 sm:p-5">
    <h2 id="policy-answer-title" className="text-base font-bold text-[#F3E9D8]">اسأل عن اللوائح</h2>
    <p className="mt-1 text-xs text-[#C6B69C]">إجابة مستندة إلى لوائح موثقة. الذكاء الاصطناعي يشرح — القواعد الحتمية تقرر.</p>
    <form className="mt-4 flex flex-col gap-2 sm:flex-row" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <label htmlFor="policy-answer-question" className="sr-only">سؤال عام عن اللوائح</label>
      <input id="policy-answer-question" type="text" maxLength={500} value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder="مثال: ما سياسة الانسحاب من المساق؟"
        className="min-w-0 flex-1 rounded-xl border border-[#C9A45C]/30 px-3 py-2 text-sm text-[#F3E9D8]" />
      <button type="submit" disabled={state === "loading" || question.trim().length < 3}
        className="rounded-xl bg-[#0E5A4F] px-4 py-2 text-xs font-semibold text-[#F3E9D8] disabled:opacity-60">
        {state === "loading" ? "جارٍ البحث في اللوائح..." : "اسأل عن اللوائح"}
      </button>
    </form>
    {state === "idle" ? <p className="mt-3 text-xs text-[#C6B69C]">تُعرض الإجابة فقط عندما يتوفر نص موثق مع إحالة دقيقة.</p> : null}
    {state === "loading" ? <p role="status" className="mt-4 text-xs text-[#C6B69C]">جارٍ البحث وتجهيز إجابة مستندة إلى النصوص الموثقة...</p> : null}
    {state === "answered" && result?.answer && result.citations.length > 0 ? <div className="mt-4 rounded-xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4">
      <h3 className="text-sm font-bold text-[#F3E9D8]">إجابة مستندة إلى لوائح موثقة</h3>
      <p dir={result.language === "en" ? "ltr" : "rtl"} className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[#F3E9D8]">{result.answer}</p>
      <div aria-label="إحالات الإجابة" className="mt-4 space-y-3">
        {result.citations.map((citation) => {
          const source = safeSourceUrl(citation.source_url);
          return <article key={citation.passage_id} className="rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-3 text-xs text-[#F3E9D8]">
            <p className="font-bold">{citation.document_title} · إصدار {citation.version_tag}</p>
            <p className="mt-1 text-[#C6B69C]">{citation.locator_text}{citation.article_number ? ` · المادة ${citation.article_number}` : ""}{citation.section_number ? ` · القسم ${citation.section_number}` : ""}{citation.page_number ? ` · الصفحة ${citation.page_number}` : ""}</p>
            {citation.heading ? <p className="mt-1 text-[#C6B69C]">{citation.heading}</p> : null}
            <details className="mt-2"><summary className="cursor-pointer font-semibold text-[#E2B671]">عرض النص الموثق</summary><p className="mt-2 whitespace-pre-wrap leading-relaxed">{citation.passage_text}</p></details>
            {source ? <a href={source} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-[#E2B671] underline">فتح المصدر ↗</a> : null}
          </article>;
        })}
      </div>
      <p className="mt-3 text-[11px] text-[#C6B69C]">هذا شرح للنصوص الموثقة، وليس قراراً جامعياً رسمياً أو حكماً على أهليتك الشخصية.</p>
    </div> : null}
    {state === "abstained" ? <div role="status" className="mt-4 rounded-xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-sm text-[#544D42]">لا توجد أدلة كافية في اللوائح الموثقة للإجابة عن هذا السؤال.</div> : null}
    {state === "handoff" && result?.handoff ? <div role="status" className="mt-4 rounded-xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-sm text-[#544D42]">
      <p>يتطلب هذا السؤال حساباً من محرك مرشدي الأكاديمي. لم تُصدر خدمة اللوائح إجابة أو قراراً بشأن حالتك.</p>
      {handoffPage ? <Link href={handoffPage.href} className="mt-2 inline-block font-semibold text-[#E2B671] underline">{handoffPage.label}</Link> : null}
    </div> : null}
    {state === "error" ? <div role="alert" className="mt-4 rounded-xl border border-[#F07869]/40 bg-[#351B17] p-4 text-sm text-[#F6A094]">
      <p>خدمة الإجابة عن اللوائح غير متاحة حالياً. يُرجى المحاولة لاحقاً.</p>
      <button type="button" onClick={() => void submit()} className="mt-2 rounded-lg border border-[#F07869]/50 bg-[#14201B] px-3 py-1.5 text-xs font-semibold">إعادة المحاولة</button>
    </div> : null}
  </section>;
}
