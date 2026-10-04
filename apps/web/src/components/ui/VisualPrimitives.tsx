import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return <button className={`${variant === "primary" ? "button-primary" : "button-secondary"} ${className}`} {...props} />;
}

export function SurfaceCard({ className = "", children, ...props }: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return <div className={`surface-card ${className}`} {...props}>{children}</div>;
}

export function AstrolabeMark({ className = "" }: { className?: string }) {
  const ticks = Array.from({ length: 72 }, (_, index) => {
    const major = index % 6 === 0;
    return <line key={index} x1="120" y1={major ? "13" : "18"} x2="120" y2="24" stroke="currentColor" strokeWidth={major ? "1.4" : ".65"} opacity={major ? ".72" : ".34"} transform={`rotate(${index * 5} 120 120)`} />;
  });

  return (
    <svg className={className} viewBox="0 0 240 240" fill="none" aria-hidden="true">
      <circle cx="120" cy="120" r="111" stroke="currentColor" strokeOpacity=".42" />
      <circle cx="120" cy="120" r="100" stroke="currentColor" strokeOpacity=".24" />
      <circle cx="120" cy="120" r="84" stroke="currentColor" strokeOpacity=".2" />
      <circle cx="120" cy="120" r="68" stroke="currentColor" strokeOpacity=".16" />
      <g>{ticks}</g>
      <path d="M120 42 139 120 120 198 101 120 120 42Z" stroke="currentColor" strokeOpacity=".5" />
      <path d="m120 68 8 52-8 52-8-52 8-52Z" fill="currentColor" fillOpacity=".08" stroke="currentColor" strokeOpacity=".35" />
      <circle cx="120" cy="120" r="6" fill="currentColor" fillOpacity=".8" />
      <circle cx="120" cy="120" r="13" stroke="currentColor" strokeOpacity=".56" />
      <path d="M120 8v8M232 120h-8M120 232v-8M8 120h8" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function PathNode({
  code,
  hours,
  state,
  label,
}: {
  code: string;
  hours?: number;
  state: "complete" | "current" | "locked";
  label: string;
}) {
  return (
    <div className={`path-node group relative z-10 flex min-w-24 flex-col items-center gap-2 rounded-2xl border border-[#C9A45C]/30 bg-[#14201B]/95 px-3 py-3 text-center ${state}`} aria-label={`${label}: ${code}${hours ? `، ${hours} ساعات` : ""}`}>
      <span className="path-node-mark" aria-hidden="true" />
      <span className="font-mono text-xs font-bold tracking-wide text-[#F3E9D8]" dir="ltr">{code}</span>
      {hours ? <span className="text-[10px] text-[#C6B69C]">{hours} س</span> : null}
      <span className="path-node-tooltip pointer-events-none absolute bottom-[calc(100%+10px)] whitespace-nowrap rounded-lg border border-[#C9A45C]/40 bg-[#101915] px-3 py-2 text-[11px] text-[#F3E9D8] shadow-xl transition-opacity group-hover:opacity-100">
        {hours ? `${code} · ${hours} س` : code}
      </span>
    </div>
  );
}

export function AstrolabeDial({
  value,
  max,
  label,
  size = 164,
}: {
  value: number;
  max: number;
  label: string;
  size?: number;
}) {
  const percentage = max > 0 ? Math.min(100, Math.max(0, Math.round((value / max) * 100))) : 0;
  const center = size / 2;
  const radius = size * 0.39;
  const circumference = Math.PI * radius * 2;
  const ticks = Array.from({ length: 48 }, (_, index) => (
    <line key={index} x1={center} y1={size * (index % 4 === 0 ? 0.08 : 0.095)} x2={center} y2={size * 0.12} stroke="currentColor" strokeOpacity={index % 4 === 0 ? ".56" : ".22"} strokeWidth={index % 4 === 0 ? "1.2" : ".7"} transform={`rotate(${index * 7.5} ${center} ${center})`} />
  ));

  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }} role="img" aria-label={`${percentage}% ${label}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute inset-0 text-[#C9A45C]" aria-hidden="true">
        <circle cx={center} cy={center} r={radius + size * .085} fill="none" stroke="currentColor" strokeOpacity=".18" />
        <g>{ticks}</g>
        <circle cx={center} cy={center} r={radius} fill="none" className="dial-track" strokeWidth="2" />
        <circle cx={center} cy={center} r={radius} fill="none" className="dial-fill" strokeWidth="3.5" strokeDasharray={circumference} strokeDashoffset={circumference - circumference * percentage / 100} transform={`rotate(-90 ${center} ${center})`} />
      </svg>
      <div className="relative z-10 flex flex-col items-center text-center">
        <span className="font-mono text-3xl font-semibold tabular-nums text-[#F3E9D8]">{percentage}<small className="text-base text-[#D9884A]">٪</small></span>
        <span className="mt-1 max-w-24 text-[11px] leading-4 text-[#C6B69C]">{label}</span>
      </div>
    </div>
  );
}
