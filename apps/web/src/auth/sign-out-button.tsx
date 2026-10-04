"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/auth/auth-provider";

export function SignOutButton({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
} = {}) {
  const auth = useAuth();
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSignOut() {
    setIsSubmitting(true);
    const result = await auth.signOut();
    setIsSubmitting(false);
    if (result.ok) {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <button
      className={className ?? "button-secondary"}
      disabled={isSubmitting}
      onClick={handleSignOut}
      type="button"
    >
      {isSubmitting ? "جاري تسجيل الخروج…" : children ?? "تسجيل الخروج"}
    </button>
  );
}
