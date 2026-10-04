import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import StudentPage from "@/app/(student)/student/page";
import { AuthProvider } from "@/auth/auth-provider";
import { contentSecurityPolicy } from "../../../../next.config";
import {
  AuthenticatedApiClient,
  type SessionTokenSource,
} from "@/lib/api/authenticated-client";
import type {
  AcademicProfileResponse,
  AcademicProgressResponse,
} from "@/lib/api/student-types";
import { FakeAuthClient, fakeSession } from "@/test/fake-auth-client";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
  useSearchParams: () => new URLSearchParams(),
}));

const mockProfile: AcademicProfileResponse = {
  id: "profile-uuid-1",
  study_plan_id: "plan-uuid-123",
  reported_cumulative_gpa: 3.85,
  reported_gpa_scale: 4.0,
  reported_earned_credit_hours: 45,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

const mockProgress: AcademicProgressResponse = {
  study_plan_id: "plan-uuid-123",
  plan_total_required_credits: 132,
  completed_plan_credits: 45,
  in_progress_plan_credits: 15,
  remaining_plan_credits: 72,
  satisfied_requirement_group_count: 2,
  total_requirement_group_count: 5,
  all_modeled_plan_requirements_satisfied: false,
  requirement_groups: [
    {
      group_id: "grp-1",
      group_code: "REQ-MATH",
      name_ar: "متطلبات الرياضيات والعلوم",
      name_en: "Math & Science Requirements",
      scope: "MAJOR",
      requirement_type: "MANDATORY",
      required_credits: 18,
      listed_credits: 18,
      completed_listed_credits: 18,
      credited_toward_requirement: 18,
      in_progress_listed_credits: 0,
      remaining_required_credits: 0,
      completed_course_count: 6,
      in_progress_course_count: 0,
      attempted_not_completed_count: 0,
      not_attempted_count: 0,
      total_listed_course_count: 6,
      is_satisfied: true,
    },
    {
      group_id: "grp-2",
      group_code: "REQ-CS-CORE",
      name_ar: "متطلبات التخصص الإجبارية",
      name_en: "Core CS Requirements",
      scope: "MAJOR",
      requirement_type: "MANDATORY",
      required_credits: 60,
      listed_credits: 60,
      completed_listed_credits: 27,
      credited_toward_requirement: 27,
      in_progress_listed_credits: 15,
      remaining_required_credits: 33,
      completed_course_count: 9,
      in_progress_course_count: 5,
      attempted_not_completed_count: 0,
      not_attempted_count: 6,
      total_listed_course_count: 20,
      is_satisfied: false,
    },
  ],
  courses: [],
  reported_cumulative_gpa: 3.85,
  reported_gpa_scale: 4.0,
  reported_earned_credit_hours: 45,
};

function createMockClient(
  profileHandler: () => Response | Promise<Response>,
  progressHandler: () => Response | Promise<Response>,
  customTokens?: SessionTokenSource,
) {
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/v1/me/academic-profile")) {
      return await profileHandler();
    }
    if (url.includes("/api/v1/me/academic-progress")) {
      return await progressHandler();
    }
    return new Response(null, { status: 404 });
  });

  const source: SessionTokenSource = customTokens ?? {
    getAccessToken: vi.fn(async () => "test-token-value"),
    refreshAccessToken: vi.fn(async () => null),
    invalidateSession: vi.fn(async () => undefined),
  };

  return {
    client: new AuthenticatedApiClient(source, fetcher, "https://api.example.test"),
    fetcher,
    source,
  };
}

