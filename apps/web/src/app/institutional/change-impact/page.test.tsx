import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import InstitutionalChangeImpactPage from "./page";
import type { ChangeImpactReport } from "@/lib/api/change-impact";
import { AuthenticatedApiError } from "@/lib/api/authenticated-client";

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => api }));

const tenant = "10000000-0000-0000-0000-000000000001";
const report: ChangeImpactReport = {
  change_id: "safe-fingerprint", change_type: "PREREQUISITE_GROUP_CHANGE",
  change_authority: "PROPOSED_ANALYST_CHANGE", old_version: "v1", new_version: "v2",
  impact_status: "CHANGED", affected_facts: [], affected_decision_types: ["ELIGIBILITY"],
  structurally_affected_courses: ["CS401"], affected_requirement_groups: [],
  comparisons: [], requires_human_review: true,
  limitations: ["RECOMPUTATION_INPUT_UNAVAILABLE"],
  audit_status: "LEDGER_PERSISTED", replay_status: "NOT_REPLAYABLE",
  historical_basis: "NOT_REWRITTEN",
};

function response(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200,
    headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  api.request.mockReset();
  api.request.mockImplementation(async (path: string) =>
    response(path.endsWith("/access") ? { university_ids: [tenant] } :
      path.includes("/course-identities") ? [{ course_id: "course-401", course_code: "CS401",
        name_ar: "تحليل البيانات", name_en: "Data Analysis" }] : report));
});

async function ready() {
  render(<InstitutionalChangeImpactPage />);
  await screen.findByLabelText("الجامعة المصرّح بها");
}

test("requires server-verified analyst membership before showing forms", async () => {
  api.request.mockRejectedValue(new AuthenticatedApiError("FORBIDDEN", 403));
  render(<InstitutionalChangeImpactPage />);
  expect((await screen.findByRole("alert")).textContent).toContain("عضوية محلل مؤسسي");
  expect(screen.queryByRole("button", { name: "تحليل الأثر المقترح" })).toBeNull();
});

test("shows all four typed Arabic forms and never a raw JSON editor", async () => {
  await ready();
  const selector = screen.getByLabelText("نوع التغيير المقترح");
  expect(screen.getByLabelText("المتطلبات الحالية")).toBeDefined();
  fireEvent.change(selector, { target: { value: "REQUIREMENT_GROUP_CREDIT_CHANGE" } });
  expect(screen.getByLabelText("مجموعة المتطلبات")).toBeDefined();
  fireEvent.change(selector, { target: { value: "COURSE_CREDIT_HOURS_CHANGE" } });
  expect(screen.getByLabelText("الساعات المقترحة")).toBeDefined();
  fireEvent.change(selector, { target: { value: "POLICY_VERSION_CHANGE" } });
  expect(screen.getByLabelText("الوثيقة")).toBeDefined();
  expect(screen.getByLabelText("الموضوع المعلن")).toBeDefined();
  expect(document.querySelector("textarea")).toBeNull();
  expect(document.querySelector("main[dir='rtl']")).toBeTruthy();
});

test("submits typed proposal and shows bounded structural result, review and audit", async () => {
  await ready();
  fireEvent.change(screen.getByLabelText("معرّف الخطة الدراسية"),
    { target: { value: "10000000-0000-0000-0000-000000000005" } });
  fireEvent.change(screen.getByLabelText("المادة المستهدفة"), { target: { value: "CS401" } });
  fireEvent.change(screen.getByLabelText("المتطلبات الحالية"), { target: { value: "CS101" } });
  fireEvent.change(screen.getByLabelText("المتطلبات المقترحة"), { target: { value: "CS102" } });
  fireEvent.change(screen.getByLabelText("الإصدار الحالي المعلن"), { target: { value: "v1" } });
  fireEvent.change(screen.getByLabelText("الإصدار المقترح"), { target: { value: "v2" } });
  fireEvent.change(screen.getByLabelText("مرجع مصدر المقترح"), { target: { value: "review-1" } });
  await userEvent.click(screen.getByRole("button", { name: "تحليل الأثر المقترح" }));
  await screen.findByRole("heading", { name: "ملخص الأثر" });
  const request = api.request.mock.calls.find(call => call[0].endsWith("/evaluate"))!;
  expect(request[0]).toBe("/api/v1/institutional/change-impact/evaluate");
  const body = JSON.parse(request[1].body as string);
  expect(body.university_id).toBe(tenant);
  expect(body.delta.old_option_course_codes).toEqual(["CS101"]);
  expect(body.delta.new_option_course_codes).toEqual(["CS102"]);
  expect(body.delta).not.toHaveProperty("ledger_entry_id");
  expect(screen.getAllByText("CS401").length).toBeGreaterThan(0);
  expect(screen.getAllByText("تحليل البيانات").length).toBeGreaterThan(0);
  const courseLabel = screen.getAllByText("تحليل البيانات").at(-1)!.parentElement!;
  expect(courseLabel.textContent).toBe("تحليل البياناتCS401");
  expect(api.request.mock.calls.filter(call => call[0].includes("/course-identities"))).toHaveLength(1);
  expect(screen.getByText("سُجل أثر التحليل")).toBeDefined();
  expect(screen.getByText("مطلوبة")).toBeDefined();
  expect(document.body.textContent).not.toContain("تم تطبيق التغيير");
  expect(document.body.textContent).not.toContain("student_user_id");
});

