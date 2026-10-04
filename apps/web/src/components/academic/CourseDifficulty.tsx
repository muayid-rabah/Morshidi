import type { AdaptiveCourseResponse } from "@/lib/api/student-types";

type CourseDifficultyData = AdaptiveCourseResponse["courses"][number];

const LEVELS: Record<string, { ar: string; en: string }> = {
  VERY_EASY: { ar: "سهلة جداً", en: "Very easy" },
  EASY: { ar: "سهلة", en: "Easy" },
  MODERATE: { ar: "متوسطة", en: "Moderate" },
  HARD: { ar: "صعبة", en: "Hard" },
  VERY_HARD: { ar: "صعبة جداً", en: "Very hard" },
};

export function CourseDifficulty({ course, locale = "ar" }: {
  course: CourseDifficultyData | undefined;
  locale?: "ar" | "en";
}) {
  if (!course) return <p className="text-xs text-amber-800" role="status">
    {locale === "ar" ? "تقدير الصعوبة غير متاح حالياً" : "Difficulty estimate unavailable"}
  </p>;
  const general = LEVELS[course.general.level]?.[locale] ?? course.general.level;
  const personal = LEVELS[course.personalized.level]?.[locale] ?? course.personalized.level;
  const low = course.personalized.confidence === "LOW";
  return <div className="mt-2 text-xs" title={locale === "ar"
    ? "تقدير نمذجي من بنية المادة والمتطلبات؛ التقدير الشخصي من الأدلة الأكاديمية المتاحة، وليس ضماناً للنجاح."
    : "Modeled from course structure and prerequisites; personal estimate uses available academic evidence, not a success guarantee."}>
    <dl className="grid gap-1">
    <div><dt className="inline font-semibold">{locale === "ar" ? "الصعوبة العامة" : "General difficulty"}: </dt>
      <dd className="inline">{general} ({course.general.score}/100) · {course.general.provenance}</dd></div>
    <div><dt className="inline font-semibold">{locale === "ar" ? "الصعوبة المتوقعة بالنسبة لك" : "Estimated difficulty for you"}: </dt>
      <dd className="inline">{personal} ({course.personalized.score}/100) · {course.personalized.provenance}</dd></div>
    </dl>
    {low && <p className="text-amber-800">{locale === "ar" ? "ثقة منخفضة: الأدلة الشخصية غير كافية أو حداثتها غير مؤكدة" : "Low confidence: limited personal evidence or unknown freshness"}</p>}
  </div>;
}
