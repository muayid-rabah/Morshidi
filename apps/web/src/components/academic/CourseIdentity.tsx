// Canonical name-first display; stable course code remains secondary metadata.
import type { CourseIdentityMap } from "@/lib/api/use-course-identities";

export function localizedCourseName(nameAr: string | null | undefined,
                                    nameEn: string | null | undefined,
                                    code: string, locale: "ar" | "en"): string {
  return (locale === "ar" ? nameAr || nameEn : nameEn || nameAr) || code;
}

export function CourseIdentity({ courseCode, nameAr, nameEn, identities, locale = "ar", compact = false }: {
  courseCode: string; nameAr?: string | null; nameEn?: string | null;
  locale?: "ar" | "en"; compact?: boolean;
  identities?: CourseIdentityMap;
}) {
  const identity = identities?.get(courseCode);
  const code = identity?.course_code ?? courseCode;
  const name = localizedCourseName(nameAr ?? identity?.name_ar, nameEn ?? identity?.name_en, code, locale);
  return <span className={compact ? "inline-flex flex-wrap items-baseline gap-1" : "flex flex-col"}>
    <span className="font-semibold">{name}</span>
    {name !== code ? <span className="text-xs font-normal opacity-70" dir="ltr"><bdi>{code}</bdi></span> : null}
  </span>;
}

export function CourseReferences({ codes, identities, locale = "ar" }: {
  codes: readonly string[]; identities: CourseIdentityMap; locale?: "ar" | "en";
}) {
  return <span className="inline-flex flex-wrap gap-2">{codes.map((code, index) =>
    <CourseIdentity key={`${code}-${index}`} courseCode={code} identities={identities} locale={locale} compact />)}</span>;
}

export function CourseOptions({ id, identities, locale = "ar" }: {
  id: string; identities: CourseIdentityMap; locale?: "ar" | "en";
}) {
  const rows = [...identities].filter(([key, row]) => key === row.course_code);
  return <datalist id={id}>{rows.map(([code, row]) => <option key={code} value={code}>
    {localizedCourseName(row.name_ar, row.name_en, code, locale)} · {code}
  </option>)}</datalist>;
}