test("policy change remains human review and does not invent before/after", async () => {
  api.request.mockImplementation(async (path: string) => response(path.endsWith("/access")
    ? { university_ids: [tenant] }
    : { ...report, change_type: "POLICY_VERSION_CHANGE", impact_status: "REVIEW_REQUIRED",
        structurally_affected_courses: [], comparisons: [] }));
  await ready();
  fireEvent.change(screen.getByLabelText("نوع التغيير المقترح"),
    { target: { value: "POLICY_VERSION_CHANGE" } });
  fireEvent.change(screen.getByLabelText("الوثيقة"), { target: { value: "POLICY-A" } });
  fireEvent.change(screen.getByLabelText("الموضوع المعلن"), { target: { value: "admission" } });
  fireEvent.change(screen.getByLabelText("الإصدار الحالي المعلن"), { target: { value: "v1" } });
  fireEvent.change(screen.getByLabelText("الإصدار المقترح"), { target: { value: "v2" } });
  fireEvent.change(screen.getByLabelText("مرجع مصدر المقترح"), { target: { value: "proposal" } });
  await userEvent.click(screen.getByRole("button", { name: "تحليل الأثر المقترح" }));
  expect((await screen.findByText(/تغيير نص اللائحة غير مربوط/)).textContent).toContain("مراجعة بشرية");
  expect(screen.queryByRole("heading", { name: "مقارنات محسوبة فعليًا" })).toBeNull();
});

test.each(["UNCHANGED", "UNKNOWN", "REVIEW_REQUIRED"] as const)(
  "shows text-only %s status", async (status) => {
    api.request.mockImplementation(async (path: string) => response(path.endsWith("/access")
      ? { university_ids: [tenant] } : { ...report, impact_status: status }));
    await ready();
    fireEvent.change(screen.getByLabelText("نوع التغيير المقترح"),
      { target: { value: "POLICY_VERSION_CHANGE" } });
    fireEvent.change(screen.getByLabelText("الوثيقة"), { target: { value: "POLICY-A" } });
    fireEvent.change(screen.getByLabelText("الموضوع المعلن"), { target: { value: "admission" } });
    fireEvent.change(screen.getByLabelText("الإصدار الحالي المعلن"), { target: { value: "v1" } });
    fireEvent.change(screen.getByLabelText("الإصدار المقترح"), { target: { value: "v2" } });
    fireEvent.change(screen.getByLabelText("مرجع مصدر المقترح"), { target: { value: "proposal" } });
    await userEvent.click(screen.getByRole("button", { name: "تحليل الأثر المقترح" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "ملخص الأثر" })).toBeDefined());
    expect(screen.getByText(status === "UNCHANGED" ? "لا تغيير في النتيجة المحسوبة"
      : status === "UNKNOWN" ? "الأثر غير معروف بسبب نقص البيانات" : "تتطلب مراجعة بشرية")).toBeDefined();
  },
);

test("audit failure does not show a successful report and permits resubmission", async () => {
  api.request.mockImplementationOnce(async () => response({ university_ids: [tenant] }))
    .mockResolvedValueOnce(response([]))
    .mockRejectedValueOnce(new AuthenticatedApiError("SERVICE_UNAVAILABLE", 503))
    .mockResolvedValueOnce(response({ ...report, change_type: "POLICY_VERSION_CHANGE" }));
  await ready();
  fireEvent.change(screen.getByLabelText("نوع التغيير المقترح"),
    { target: { value: "POLICY_VERSION_CHANGE" } });
  fireEvent.change(screen.getByLabelText("الوثيقة"), { target: { value: "POLICY-A" } });
  fireEvent.change(screen.getByLabelText("الموضوع المعلن"), { target: { value: "admission" } });
  fireEvent.change(screen.getByLabelText("الإصدار الحالي المعلن"), { target: { value: "v1" } });
  fireEvent.change(screen.getByLabelText("الإصدار المقترح"), { target: { value: "v2" } });
  fireEvent.change(screen.getByLabelText("مرجع مصدر المقترح"), { target: { value: "proposal" } });
  const submit = screen.getByRole("button", { name: "تحليل الأثر المقترح" });
  await userEvent.click(submit);
  expect((await screen.findByRole("alert")).textContent).toContain("سجل التدقيق");
  expect(screen.queryByRole("heading", { name: "ملخص الأثر" })).toBeNull();
  await userEvent.click(submit);
  expect(await screen.findByRole("heading", { name: "ملخص الأثر" })).toBeDefined();
});
