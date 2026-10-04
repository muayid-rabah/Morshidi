import { AstrolabeDial } from "@/components/ui/VisualPrimitives";

interface CircularProgressProps {
  value: number;
  max: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  sublabel?: string;
  className?: string;
}

export function CircularProgress({
  value,
  max,
  size = 120,
  label,
  sublabel,
  className = "",
}: CircularProgressProps) {
  return (
    <div className={`flex flex-col items-center justify-center ${className}`}>
      <AstrolabeDial value={value} max={max} label={label ?? "التقدم"} size={size} />
      {sublabel ? <span className="mt-2 text-xs text-[#C6B69C]">{sublabel}</span> : null}
    </div>
  );
}
