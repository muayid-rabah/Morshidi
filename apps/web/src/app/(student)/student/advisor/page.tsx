"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseIdentity } from "@/components/academic/CourseIdentity";
import type { AdvisorResponse, ConversationThread, ConversationMessage } from "@/lib/api/student-types";
import {
  SendIcon,
  CompassIcon,
} from "@/components/ui/Icons";

interface ChatMessage {
  id: string;
  sender: "student" | "advisor";
  text: string;
  advisorData?: AdvisorResponse;
  timestamp: string;
}

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: "welcome",
    sender: "advisor",
    text: "أهلاً بك في مرشدي! أنا مرشدك الأكاديمي الذكي المعتمد على القواعد الحتمية لجامعتك. يمكنني شرح أهليتك للمواد، توضيح شجرة المتطلبات السابقة، واقتراح خطة دراسية متوازنة. تفضل بطرح أي استفسار أكاديمي.",
    timestamp: "الآن",
  },
];

const SUGGESTED_QUESTIONS = [
  "هل يمكنني تسجيل مادة الذكاء الاصطناعي؟",
  "كم ساعة متبقية لتخرجي في الخطة؟",
  "ما هي أفضل باقة مواد مقترحة للفصل القادم؟",
  "ما هي المتطلبات السابقة لمادة الخوارزميات؟",
];

