import type { ReactNode } from "react";

export type BadgeVariant =
  | "gold"
  | "success"
  | "warning"
  | "review"
  | "error"
  | "neutral";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
  size?: "sm" | "md";
}

export function Badge({
  children,
  variant = "neutral",
  className = "",
  size = "md",
}: BadgeProps) {
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs font-semibold";

  const variantClasses = {
    gold: "bg-[#16362E] text-[#E2B671] border border-[#C9A45C]/30",
    success: "bg-[#16362E] text-[#9DCEA9] border border-[#5B9974]/50",
    warning: "bg-amber-50 text-amber-800 border border-amber-200",
    review: "bg-amber-100/70 text-amber-900 border border-amber-300 font-bold",
    error: "bg-[#351B17] text-[#F07869] border border-[#F07869]/40",
    neutral: "bg-[#0F1A17] text-[#C6B69C] border border-[#C9A45C]/30",
  }[variant];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full ${sizeClasses} ${variantClasses} ${className}`}
    >
      {children}
    </span>
  );
}
