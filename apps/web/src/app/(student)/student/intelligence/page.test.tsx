import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import StudentIntelligencePage from "./page";

const client = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => client }));

const example = {
  source_type: "SYNTHETIC", validation_status: "NOT_VALIDATED_FOR_REAL_STUDENTS",
  strength_difficulty: { strengths: { status: "AVAILABLE", policy_version: "1.0",
    signals: [{ rule_id: "STRENGTH-002", value: "RECOVERY_EVIDENCE", count: 1, course_codes: ["CS101"] }],
    limitations: ["Not a trait"] }, difficulty: { status: "INSUFFICIENT_DATA", policy_version: "1.0",
    signals: [], limitations: ["Not ability"] } }, risk: "NOT_EXPOSED_TO_STUDENTS",
  limitation: "NO_ACADEMIC_DECISION_OVERRIDE",
  workload: { status: "RANGE", low_hours_per_week: 6, high_hours_per_week: 9,
    coverage: "HIGH", uncertainty: "NOT_CALIBRATED_FOR_REAL_STUDENTS",
    source_version: "p11-workload-v1", assumptions: [], synthetic: true },
  skills: { status: "AVAILABLE", taxonomy_version: "p11-taxonomy-v1", synthetic: true,
    limitation: "NO_MASTERY_ASSESSMENT", items: [
      { skill_id: "SYN-CODE", name_ar: "البرمجة", name_en: "Programming", state: "EVIDENCED",
        source_courses: ["CS101"], evidence_dates: { CS101: "2026-09-01" },
        mapping_provenance: ["SYNTHETIC_MAPPING"], limitation: "COURSE_EVIDENCE_NOT_SKILL_MASTERY" },
    ] },
  careers: [{ career_id: "SYN-SOFTWARE", title_ar: "مطوّر تجريبي", title_en: "Fictional developer",
    status: "DESCRIPTIVE_ONLY", evidenced: ["SYN-CODE"], exposed: [], gaps: ["SYN-QUANT"], unresolved: [],
    stale: false, source_at: "2026-09-01", source_version: "p11-career-v1", synthetic: true,
    uncertainty: "NOT_VALIDATED_FOR_CAREER_FIT", limitation: "NO_EMPLOYMENT_PROBABILITY_OR_PROMISE" }],
  internships: [{ partner_id: "SYN-PARTNER", title_ar: "تدريب تجريبي", title_en: "Fictional internship",
    status: "GAP", expires_at: "2027-09-01", source_version: "p11-criteria-v1", synthetic: true,
    limitation: "MODELED_READINESS_NOT_PLACEMENT_ELIGIBILITY", criteria: [
      { criterion_id: "SYN-C1", requirement_ar: "دليل كمي", requirement_en: "Quantitative evidence", status: "GAP", evidence: null },
    ] }],
};

beforeEach(() => { client.request.mockReset(); client.request.mockResolvedValue(new Response(JSON.stringify(example))); });

test("Arabic RTL view shows synthetic provenance, bounded range, skills and gaps", async () => {
  render(<StudentIntelligencePage />);
  expect(screen.getByRole("status").textContent).toContain("تحميل");
  await screen.findByText(/بيانات تجريبية اصطناعية/);
  expect(document.querySelector("main[dir='rtl']")).toBeTruthy();
  expect(screen.getByText(/6–9/)).toBeTruthy();
  expect(screen.getByText(/البرمجة/)).toBeTruthy();
  expect(screen.getByText(/SYN-QUANT/)).toBeTruthy();
  expect(screen.getByText(/تعافٍ بعد تعثر سابق/)).toBeTruthy();
  expect(screen.getByText(/لا تُعرض هنا إشارات خطر/)).toBeTruthy();
  expect(client.request).toHaveBeenCalledWith("/api/v1/me/intelligence");
});

test("English LTR view preserves uncertainty and no-placement caveat", async () => {
  render(<StudentIntelligencePage />);
  await screen.findByText(/بيانات تجريبية اصطناعية/);
  await userEvent.click(screen.getByRole("button", { name: "Switch language" }));
  expect(document.querySelector("main[dir='ltr']")).toBeTruthy();
  expect(screen.getByText(/Programming/)).toBeTruthy();
  expect(screen.getByText(/employment nor placement eligibility/)).toBeTruthy();
});

test("unavailable and error states are explicit", async () => {
  client.request.mockResolvedValueOnce(new Response(JSON.stringify({ ...example, source_type: "UNAVAILABLE",
    workload: { ...example.workload, status: "UNKNOWN" },
    skills: { ...example.skills, status: "UNRESOLVED", items: [] }, careers: [], internships: [] })));
  const { unmount } = render(<StudentIntelligencePage />);
  expect((await screen.findAllByText(/لا تتوفر بيانات معتمدة/)).length).toBeGreaterThan(0);
  unmount();
  client.request.mockRejectedValueOnce(new Error("offline"));
  render(<StudentIntelligencePage />);
  await screen.findByRole("alert");
});