export default function AdvisorPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();

  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const identities = useCourseIdentities(messages.some(message =>
    Boolean(message.advisorData?.clarification?.candidate_course_codes?.length)));
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [olderThreadsAvailable, setOlderThreadsAvailable] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [historyReady, setHistoryReady] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [olderAvailable, setOlderAvailable] = useState(false);
  const [loadedCount, setLoadedCount] = useState(0);
  const [inputPrompt, setInputPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const showHistory = (rows: ConversationMessage[]): ChatMessage[] => rows.map((row) => ({
    id: row.id, sender: row.role === "USER" ? "student" : "advisor",
    text: row.content,
    timestamp: new Date(row.created_at).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" }),
  }));

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    let active = true;
    const api = new StudentApiService(client);
    void api.listConversations().then(async (items) => {
      if (!active) return;
      setThreads(items);
      setOlderThreadsAvailable(items.length === 100);
      const first = items.find((item) => item.status === "ACTIVE") ?? items[0];
      if (first) {
        const rows = await api.getConversationMessages(first.id);
        if (!active) return;
        setThreadId(first.id);
        setMessages(rows.length ? showHistory(rows) : INITIAL_MESSAGES);
        setLoadedCount(rows.length);
        setOlderAvailable(rows.length === 100);
      }
      setHistoryReady(true);
    }).catch(() => { if (active) { setHistoryError(true); setHistoryReady(true); } });
    return () => { active = false; };
  }, [auth.isAuthenticated, client]);

  const openThread = async (id: string) => {
    setHistoryError(false);
    setHistoryReady(false);
    try {
      const rows = await new StudentApiService(client).getConversationMessages(id);
      setThreadId(id);
      setMessages(rows.length ? showHistory(rows) : INITIAL_MESSAGES);
      setLoadedCount(rows.length);
      setOlderAvailable(rows.length === 100);
    } catch { setHistoryError(true); }
    finally { setHistoryReady(true); }
  };

  const loadOlder = async () => {
    if (!threadId) return;
    try {
      const rows = await new StudentApiService(client).getConversationMessages(threadId, loadedCount);
      setMessages((current) => [...showHistory(rows), ...current]);
      setLoadedCount((count) => count + rows.length);
      setOlderAvailable(rows.length === 100);
    } catch { setHistoryError(true); }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend ?? inputPrompt).trim();
    if (!query || loading || !historyReady || historyError ||
        (threadId && threads.find((item) => item.id === threadId)?.status === "ARCHIVED")) return;

    setInputPrompt("");
    setLoading(true);
    let activeThreadId = threadId;

    try {
      const api = new StudentApiService(client);
      const id = activeThreadId ?? (await api.createConversation(query.slice(0, 100))).id;
      activeThreadId = id;
      if (!threadId) setThreadId(id);
      const reply = await api.continueConversation(id, query, AbortSignal.timeout(55_000));
      const advisorMsg: ChatMessage = {
        id: reply.assistant_message.id,
        sender: "advisor",
        text: reply.assistant_message.content,
        advisorData: reply.advisor,
        timestamp: new Date(reply.assistant_message.created_at).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" }),
      };
      const studentMsg = showHistory([reply.user_message])[0];
      setMessages((prev) => [...(prev === INITIAL_MESSAGES ? [] : prev), studentMsg, advisorMsg]);
      setLoadedCount((count) => count + 2);
      setThreads(await api.listConversations());
    } catch {
      if (activeThreadId) await openThread(activeThreadId);
      setHistoryError(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100svh-140px)] min-h-[34rem] flex-col space-y-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[#C9A45C]/30 pb-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-full border border-[#C9A45C]/35 bg-[#14201B] text-[#D9884A]" aria-hidden="true">
            <CompassIcon className="h-5 w-5" />
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-[#F3E9D8]">مرشدي</h1>
        </div>
      </div>

      {/* Suggested Questions */}
      <nav aria-label="المحادثات السابقة" className="flex shrink-0 flex-wrap items-center gap-2 text-xs">
        <button type="button" onClick={() => { setThreadId(null); setMessages(INITIAL_MESSAGES); setLoadedCount(0); setOlderAvailable(false); }}
          className="button-secondary min-h-10 px-4 py-2 text-xs">محادثة جديدة</button>
        {threads.map((thread) => <button key={thread.id} type="button" onClick={() => void openThread(thread.id)}
          aria-current={threadId === thread.id ? "page" : undefined} className="rounded-lg border px-3 py-1">
          {thread.title} {thread.status === "ARCHIVED" ? "(مؤرشفة)" : ""}
        </button>)}
        {olderThreadsAvailable ? <button type="button" onClick={() => {
          void new StudentApiService(client).listConversations(threads.length).then((older) => {
            setThreads((current) => [...current, ...older]); setOlderThreadsAvailable(older.length === 100);
          }).catch(() => setHistoryError(true));
        }} className="rounded-lg border px-3 py-1">محادثات أقدم / Older chats</button> : null}
        {threadId && threads.find((item) => item.id === threadId)?.status === "ACTIVE" ?
          <button type="button" onClick={() => { void new StudentApiService(client).archiveConversation(threadId).then(async () => {
            setThreads(await new StudentApiService(client).listConversations());
          }).catch(() => setHistoryError(true)); }} className="rounded-lg border px-3 py-1">أرشفة / Archive</button> : null}
      </nav>
      {historyError ? <p role="alert" className="text-sm text-[#F07869]">تعذّر تحميل المحادثة. أعد المحاولة.</p> : null}
      <div className="flex shrink-0 flex-wrap items-center gap-2 text-xs">
        <span className="font-bold text-[#C6B69C]">أسئلة شائعة سريعة:</span>
        {SUGGESTED_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => void handleSendMessage(q)}
            disabled={loading || !historyReady || historyError ||
              Boolean(threadId && threads.find((item) => item.id === threadId)?.status === "ARCHIVED")}
            className="rounded-xl border border-[#C9A45C]/30 bg-[#0F1A17] px-3 py-1 font-semibold text-[#E2B671] hover:bg-[#16362E] hover:border-[#D9884A] transition-colors disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Chat Messages Area */}
      <div role="log" aria-live="polite" aria-relevant="additions" className="manuscript-scroll flex-1 overflow-y-auto rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-4 shadow-xs space-y-6 sm:p-6">
        {olderAvailable ? <button type="button" onClick={() => void loadOlder()} className="rounded-lg border px-3 py-1 text-xs">رسائل أقدم / Older messages</button> : null}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start gap-3.5 ${
              msg.sender === "student" ? "flex-row-reverse" : "flex-row"
            }`}
          >
            {/* Avatar */}
            {msg.sender === "advisor" ? <span className="mt-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#C9A45C]/35 bg-[#14201B] text-[#D9884A]" aria-label="مرشدي"><CompassIcon className="h-4 w-4" aria-hidden="true" /></span> : null}

            {/* Bubble */}
            <div
              className={`max-w-[85%] sm:max-w-[75%] rounded-3xl p-5 text-xs ${
                msg.sender === "student"
                  ? "manuscript-user rounded-tr-xs font-semibold shadow-xs"
                  : "manuscript-assistant rounded-tl-xs shadow-xs"
              }`}
            >
              <div className="flex items-center justify-between gap-4 mb-2 text-[10px]">
                <span className={`font-bold ${msg.sender === "student" ? "text-[#18211D]/75" : "text-[#D9884A]"}`}>
                  {msg.sender === "student" ? "أنت" : "مرشدي"}
                </span>
                <span className={msg.sender === "student" ? "text-[#18211D]/60" : "text-[#C6B69C]"}>
                  {msg.timestamp}
                </span>
              </div>

              {/* Message text */}
              <p className="leading-relaxed whitespace-pre-line text-sm font-medium">
                {msg.text}
              </p>

              {/* Advisor Evidence & Authority Badge */}
              {msg.advisorData ? (
                <div className="mt-4 space-y-2 border-t border-[#C9A45C]/20 pt-3 text-[11px] text-[#C6B69C]">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-[#14201B] px-2 py-0.5 font-bold text-[#D9884A] border border-[#C9A45C]/30">
                      المصدر: {msg.advisorData.answer_authority}
                    </span>
                    <span className="rounded-md bg-[#14201B] px-2 py-0.5 text-[#C6B69C] border border-[#C9A45C]/30">
                      النية: {msg.advisorData.intent}
                    </span>
                    <span className="rounded-md bg-[#14201B] px-2 py-0.5 font-mono text-[#C6B69C] border border-[#C9A45C]/30">
                      السياسة: {msg.advisorData.policy_version}
                    </span>
                  </div>

                  {/* Clarification candidate course codes if any */}
                  {msg.advisorData.clarification?.candidate_course_codes &&
                  msg.advisorData.clarification.candidate_course_codes.length > 0 ? (
                    <div className="pt-2">
                      <span className="block font-bold text-[#F3E9D8] mb-1.5">
                        هل تقصد إحدى المواد التالية؟ اضغط للتحديد:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {msg.advisorData.clarification.candidate_course_codes.map((code) => (
                          <button
                            key={code}
                            type="button"
                            onClick={() => void handleSendMessage(`ما هي متطلبات المادة ${code}؟`)}
                            className="rounded-xl bg-[#14201B] px-3 py-1 font-mono font-bold text-[#D9884A] border border-[#C9A45C]/30 hover:bg-[#16362E] transition-colors"
                            dir="ltr"
                          >
                            <CourseIdentity courseCode={code} identities={identities} />
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {/* Trace authoritative sources */}
                  {msg.advisorData.trace?.authoritative_sources &&
                  msg.advisorData.trace.authoritative_sources.length > 0 ? (
                    <div className="text-[10px] text-[#C6B69C] pt-1">
                      <strong>المستندات المعتمدة: </strong>
                      {msg.advisorData.trace.authoritative_sources.join(", ")}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        ))}

        {/* Loading Indicator */}
        {loading ? (
          <div className="flex items-start gap-3.5">
            <div className="compass-typing flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#C9A45C]/35 bg-[#14201B] text-[#D9884A]">
              <CompassIcon className="h-4 w-4" />
            </div>
            <div className="manuscript-assistant rounded-3xl rounded-tl-xs border p-4 text-xs shadow-xs">
              <div className="flex items-center gap-2 text-[#C6B69C]">
                <CompassIcon className="compass-typing h-4 w-4 text-[#D9884A]" />
                <span>مرشدي يجهّز الرد...</span>
              </div>
            </div>
          </div>
        ) : null}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleSendMessage();
        }}
        className="shrink-0"
      >
        <div className="flex gap-2">
          <input
            type="text"
            aria-label="الاستفسار الأكاديمي"
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            placeholder="اكتب سؤالك الأكاديمي…"
            className="flex-1 rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] px-5 py-3 text-xs text-[#F3E9D8] placeholder-[#C6B69C]/60 focus:border-[#D9884A] focus:outline-hidden focus:ring-2 focus:ring-[#D9884A]/20 shadow-xs"
          />
          <button
            type="submit"
            disabled={loading || !historyReady || historyError || !inputPrompt.trim() ||
              Boolean(threadId && threads.find((item) => item.id === threadId)?.status === "ARCHIVED")}
            className="button-primary min-h-12 px-6 py-3 text-xs disabled:opacity-50"
          >
            <SendIcon className="h-4 w-4" />
            <span>إرسال</span>
          </button>
        </div>
      </form>
    </div>
  );
}
