interface ProgressBarProps {
  completed: number;
  total: number;
  label?: string;
  showPercent?: boolean;
  className?: string;
  barColor?: string;
}

export function ProgressBar({
  completed,
  total,
  label,
  showPercent = true,
  className = "",
  barColor = "bg-[#0E5A4F]",
}: ProgressBarProps) {
  const safeTotal = Number(total) || 0;
  const safeCompleted = Number(completed) || 0;
  const percent = safeTotal > 0 ? Math.min(100, Math.max(0, Math.round((safeCompleted / safeTotal) * 100))) : 0;

  return (
    <div className={`w-full ${className}`}>
      {label || showPercent ? (
        <div className="mb-2 flex items-center justify-between text-xs font-semibold text-[#C6B69C]">
          {label ? <span>{label}</span> : <span />}
          {showPercent ? <span className="font-mono text-[#F3E9D8]">{percent}%</span> : null}
        </div>
      ) : null}
      <div
        className="h-2.5 w-full overflow-hidden rounded-full bg-[#C9A45C]/60"
        role="progressbar"
        aria-valuenow={safeCompleted}
        aria-valuemin={0}
        aria-valuemax={safeTotal}
        aria-label={label ?? "مؤشر التقدم"}
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${barColor}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
