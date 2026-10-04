import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import OfferingsPage from "./page";

const api = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => api }));

const payload = {
  course_code: "CS101", academic_decision: "ELIGIBLE", operational_state: "SECTION_OPEN",
  source_type: "SYNTHETIC", source_version: "p10-synthetic-v1", fresh_until: "2027-09-01",
  coverage_complete: true, provenance: "SANDBOX / SYNTHETIC DATA",
  sections: [{ section_id: "SYN-CS101-A", course_code: "CS101", status: "OPEN",
    modality: "IN_PERSON", campus: "FICTIONAL-CAMPUS", location: "SYNTHETIC-ROOM",
    meetings: [{ day: 1, starts_at: "09:00", ends_at: "11:00", timezone: "Asia/Amman" }],
    capacity: 30, enrolled: 10, available: null, waitlist: null,
    capacity_state: "KNOWN_OPEN", provenance: "SYNTHETIC_SANDBOX_FACT" }],
};

beforeEach(() => {
  api.request.mockReset();
  api.request.mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
});

test("Arabic RTL student view renders synthetic section and academic/operational separation", async () => {
  render(<OfferingsPage />);
  expect(document.querySelector("main[dir='rtl']")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("رمز المادة"), { target: { value: "cs101" } });
  fireEvent.change(screen.getByLabelText("الفصل"), { target: { value: "SANDBOX-P10-FALL" } });
  fireEvent.click(screen.getByRole("button", { name: "عرض الشُعب" }));
  expect((await screen.findByText(/SANDBOX \/ SYNTHETIC DATA/)).textContent).toContain("غير رسمية");
  expect(screen.getByText(/SYN-CS101-A/)).toBeDefined();
  expect(screen.getByText(/الأهلية الأكاديمية/)).toBeDefined();
  expect(api.request.mock.calls[0][0]).toContain("/api/v1/me/offerings/CS101");
});

test("English LTR, stale warning, and provider failure states", async () => {
  api.request.mockResolvedValueOnce(new Response(JSON.stringify({ ...payload,
    operational_state: "SNAPSHOT_STALE" }), { status: 200 }));
  render(<OfferingsPage />);
  fireEvent.click(screen.getByRole("button", { name: "Switch language" }));
  expect(document.querySelector("main[dir='ltr']")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Course code"), { target: { value: "CS101" } });
  fireEvent.change(screen.getByLabelText("Period"), { target: { value: "P10" } });
  fireEvent.click(screen.getByRole("button", { name: "Show sections" }));
  expect((await screen.findByRole("alert")).textContent).toContain("stale");
});

test("failed provider request does not claim course is unavailable", async () => {
  api.request.mockRejectedValueOnce(new Error("network"));
  render(<OfferingsPage />);
  fireEvent.change(screen.getByLabelText("رمز المادة"), { target: { value: "CS101" } });
  fireEvent.change(screen.getByLabelText("الفصل"), { target: { value: "P10" } });
  fireEvent.click(screen.getByRole("button", { name: "عرض الشُعب" }));
  expect((await screen.findByRole("alert")).textContent).toContain("لا يعني ذلك عدم طرح المادة");
});

test("empty complete snapshot remains a scoped observation, not an official non-offering claim", async () => {
  api.request.mockResolvedValueOnce(new Response(JSON.stringify({ ...payload,
    operational_state: "NO_MATCHING_OFFERING", sections: [] }), { status: 200 }));
  render(<OfferingsPage />);
  fireEvent.change(screen.getByLabelText("رمز المادة"), { target: { value: "CS101" } });
  fireEvent.change(screen.getByLabelText("الفصل"), { target: { value: "P10" } });
  fireEvent.click(screen.getByRole("button", { name: "عرض الشُعب" }));
  expect((await screen.findByText(/ليس تأكيداً رسمياً بعدم طرح المادة/)).textContent).toContain("ليس تأكيداً");
});

test("explicit planner overlay renders typed timetable conflict without changing academic rank", async () => {
  api.request.mockResolvedValueOnce(new Response(JSON.stringify({
    academic_planner: { plan_options: [{ rank: 1, courses: [{ course_code: "CS101" }, { course_code: "MATH101" }] }] },
    offering_overlay: [{ academic_rank: 1, course_codes: ["CS101", "MATH101"],
      selected_section_ids: null, operational_status: "NO_CONFIRMED_SET_OR_INCOMPLETE_DATA",
      possible_pair_conflicts: [{ reason: "TIME_OVERLAP", first_section_id: "SYN-CS101-A",
        second_section_id: "SYN-MATH101-A", day: 1, starts_at: "10:00", ends_at: "11:00",
        timezone: "Asia/Amman" }] }],
    source_type: "SYNTHETIC", source_version: "v1", provenance: "SANDBOX / SYNTHETIC DATA",
    fresh_until: "2027-09-01", planning_scope: "ACADEMIC_RESULT_PLUS_EXPLICIT_OPERATIONAL_OVERLAY",
  }), { status: 200 }));
  render(<OfferingsPage />);
  fireEvent.change(screen.getByLabelText("الفصل"), { target: { value: "SANDBOX-P10-FALL" } });
  fireEvent.click(screen.getByRole("button", { name: "مقارنة الخطة الأكاديمية بالعروض" }));
  expect((await screen.findByText(/TIME_OVERLAP/)).textContent).toContain("SYN-MATH101-A");
  expect(screen.getByText("CS101")).toBeDefined();
  expect(screen.getByText("MATH101")).toBeDefined();
  expect(api.request.mock.calls[0][0]).toContain("/api/v1/me/semester-plans/offerings");
});
