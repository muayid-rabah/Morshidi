import type { DashboardError } from "@/lib/api/student-types";
import { AlertTriangleIcon, RefreshIcon } from "@/components/ui/Icons";

interface ErrorAlertProps {
  error: DashboardError | string;
  onRetry?: () => void;
  className?: string;
}

export function getErrorMessage(error: DashboardError | string): string {
  switch (error) {
    case "FORBIDDEN":
      return "غير مصرح لك بالوصول إلى هذه البيانات الأكاديمية.";
    case "NOT_FOUND":
      return "لم يتم العثور على ملف أكاديمي";
    case "VALIDATION_ERROR":
      return "بيانات الطلب غير صالحة.";
    case "SERVICE_UNAVAILABLE":
      return "الخدمة غير متوفرة حالياً. يُرجى المحاولة لاحقاً.";
    case "SERVER_ERROR":
      return "حدث خطأ في الخادم أثناء تحميل البيانات الأكاديمية.";
    case "NETWORK_ERROR":
      return "تعذّر الاتصال بالخادم. تحقق من اتصال الإنترنت.";
    case "CONFIGURATION_ERROR":
      return "تعذّر تهيئة الاتصال بالخادم. تحقق من إعدادات النظام.";
    default:
      return typeof error === "string" && error !== "UNKNOWN"
        ? error
        : "تعذّر تحميل البيانات الأكاديمية.";
  }
}

export function isRetryableError(error: DashboardError | string): boolean {
  return error !== "FORBIDDEN" && error !== "CONFIGURATION_ERROR";
}

export function ErrorAlert({
  error,
  onRetry,
  className = "",
}: ErrorAlertProps) {
  const message = getErrorMessage(error);
  const canRetry = Boolean(onRetry) && isRetryableError(error);

  return (
    <div
      role="alert"
      className={`flex flex-col gap-3 rounded-2xl border border-[#F07869]/40 bg-[#351B17]/80 p-5 text-[#F6A094] shadow-sm sm:flex-row sm:items-center sm:justify-between ${className}`}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#47231D] text-[#F07869]">
          <AlertTriangleIcon className="h-5 w-5" />
        </div>
        <p className="text-sm font-medium leading-relaxed">{message}</p>
      </div>
      {canRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-10 items-center justify-center gap-1.5 self-start rounded-xl border border-[#F07869]/50 bg-[#14201B] px-4 py-2 text-xs font-semibold text-[#F07869] shadow-xs transition-colors hover:bg-[#351B17] sm:self-center"
        >
          <RefreshIcon className="h-3.5 w-3.5" />
          <span>إعادة المحاولة</span>
        </button>
      ) : null}
    </div>
  );
}
