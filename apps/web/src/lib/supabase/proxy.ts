import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { getPublicSupabaseConfig } from "@/lib/config/public-env";

export function isProtectedStudentPath(pathname: string): boolean {
  return pathname === "/student" || pathname.startsWith("/student/")
    || pathname === "/institutional/change-impact"
    || pathname === "/institutional/ai-query"
    || pathname === "/institutional/cohorts";
}

function copySessionState(source: NextResponse, target: NextResponse): NextResponse {
  source.cookies.getAll().forEach((cookie) => target.cookies.set(cookie));
  for (const header of ["cache-control", "expires", "pragma"]) {
    const value = source.headers.get(header);
    if (value) target.headers.set(header, value);
  }
  return target;
}

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });
  const config = getPublicSupabaseConfig();
  const supabase = createServerClient(config.url, config.publishableKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          supabaseResponse.cookies.set(name, value, options),
        );
        Object.entries(headers).forEach(([key, value]) =>
          supabaseResponse.headers.set(key, value),
        );
      },
    },
  });

  // Official verification/refresh boundary. Academic authorization stays in FastAPI.
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;

  if (!claims && isProtectedStudentPath(request.nextUrl.pathname)) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.search = "";
    loginUrl.searchParams.set(
      "returnTo",
      `${request.nextUrl.pathname}${request.nextUrl.search}`,
    );
    return copySessionState(supabaseResponse, NextResponse.redirect(loginUrl));
  }

  if (claims && request.nextUrl.pathname === "/login") {
    const studentUrl = request.nextUrl.clone();
    const destination = request.nextUrl.searchParams.get("returnTo");
    studentUrl.pathname = destination === "/institutional/change-impact" || destination === "/institutional/ai-query" || destination === "/institutional/cohorts"
      ? destination : "/student";
    studentUrl.search = "";
    return copySessionState(supabaseResponse, NextResponse.redirect(studentUrl));
  }

  return supabaseResponse;
}
