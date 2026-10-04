"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/auth/auth-provider";

export function ProtectedBoundary({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "unauthenticated") router.replace("/login");
  }, [auth.status, router]);

  if (auth.status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center p-6" role="status">
        <p className="text-zinc-600 dark:text-zinc-300">جاري التحقق من الجلسة…</p>
      </main>
    );
  }

  if (auth.status === "configuration_error") {
    return (
      <main className="flex min-h-screen items-center justify-center p-6" role="alert">
        <p>تعذّر تهيئة تسجيل الدخول. تواصل مع مسؤول النظام.</p>
      </main>
    );
  }

  if (!auth.isAuthenticated) return null;
  return children;
}
