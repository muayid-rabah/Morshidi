import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import CohortsPage from "./page";

const client = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => client }));
const university = "f1000000-0000-0000-0000-000000000010";
const plan = "f1000000-0000-0000-0000-000000000023";
const cohort = { status: "SUPPRESSED", definition: { university_id: university, study_plan_id: plan,
  entry_period: "SYN-2025-FALL", period: "SYN-2026-FALL", minimum_level: 1, maximum_level: 8 },
  size: null, metrics: null, causal_limits: ["DESCRIPTIVE_ONLY", "NOT_CAUSAL", "MAY_BE_CONFOUNDED"],
  source_version: "p11-synthetic-history-v1", synthetic: true, fingerprint: "safe" };

beforeEach(() => {
  client.request.mockReset();
  client.request.mockImplementation(async (path: string) => new Response(JSON.stringify(
    path.endsWith("/access") ? { university_ids: [university] } : cohort)));
});

test("analyst-gated Arabic RTL aggregate suppresses small cell and states causal limits", async () => {
  render(<CohortsPage />);
  expect(document.querySelector("main[dir='rtl']")).toBeTruthy();
  const planInput = await screen.findByLabelText("معرّف الخطة");
  fireEvent.change(planInput, { target: { value: plan } });
  fireEvent.change(screen.getByLabelText("فترة الالتحاق"), { target: { value: "SYN-2025-FALL" } });
  fireEvent.change(screen.getByLabelText("فترة الرصد"), { target: { value: "SYN-2026-FALL" } });
  await userEvent.click(screen.getByRole("button", { name: "عرض الإجماليات" }));
  await screen.findByText("SUPPRESSED");
  expect(screen.getByText(/حُجبت الخلية/)).toBeTruthy();
  expect(screen.getAllByText(/NOT_CAUSAL/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/حجم المجموعة/)).toBeNull();
});

test("English LTR, access denial and error remain explicit", async () => {
  client.request.mockRejectedValueOnce(new Error("denied"));
  const { unmount } = render(<CohortsPage />);
  await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("button", { name: "Switch language" }));
  expect(document.querySelector("main[dir='ltr']")).toBeTruthy();
  unmount();
});

test("optional descriptive comparison never claims causality", async () => {
  client.request.mockImplementation(async (path: string) => new Response(JSON.stringify(
    path.endsWith("/access") ? { university_ids: [university] } :
      { ...cohort, status: "AVAILABLE", size: 6,
        metrics: { mean_completion_ratio: 0.6, repeated_course_count: null,
          completion_evidence_count: 6 }, comparison_period: "SYN-2025-FALL",
        comparison: { status: "DESCRIPTIVE", difference: 0.1, causal_limits: cohort.causal_limits } })));
  render(<CohortsPage />);
  await screen.findByLabelText("معرّف الخطة");
  fireEvent.change(screen.getByLabelText("معرّف الخطة"), { target: { value: plan } });
  fireEvent.change(screen.getByLabelText("فترة الالتحاق"), { target: { value: "SYN-2025-FALL" } });
  fireEvent.change(screen.getByLabelText("فترة الرصد"), { target: { value: "SYN-2026-FALL" } });
  fireEvent.change(screen.getByLabelText("فترة المقارنة (اختياري)"), { target: { value: "SYN-2025-FALL" } });
  await userEvent.click(screen.getByRole("button", { name: "عرض الإجماليات" }));
  expect(await screen.findByText(/فرق وصفي في متوسط التقدم/)).toBeTruthy();
  expect(screen.getAllByText(/NOT_CAUSAL/).length).toBeGreaterThan(0);
});
