import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import PlanTransitionPage from "./page";

const client = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => client }));

const current = { plan_key: ["test-inst", "program", "major-a", "plan", "v1"],
  institution_id: "test-inst", program_id: "program", major_id: "major-a", plan_id: "plan", version_id: "v1",
  effective_from: "2025-01-01", effective_to: null, source_version: "source-v1",
  content_fingerprint: "first", source_fingerprint: "source-first", source: "isolated-test", synthetic: true,
  label: "MODELED_UNOFFICIAL" };
const target = { ...current, plan_key: ["test-inst", "program", "major-b", "plan", "v2"],
  major_id: "major-b", version_id: "v2", content_fingerprint: "second" };
const listing = { status: "AVAILABLE", current, targets: [target], label: "MODELED_UNOFFICIAL", write_performed: false };
const projection = { status: "EQUIVALENCY_UNRESOLVED", kind: "CROSS_MAJOR_PROJECTION",
  label: "MODELED_UNOFFICIAL", evaluated_on: "2026-10-01", current, target, write_performed: false,
  limitation: "NOT_OFFICIAL_REGISTRAR_APPROVAL", unmapped_attempt_codes: [],
  projection: { source_plan_key: current.plan_key, target_plan_key: target.plan_key,
    lines: [{ source_course_id: "a", target_course_id: "b", status: "EQUIVALENT",
      recognized_credits: "3", unresolved_credits: "0", rule_ids: ["eq-1"], explanation: "Modeled",
      rule_evidence: [{ rule_id: "eq-1", rule_version: "v1", effective_from: "2025-01-01",
        effective_to: null, source_plan_key: current.plan_key, target_plan_key: target.plan_key,
        authority: "isolated-test", provenance: "test-source", status: "APPROVED" }] }],
    recognized_credits: "3", unresolved_credits: "0", remaining_target_credits: "3",
    new_requirements: ["c"], removed_requirements: ["old"], changed_groups: [],
    changed_prerequisites: [], fingerprint: "result", label: "MODELED_UNOFFICIAL_NO_WRITE" } };

beforeEach(() => {
  client.request.mockReset();
  client.request.mockImplementation(async (path: string) => new Response(JSON.stringify(
    path.endsWith("course-identities") ? [
      { course_id: "a", course_code: "CS101", name_ar: "مقدمة", name_en: "Introduction" },
      { course_id: "b", course_code: "CS201", name_ar: "مادة متقدمة", name_en: "Advanced course" },
    ] : path.endsWith("evaluate") ? projection : listing)));
});

test("Arabic-first modeled page uses server targets and shows no-write evidence", async () => {
  render(<PlanTransitionPage />);
  expect(document.querySelector("main[dir='rtl']")).toBeTruthy();
  expect(screen.getByText(/مقارنة نموذجية غير رسمية/)).toBeTruthy();
  await screen.findByText("plan / v1");
  await userEvent.click(screen.getByRole("button", { name: /عرض المقارنة النموذجية/ }));
  expect(await screen.findByText(/إسقاط انتقال تخصص نموذجي/)).toBeTruthy();
  expect(screen.getByText(/eq-1/)).toBeTruthy();
  expect(screen.getByText(/للقراءة فقط/)).toBeTruthy();
  expect(client.request).toHaveBeenCalledWith("/api/v1/me/plan-transitions/evaluate",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ target_plan_key: target.plan_key }) }));
  expect(await screen.findByText("مقدمة")).toBeTruthy();
  expect(screen.getByText("CS101")).toBeTruthy();
});

test("English mode keeps unofficial warning and review state", async () => {
  render(<PlanTransitionPage />);
  await screen.findByText("plan / v1");
  await userEvent.click(screen.getByRole("button", { name: "Switch language" }));
  expect(document.querySelector("main[dir='ltr']")).toBeTruthy();
  expect(screen.getByText(/MODELED \/ UNOFFICIAL/)).toBeTruthy();
  await userEvent.click(screen.getByRole("button", { name: "View modeled comparison" }));
  expect(await screen.findByText(/This result requires human review/)).toBeTruthy();
  expect(screen.getByText(/Read-only/)).toBeTruthy();
  expect(await screen.findByText("Introduction")).toBeTruthy();
});

test("unavailable target and API error do not offer a write action", async () => {
  client.request.mockReset();
  client.request.mockResolvedValueOnce(new Response(JSON.stringify({ ...listing, status: "TARGET_PLAN_UNAVAILABLE", targets: [] })));
  render(<PlanTransitionPage />);
  await screen.findByText(/لا تتوفر خطط مستهدفة/);
  expect(screen.queryByRole("button", { name: /عرض المقارنة النموذجية/ })).toBeNull();
});
