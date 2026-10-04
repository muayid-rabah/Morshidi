import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import InstitutionalAIQueryPage from "./page";
import type { QueryResponse } from "@/lib/api/institutional-ai-query";
import { AuthenticatedApiError } from "@/lib/api/authenticated-client";

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => api }));

const tenant = "10000000-0000-0000-0000-000000000001";
const period = "20000000-0000-0000-0000-000000000002";
const plan = "30000000-0000-0000-0000-000000000003";

const answered: QueryResponse = {
  status: "ANSWERED", interpretation: {
    metric_id: "INST_SIG_DECLARED_DEMAND_COUNT", metric_label: "الطلب المعلن على المادة",
    metric_catalog_version: "WC039_METRIC_CATALOG_V1", question_language: "ar",
    target_period_id: period, target_period_key: "2026-FALL", study_plan_id: plan,
    course_code: "CS101",
  },
  result: { status: "AVAILABLE", value: 24, unit: "count", quality_flags: [],
    answer_text: "الطلب المعلن على المادة: 24 count." },
  provenance: { catalog_version: "catalog-v1", prerequisite_version: "pre-v1",
    demand_source_version: "demand-v1", policy_version: "policy-v1", computed_at: "2026-09-29" },
  query_fingerprint: "safe-fingerprint", limitations: ["OBSERVED_INTENTS_ONLY"], abstention_reason: null,
};

function response(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200,
    headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  api.request.mockReset();
  api.request.mockImplementation(async (path: string) => response(path.endsWith("/access")
    ? { university_ids: [tenant] } : answered));
});

async function ready() {
  render(<InstitutionalAIQueryPage />);
  await screen.findByLabelText("معرّف الفترة المستهدفة");
}

async function submit(question = "كم الطلب المعلن على هذه المادة؟") {
  fireEvent.change(screen.getByLabelText("معرّف الفترة المستهدفة"), { target: { value: period } });
  fireEvent.change(screen.getByLabelText("معرّف الخطة الدراسية"), { target: { value: plan } });
  fireEvent.change(screen.getByLabelText("رمز المادة"), { target: { value: "cs101" } });
  fireEvent.change(screen.getByLabelText("سؤالك عن مؤشر واحد"), { target: { value: question } });
  await userEvent.click(screen.getByRole("button", { name: "تحليل السؤال" }));
}

test("requires verified analyst access before rendering the form", async () => {
  api.request.mockRejectedValue(new AuthenticatedApiError("FORBIDDEN", 403));
  render(<InstitutionalAIQueryPage />);
  expect((await screen.findByRole("alert")).textContent).toContain("للمحلل المؤسسي");
  expect(screen.queryByLabelText("سؤالك عن مؤشر واحد")).toBeNull();
});

test("Arabic RTL form has typed scope, one question and 300-character bound", async () => {
  await ready();
  expect(document.querySelector("main[dir='rtl']")).toBeTruthy();
  expect(screen.getByLabelText("سؤالك عن مؤشر واحد").getAttribute("maxlength")).toBe("300");
  expect(screen.getByLabelText("رمز المادة")).toBeDefined();
  expect(document.querySelector("textarea")).toBeTruthy();
  expect(document.querySelector("[aria-live='polite']")).toBeTruthy();
  expect(screen.getByText(/الجامعة المصرّح بها/)).toBeDefined();
  expect(document.querySelector("select")).toBeNull();
});

test("multiple active universities get an explicit selector", async () => {
  api.request.mockImplementation(async (path: string) => response(path.endsWith("/access")
    ? { university_ids: [tenant, plan] } : answered));
  await ready();
  expect(screen.getByLabelText("الجامعة")).toBeDefined();
});

test("submits only typed scope and question, then shows interpretation, value and provenance", async () => {
  await ready();
  await submit();
  await screen.findByText(/كيف فهم مرشدي السؤال/);
  const [path, init] = api.request.mock.calls.find(call => call[0] === "/api/v1/institutional/ai-query") as [string, RequestInit];
  expect(path).toBe("/api/v1/institutional/ai-query");
  const body = JSON.parse(init.body as string);
  expect(body).toEqual({ university_id: tenant, target_period_id: period,
    study_plan_id: plan, course_code: "CS101", question: "كم الطلب المعلن على هذه المادة؟" });
  expect(screen.getByText("WC039_METRIC_CATALOG_V1")).toBeDefined();
  expect(screen.getByText("2026-09-29")).toBeDefined();
  expect(screen.getByText(/بصمة الاستعلام/)).toBeDefined();
  expect(screen.getByText(/OBSERVED_INTENTS_ONLY/)).toBeDefined();
  expect(document.body.textContent).not.toContain("trace_id");
  expect(document.body.textContent).not.toContain("student_user_id");
  expect(document.body.textContent).not.toContain("chain-of-thought");
});

test.each(["SUPPRESSED", "INSUFFICIENT_DATA", "REVIEW_REQUIRED", "NOT_APPLICABLE"] as const)(
  "renders %s without a numerical value", async (status) => {
    api.request.mockImplementation(async (path: string) => response(path.endsWith("/access")
      ? { university_ids: [tenant] }
      : { ...answered, result: { ...answered.result, status, value: null,
          answer_text: status === "SUPPRESSED" ? "unsafe 2" : "no value" } }));
    await ready();
    await submit();
    await screen.findByText(status === "SUPPRESSED"
      ? "النتيجة محجوبة وفق سياسة الإفصاح المؤسسي." : "no value");
    if (status === "SUPPRESSED") expect(document.body.textContent).not.toContain("unsafe 2");
    expect(document.body.textContent).not.toContain("24 count");
  },
);

test("abstention is a safe state and does not show individual data", async () => {
  api.request.mockImplementation(async (path: string) => response(path.endsWith("/access")
    ? { university_ids: [tenant] }
    : { status: "ABSTAINED", interpretation: null, result: null, provenance: null,
        query_fingerprint: null, limitations: [], abstention_reason: "UNSUPPORTED_QUERY" }));
  await ready();
  await submit("أعطني أسماء الطلاب ومعدلاتهم");
  expect((await screen.findByText(/لم يتمكن مرشدي/)).textContent).toContain("مؤشر مؤسسي معتمد");
  expect(screen.queryByText(/كيف فهم مرشدي السؤال/)).toBeNull();
});

test("provider/API failure shows retryable safe error", async () => {
  api.request.mockImplementation(async (path: string) => {
    if (path.endsWith("/access")) return response({ university_ids: [tenant] });
    throw new AuthenticatedApiError("SERVICE_UNAVAILABLE", 503);
  });
  await ready();
  await submit();
  expect((await screen.findByRole("alert")).textContent).toContain("إعادة المحاولة");
  await userEvent.click(screen.getByRole("button", { name: "تحليل السؤال" }));
  await waitFor(() => expect(api.request.mock.calls.filter(call => call[0] === "/api/v1/institutional/ai-query")).toHaveLength(2));
});
