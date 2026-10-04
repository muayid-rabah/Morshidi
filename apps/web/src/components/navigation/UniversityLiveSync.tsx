"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";

type Notice = { id: number; event_id: string; summary: string; created_at: string };
const BellMark = () => <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" strokeLinecap="round" strokeLinejoin="round"/></svg>;
const SyncMark = () => <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5M5.6 9A7 7 0 0 1 18 6l2 1M4 17l2 1a7 7 0 0 0 12.4-3" strokeLinecap="round" strokeLinejoin="round"/></svg>;

export function UniversityLiveSync() {
  const auth = useAuth();
  const api = useAuthenticatedApi();
  const [items, setItems] = useState<Notice[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const [connected, setConnected] = useState(false);

  const update = useCallback((incoming: Notice[]) => {
    setItems((previous) => {
      const byId = new Map([...incoming, ...previous].map((item) => [item.id, item]));
      return [...byId.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 30);
    });
    setLastSync(new Date());
  }, []);

  const poll = useCallback(async () => {
    const response = await api.request("/api/v1/me/university-notifications");
    if (!response.ok) throw new Error("sync unavailable");
    update(await response.json() as Notice[]);
  }, [api, update]);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    let stopped = false;
    let fallback: number | undefined;
    const start = async () => {
      try {
        const response = await api.request("/api/v1/me/university-stream");
        if (!response.ok || !response.body) throw new Error("stream unavailable");
        setConnected(true);
        fallback = window.setInterval(() => { void poll().catch(() => setConnected(false)); }, 60_000);
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        while (!stopped) {
          const part = await reader.read();
          if (part.done) break;
          buffer += decoder.decode(part.value, { stream: true });
          const messages = buffer.split("\n\n");
          buffer = messages.pop() || "";
          for (const message of messages) {
            const line = message.split("\n").find((value) => value.startsWith("data: "));
            if (!line) continue;
            try {
              const notice = JSON.parse(line.slice(6)) as Notice;
              update([notice]);
              setUnread((count) => count + 1);
              window.dispatchEvent(new CustomEvent("morshidi:university-event", { detail: notice }));
            } catch { /* Ignore malformed stream frames and keep listening. */ }
          }
        }
        if (!stopped) {
          setConnected(false);
          try { await poll(); } catch { /* Continue on periodic retry. */ }
          fallback = window.setInterval(() => { void poll().catch(() => setConnected(false)); }, 60_000);
        }
      } catch {
        setConnected(false);
        try { await poll(); } catch { /* Keep the shell usable if the sync API is down. */ }
        fallback = window.setInterval(() => { void poll().catch(() => setConnected(false)); }, 60_000);
      }
    };
    void start();
    return () => { stopped = true; setConnected(false); if (fallback) window.clearInterval(fallback); };
  }, [api, auth.isAuthenticated, poll, update]);

  const syncLabel = useMemo(() => lastSync ? lastSync.toLocaleTimeString("ar-JO", { hour: "2-digit", minute: "2-digit" }) : "—", [lastSync]);

  return <div className="relative">
    <button type="button" onClick={() => { setOpen((value) => !value); setUnread(0); }} aria-label={`الإشعارات${unread ? `، ${unread} جديدة` : ""}`} aria-expanded={open}
      className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl border border-[#C9A45C]/30 bg-[#14201B] text-[#F3E9D8] hover:border-[#D9884A] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#D9884A]">
      <BellMark />
      {unread > 0 && <span className="absolute -left-1 -top-1 min-w-4 rounded-full bg-[#B8672E] px-1 text-[10px] text-white">{unread}</span>}
    </button>
    {open && <div className="absolute left-0 top-12 z-50 w-[min(22rem,90vw)] rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-3 shadow-xl" dir="rtl">
      <div className="flex items-center justify-between border-b border-[#C9A45C]/20 pb-2"><strong className="text-sm text-[#F3E9D8]">إشعارات الجامعة</strong><button type="button" onClick={() => void poll().catch(() => setConnected(false))} className="rounded-lg p-1 text-[#D9884A]" aria-label="تحديث الإشعارات"><SyncMark /></button></div>
      <p className="py-2 text-[10px] text-[#B7A78E]">{connected ? "متصل" : "مزامنة دورية"} · آخر تحديث {syncLabel}</p>
      <ul className="max-h-72 space-y-2 overflow-y-auto">{items.length ? items.map(item => <li key={item.id} className="rounded-xl border border-[#C9A45C]/15 bg-[#14201B] p-2 text-xs text-[#F3E9D8]">{item.summary}<time className="mt-1 block text-[10px] text-[#B7A78E]" dir="ltr">{new Date(item.created_at).toLocaleString("ar-JO")}</time></li>) : <li className="py-6 text-center text-xs text-[#B7A78E]">لا إشعارات جديدة</li>}</ul>
    </div>}
  </div>;
}
