"use client";

import { useEffect, useState } from "react";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";

export interface CourseDisplayIdentity {
  course_id: string; course_code: string; name_ar: string | null; name_en: string | null;
}
export type CourseIdentityMap = ReadonlyMap<string, CourseDisplayIdentity>;
const EMPTY: CourseIdentityMap = new Map();

export function courseIdentityMap(rows: CourseDisplayIdentity[]): CourseIdentityMap {
  return new Map(rows.flatMap(row => [[row.course_code, row], [row.course_id, row]]));
}

// One bounded catalog request per page/scope; no per-course lookup or persistent cache.
export function useCourseIdentities(enabled: boolean, universityId?: string): CourseIdentityMap {
  const client = useAuthenticatedApi();
  const path = universityId === undefined ? "/api/v1/me/course-identities" as const :
    `/api/v1/institutional/change-impact/course-identities?university_id=${encodeURIComponent(universityId)}` as const;
  const [loaded, setLoaded] = useState<{ client: typeof client; path: string; map: CourseIdentityMap } | null>(null);
  useEffect(() => {
    if (!enabled || universityId === "") return;
    let active = true;
    const controller = new AbortController();
    void client.request(path, { signal: controller.signal }).then(async response => {
      if (!response.ok) return;
      const rows: unknown = await response.json();
      if (!Array.isArray(rows) || !rows.every(row => row && typeof row.course_code === "string" &&
          typeof row.course_id === "string" && (row.name_ar === null || typeof row.name_ar === "string") &&
          (row.name_en === null || typeof row.name_en === "string"))) return;
      if (active) setLoaded({ client, path, map: courseIdentityMap(rows) });
    }).catch(() => { /* Display falls back to stable code; academic results remain unchanged. */ });
    return () => { active = false; controller.abort(); };
  }, [client, path, enabled, universityId]);
  return enabled && loaded?.client === client && loaded.path === path ? loaded.map : EMPTY;
}
