import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import CapacityPage from "./page";

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => api }));
const university = "f1000000-0000-0000-0000-000000000010";
const period = "f1000000-0000-0000-0000-000000000012";

beforeEach(() => {
  api.request.mockReset();
  api.request.mockImplementation(async (path: string) => new Response(JSON.stringify(
    path.endsWith("/access") ? { university_ids: [university] } :
    path.includes("/sensitivity") ? { base_fingerprint: "base", kind: "CAPACITY",
      base_course_supplied_seats: 60, base_observed_demand: null,
      points: [{ assumption_value: 30, scenario_fingerprint: "one",
        modeled_course_supplied_seats: 60, modeled_demand: null, modeled_gap: null,
        supply_status: "DEMAND_UNAVAILABLE" }], source_type: "SYNTHETIC",
      provenance: "SANDBOX / SYNTHETIC DATA", freshness_status: "FRESH",
      demand_status: "SUPPRESSED", label: "MODELLED SENSITIVITY ONLY" } :
    path.includes("/simulation") ? { base_fingerprint: "base", scenario_fingerprint: "scenario",
      base_supplied_seats: null, modeled_supplied_seats: null, seat_delta: null,
      modeled_demand_delta: 0, section_delta: 1, label: "MODELLED ASSUMPTIONS ONLY",
      base_course_supplied_seats: 60, modeled_course_supplied_seats: 90,
      modeled_course_seat_delta: 30, base_observed_gap: 5, modeled_assumed_gap: -25 } :
      { status: "AVAILABLE", observed_intent_demand: 65, supplied_section_capacity: 60,
        seat_gap: 5, demand_to_capacity_ratio: "1.0833", full_sections: 1,
        unknown_capacity_sections: 0, source_version: "p10-synthetic-v1",
        source_type: "SYNTHETIC", provenance: "SANDBOX / SYNTHETIC DATA",
        freshness_status: "FRESH", fresh_until: "2027-09-01", coverage_complete: true,
        demand_status: "PARTIAL", demand_quality_flags: [], observed_only: true,
        population_coverage_ratio: null }), { status: 200 }));
});

test("bounded sensitivity view keeps suppressed demand unknown", async () => {
  render(<CapacityPage />);
  fireEvent.click(screen.getByRole("button", { name: "Switch language" }));
  await screen.findByLabelText("University ID");
  fireEvent.change(screen.getByLabelText("Period ID"), { target: { value: period } });
  fireEvent.change(screen.getByLabelText("Course code"), { target: { value: "CS101" } });
  fireEvent.click(screen.getByRole("button", { name: "Compare demand and supply" }));
  await screen.findByText("5");
  fireEvent.change(screen.getByLabelText("Existing section ID"), { target: { value: "SYN-CS101-A" } });
  fireEvent.click(screen.getByRole("button", { name: "Compare modeled capacities" }));
  expect((await screen.findByText("MODELLED SENSITIVITY ONLY")).textContent).toContain("MODELLED");
  expect(screen.getByText(/gap: UNKNOWN \/ SUPPRESSED/)).toBeTruthy();
  const body = JSON.parse(api.request.mock.calls.find(call => call[0].includes("/sensitivity"))![1].body as string);
  expect(body).toMatchObject({ kind: "CAPACITY", section_id: "SYN-CS101-A",
    start: 30, stop: 50, step: 10 });
});

test("analyst gate precedes institutional forms", async () => {
  api.request.mockRejectedValue(new Error("denied"));
  render(<CapacityPage />);
  expect((await screen.findByRole("alert")).textContent).toContain("عضوية محلل مؤسسي");
  expect(screen.queryByRole("button", { name: "عرض المقارنة" })).toBeNull();
});

test("Arabic RTL capacity metrics and modeled scenario labeling", async () => {
  render(<CapacityPage />);
  await screen.findByLabelText("معرّف الجامعة");
  fireEvent.change(screen.getByLabelText("معرّف الفصل"), { target: { value: period } });
  fireEvent.change(screen.getByLabelText("رمز المادة"), { target: { value: "cs101" } });
  fireEvent.click(screen.getByRole("button", { name: "عرض المقارنة" }));
  expect((await screen.findByText("5")).textContent).toBe("5");
  fireEvent.change(screen.getByLabelText("رمز الشعبة الافتراضية"), { target: { value: "CS101-C" } });
  fireEvent.click(screen.getByRole("button", { name: "شغّل المحاكاة" }));
  expect((await screen.findByText("MODELLED ASSUMPTIONS ONLY")).textContent).toContain("MODELLED");
  expect(document.querySelector("main[dir='rtl']")).toBeTruthy();
  const body = JSON.parse(api.request.mock.calls.find(call => call[0].includes("/simulation"))![1].body as string);
  expect(body.section_id).toBe("MODELLED-CS101-C");
  expect(body.university_id).toBe(university);
});

test("English LTR and privacy suppression do not display a demand value", async () => {
  api.request.mockImplementation(async (path: string) => new Response(JSON.stringify(
    path.endsWith("/access") ? { university_ids: [university] } :
      { status: "SUPPRESSED", observed_intent_demand: null, supplied_section_capacity: null,
        seat_gap: null, full_sections: 0, unknown_capacity_sections: 0, source_version: null }), { status: 200 }));
  render(<CapacityPage />);
  fireEvent.click(screen.getByRole("button", { name: "Switch language" }));
  await screen.findByLabelText("University ID");
  fireEvent.change(screen.getByLabelText("Period ID"), { target: { value: period } });
  fireEvent.change(screen.getByLabelText("Course code"), { target: { value: "CS101" } });
  fireEvent.click(screen.getByRole("button", { name: "Compare demand and supply" }));
  expect((await screen.findByText("Demand suppressed for privacy.")).textContent).toContain("privacy");
  expect(document.querySelector("main[dir='ltr']")).toBeTruthy();
});

test("stale capacity source is visibly warned", async () => {
  api.request.mockImplementation(async (path: string) => new Response(JSON.stringify(
    path.endsWith("/access") ? { university_ids: [university] } :
      { status: "INCOMPLETE_OR_STALE_SUPPLY", observed_intent_demand: 65,
        supplied_section_capacity: null, seat_gap: null, full_sections: null,
        unknown_capacity_sections: null, source_version: "old",
        source_type: "SYNTHETIC", provenance: "SANDBOX / SYNTHETIC DATA",
        freshness_status: "STALE", fresh_until: "2026-01-01", coverage_complete: false,
        demand_status: "PARTIAL", demand_quality_flags: [], observed_only: true,
        population_coverage_ratio: null }), { status: 200 }));
  render(<CapacityPage />);
  await screen.findByLabelText("معرّف الجامعة");
  fireEvent.change(screen.getByLabelText("معرّف الفصل"), { target: { value: period } });
  fireEvent.change(screen.getByLabelText("رمز المادة"), { target: { value: "CS101" } });
  fireEvent.click(screen.getByRole("button", { name: "عرض المقارنة" }));
  expect((await screen.findByRole("alert")).textContent).toContain("قديم");
});