describe("Student Dashboard (لوحة الطالب)", () => {
  it("renders page heading, student email, academic profile, and progress successfully", async () => {
    const { client } = createMockClient(
      () => new Response(JSON.stringify(mockProfile), { status: 200 }),
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    // Verify main page heading
    const heading = await screen.findByRole("heading", { name: "لوحة الطالب", level: 1 });
    expect(heading).toBeDefined();

    // Verify authenticated user email
    expect(screen.getByText("student@example.com")).toBeDefined();

    // Verify Academic Profile Card
    const profileHeading = await screen.findByRole("heading", { name: "الملف الأكاديمي", level: 2 });
    expect(profileHeading).toBeDefined();
    expect(screen.getByText("plan-uuid-123")).toBeDefined();
    expect(screen.getByText("3.85")).toBeDefined();
    expect(screen.getByText("4")).toBeDefined();

    // Verify Academic Progress Card
    expect(screen.getByRole("heading", { name: "التقدم الأكاديمي", level: 2 })).toBeDefined();
    expect(screen.getByText("132")).toBeDefined();
    expect(screen.getByText("72")).toBeDefined();
    expect(screen.getByText("2 من 5")).toBeDefined();

    // Verify Requirement Groups breakdown
    expect(screen.getByRole("heading", { name: "تفاصيل متطلبات الخطة", level: 2 })).toBeDefined();
    expect(screen.getByText("متطلبات الرياضيات والعلوم")).toBeDefined();
    expect(screen.getByText("(REQ-MATH)")).toBeDefined();
    expect(screen.getByText("مستوفاة")).toBeDefined();
    expect(screen.getByText("متطلبات التخصص الإجبارية")).toBeDefined();
    expect(screen.getByText("(REQ-CS-CORE)")).toBeDefined();
    expect(screen.getByText("غير مستوفاة")).toBeDefined();

    // Verify SignOutButton is rendered
    expect(screen.getByRole("button", { name: "تسجيل الخروج" })).toBeDefined();
  });

  it("shows satisfied plan badge when all modeled requirements are satisfied", async () => {
    const satisfiedProgress: AcademicProgressResponse = {
      ...mockProgress,
      all_modeled_plan_requirements_satisfied: true,
    };

    const { client } = createMockClient(
      () => new Response(JSON.stringify(mockProfile), { status: 200 }),
      () => new Response(JSON.stringify(satisfiedProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const badge = await screen.findByText("مستوفاة بالكامل");
    expect(badge).toBeDefined();
  });

  it("handles 0 values correctly without replacing them with fallback", async () => {
    const zeroProfile: AcademicProfileResponse = {
      ...mockProfile,
      reported_cumulative_gpa: 0,
      reported_earned_credit_hours: 0,
    };
    const zeroProgress: AcademicProgressResponse = {
      ...mockProgress,
      completed_plan_credits: 0,
      in_progress_plan_credits: 0,
      remaining_plan_credits: 0,
    };

    const { client } = createMockClient(
      () => new Response(JSON.stringify(zeroProfile), { status: 200 }),
      () => new Response(JSON.stringify(zeroProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    await screen.findByRole("heading", { name: "الملف الأكاديمي" });
    const zeros = screen.getAllByText("0");
    expect(zeros.length).toBeGreaterThanOrEqual(4);
  });

  it("displays fallback 'غير متوفر' when profile fields are null", async () => {
    const nullProfile: AcademicProfileResponse = {
      id: "profile-uuid-null",
      study_plan_id: "plan-uuid-null",
      reported_cumulative_gpa: null,
      reported_gpa_scale: null,
      reported_earned_credit_hours: null,
      created_at: null,
      updated_at: null,
    };

    const { client } = createMockClient(
      () => new Response(JSON.stringify(nullProfile), { status: 200 }),
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    await screen.findByRole("heading", { name: "الملف الأكاديمي" });
    const fallbacks = screen.getAllByText("غير متوفر");
    expect(fallbacks.length).toBeGreaterThanOrEqual(3);
  });

  it("renders loading state with role status while fetching", async () => {
    let finishLoading: () => void = () => undefined;
    const pendingPromise = new Promise<Response>((resolve) => {
      finishLoading = () => resolve(new Response(JSON.stringify(mockProfile), { status: 200 }));
    });

    const { client } = createMockClient(
      () => pendingPromise,
      () => pendingPromise,
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    expect(screen.getByRole("status")).toBeDefined();

    const loadingMsg = await screen.findByText("جاري تحميل البيانات الأكاديمية…");
    expect(loadingMsg).toBeDefined();
    expect(screen.getByRole("status")).toBeDefined();

    finishLoading();
    await waitFor(() => {
      expect(screen.queryByRole("status")).toBeNull();
    });
  });

  it("renders 403 Forbidden state with Arabic access-denied message and no retry button", async () => {
    const { client } = createMockClient(
      () => new Response("Forbidden", { status: 403 }),
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("غير مصرح لك بالوصول إلى هذه البيانات الأكاديمية.");
    expect(screen.queryByRole("button", { name: "إعادة المحاولة" })).toBeNull();
    expect(screen.getByRole("button", { name: "تسجيل الخروج" })).toBeDefined();
  });

  it("renders 404 Missing Profile state with Arabic message and retry button", async () => {
    const { client } = createMockClient(
      () => new Response(JSON.stringify({ detail: "Student resource was not found" }), { status: 404 }),
      () => new Response(JSON.stringify({ detail: "Student resource was not found" }), { status: 404 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const notFoundText = await screen.findByText("لم يتم العثور على ملف أكاديمي");
    expect(notFoundText).toBeDefined();
    expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeDefined();
    expect(screen.getByRole("button", { name: "تسجيل الخروج" })).toBeDefined();
  });

  it("renders 422 Validation error message with retry button", async () => {
    const { client } = createMockClient(
      () => new Response("Unprocessable Entity", { status: 422 }),
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("بيانات الطلب غير صالحة.");
    expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeDefined();
  });

  it("renders 503 Service Unavailable message with retry button", async () => {
    const { client } = createMockClient(
      () => new Response("Service Unavailable", { status: 503 }),
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("الخدمة غير متوفرة حالياً. يُرجى المحاولة لاحقاً.");
    expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeDefined();
  });

  it("renders 500 Server Error message with retry button", async () => {
    const { client } = createMockClient(
      () => new Response("Internal Server Error", { status: 500 }),
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("حدث خطأ في الخادم أثناء تحميل البيانات الأكاديمية.");
    expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeDefined();
  });

  it("renders Network Error message with retry button", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("Failed to fetch");
    });
    const source: SessionTokenSource = {
      getAccessToken: vi.fn(async () => "test-token"),
      refreshAccessToken: vi.fn(async () => null),
      invalidateSession: vi.fn(async () => undefined),
    };
    const client = new AuthenticatedApiClient(source, fetcher, "https://api.example.test");

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("تعذّر الاتصال بالخادم. تحقق من اتصال الإنترنت.");
    expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeDefined();
  });

  it("re-fetches data when clicking retry button after recoverable error", async () => {
    let callCount = 0;
    const { client } = createMockClient(
      () => {
        callCount++;
        if (callCount <= 1) {
          return new Response("Server error", { status: 500 });
        }
        return new Response(JSON.stringify(mockProfile), { status: 200 });
      },
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toBeDefined();
    const retryBtn = screen.getByRole("button", { name: "إعادة المحاولة" });
    await userEvent.click(retryBtn);

    const profileHeading = await screen.findByRole("heading", { name: "الملف الأكاديمي" });
    expect(profileHeading).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("re-fetches data when clicking refresh data button in header", async () => {
    let fetchCount = 0;
    const { client } = createMockClient(
      () => {
        fetchCount++;
        return new Response(JSON.stringify(mockProfile), { status: 200 });
      },
      () => new Response(JSON.stringify(mockProgress), { status: 200 }),
    );

    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    await screen.findByRole("heading", { name: "الملف الأكاديمي" });
    expect(fetchCount).toBe(1);

    const refreshBtn = screen.getByRole("button", { name: "تحديث البيانات" });
    await userEvent.click(refreshBtn);

    await waitFor(() => {
      expect(fetchCount).toBe(2);
    });
  });

  it("wires Bearer token to both profile and progress requests", async () => {
    let capturedProfileHeaders: Headers | undefined;
    let capturedProgressHeaders: Headers | undefined;

    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/v1/me/academic-profile")) {
        capturedProfileHeaders = new Headers(init?.headers);
        return new Response(JSON.stringify(mockProfile), { status: 200 });
      }
      if (url.includes("/api/v1/me/academic-progress")) {
        capturedProgressHeaders = new Headers(init?.headers);
        return new Response(JSON.stringify(mockProgress), { status: 200 });
      }
      return new Response(null, { status: 404 });
    });

    const source: SessionTokenSource = {
      getAccessToken: vi.fn(async () => "student-jwt-abc-123"),
      refreshAccessToken: vi.fn(async () => null),
      invalidateSession: vi.fn(async () => undefined),
    };
    const client = new AuthenticatedApiClient(source, fetcher, "https://api.example.test");

    const authClient = new FakeAuthClient(fakeSession("student-jwt-abc-123"));
    render(
      <AuthProvider client={authClient}>
        <StudentPage client={client} />
      </AuthProvider>,
    );

    await screen.findByRole("heading", { name: "لوحة الطالب" });

    expect(capturedProfileHeaders?.get("Authorization")).toBe("Bearer student-jwt-abc-123");
    expect(capturedProgressHeaders?.get("Authorization")).toBe("Bearer student-jwt-abc-123");
  });

  it("shows configuration error when client cannot be initialized and is not injected", async () => {
    const authClient = new FakeAuthClient(fakeSession());
    render(
      <AuthProvider client={authClient}>
        <StudentPage />
      </AuthProvider>,
    );

    const configError = await screen.findByText("تعذّر تهيئة الاتصال بالخادم. تحقق من إعدادات النظام.");
    expect(configError).toBeDefined();
    expect(screen.getByRole("button", { name: "تسجيل الخروج" })).toBeDefined();
  });

  it("shows unauthenticated message when user is not logged in", async () => {
    const authClient = new FakeAuthClient(null);
    render(
      <AuthProvider client={authClient}>
        <StudentPage />
      </AuthProvider>,
    );

    const msg = await screen.findByText("يجب تسجيل الدخول للوصول إلى لوحة الطالب.");
    expect(msg).toBeDefined();
  });
});

describe("Content Security Policy (next.config.ts)", () => {
  it("explicitly permits backend and supabase in connect-src without wildcards", () => {
    expect(contentSecurityPolicy).toContain("https://morshidi.onrender.com");
    expect(contentSecurityPolicy).toContain("https://*.supabase.co");
    expect(contentSecurityPolicy).not.toContain("connect-src *");
  });
});
