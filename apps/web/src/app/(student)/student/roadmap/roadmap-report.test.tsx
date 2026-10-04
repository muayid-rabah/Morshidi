import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RoadmapPage from "./page";
import ReportPage from "../report/page";
import type { AcademicRoadmapResponse } from "@/lib/api/student-types";

const getRoadmap = vi.fn();
const getAdaptiveCourseIntelligence = vi.fn();
const generateModeledRoadmap = vi.fn();
const getModeledReport = vi.fn();
const stableClient = { request: async () => new Response(JSON.stringify([
  { course_id: "syn-1", course_code: "SYN101", name_ar: "مقدمة تجريبية", name_en: "Synthetic Introduction" },
  { course_id: "syn-2", course_code: "SYN102", name_ar: "دراسة متقدمة", name_en: "Synthetic Advanced" },
])) };
vi.mock("@/auth/auth-provider", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => stableClient }));
vi.mock("@/lib/api/student-api", () => ({ StudentApiService: class { getRoadmap = getRoadmap; getAdaptiveCourseIntelligence = getAdaptiveCourseIntelligence; generateModeledRoadmap = generateModeledRoadmap; getModeledReport = getModeledReport; } }));

const roadmap: AcademicRoadmapResponse = {
  study_plan_id: "synthetic-plan", plan_number: "SYN-1", effective_year: 2026,
  plan_updated_at: "2026-09-01T00:00:00Z", generated_at: "2026-09-30T00:00:00Z",
  plan_total_required_credits: 6, completed_plan_credits: 3, in_progress_plan_credits: 0, remaining_plan_credits: 3,
  courses: [
    { course_code: "SYN101", name_ar: "مقدمة تجريبية", name_en: "Synthetic Introduction", credit_hours: 3,
      requirement_group_code: "CORE", state: "COMPLETED", reasons: ["NO_PREREQUISITES"], missing_prerequisite_groups: [],
      prerequisite_logic_status: "not_applicable", structural_criticality: true, structural_impact_count: 1, planned_semester: null,
      planned_order: null, critical_path: false, critical_path_reason: null, critical_path_length: 0, critical_path_downstream_codes: [], critical_path_evidence_chain: [] },
    { course_code: "SYN102", name_ar: "دراسة متقدمة", name_en: "Synthetic Advanced", credit_hours: 3,
      requirement_group_code: "CORE", state: "BLOCKED", reasons: ["MISSING_PREREQUISITE_GROUP"], missing_prerequisite_groups: [["SYN101"]],
      prerequisite_logic_status: "verified", structural_criticality: false, structural_impact_count: 0, planned_semester: null,
      planned_order: null, critical_path: true, critical_path_reason: "MAXIMAL_UNFINISHED_REQUIRED_PREREQUISITE_CHAIN", critical_path_length: 1, critical_path_downstream_codes: [], critical_path_evidence_chain: ["SYN102"] },
  ],
  edges: [{ prerequisite_code: "SYN101", target_code: "SYN102", dependency_type: "prerequisite", group_number: 1, option_count: 1 }],
  limitations: ["Modeled only"],
  snapshot_fingerprint: "synthetic-fingerprint", snapshot_contract_version: "P9_ROADMAP_INPUT_V1",
  critical_path_policy_version: "P9_REQUIRED_PREREQUISITE_CHAIN_V1", modeling_status: "NOT_REQUESTED",
  modeled_plan_policy_version: null, source_type: "synthetic", source_retrieved_at: "2026-09-01T00:00:00Z",
  source_content_hash: "synthetic-hash", source_snapshot_ref: null, source_status: "active",
};

beforeEach(() => {
  getRoadmap.mockReset(); getRoadmap.mockResolvedValue(roadmap);
  getAdaptiveCourseIntelligence.mockReset(); getAdaptiveCourseIntelligence.mockResolvedValue({ courses: roadmap.courses.map((item) => ({
    course_code: item.course_code, general: { score: 64, level: "HARD", provenance: "MODEL_BASED", model_version: "GENERAL_DIFFICULTY_MODEL_V1" },
    personalized: { score: 56, level: "MODERATE", confidence: "LOW", provenance: "MODELED_STRUCTURAL_FALLBACK_NO_GRADE_MASTERY", model_version: "PERSONAL_DIFFICULTY_MODEL_V1", reason_codes: ["INSUFFICIENT_VERIFIED_GRADE_EVIDENCE"], contributing_skills: [], risk_factors: [] },
  })) });
  generateModeledRoadmap.mockReset(); generateModeledRoadmap.mockResolvedValue({ ...roadmap, modeling_status: "MODELED_PATH" });
  getModeledReport.mockReset(); getModeledReport.mockResolvedValue({ ...roadmap, report_schema_version: "P9_MODELED_REPORT_V1",
    modeled_state_marker: "MODELED_UNOFFICIAL", content_fingerprint: "synthetic-report-fingerprint" });
});

describe("P9 student roadmap", () => {
  it("does not model on load and renders explicitly requested planned evidence", async () => {
    const user = userEvent.setup();
    generateModeledRoadmap.mockResolvedValueOnce({ ...roadmap, modeling_status: "MODELED_PATH",
      courses: roadmap.courses.map((course) => course.course_code === "SYN102" ?
        { ...course, state: "PLANNED", planned_semester: 2, planned_order: 1 } : course) });
    render(<RoadmapPage />);
    await screen.findByRole("heading", { level: 1 });
    expect(generateModeledRoadmap).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Switch to English" }));
    expect(screen.getByText(/No modeled path has been generated/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Generate modeled path" }));
    await waitFor(() => expect(generateModeledRoadmap).toHaveBeenCalledOnce());
    expect(await screen.findByText(/Planned courses are modeled/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /Synthetic Advanced/ }));
    expect(screen.getByText(/order 1/)).toBeTruthy();
    expect(screen.getByText(/Structural critical path/)).toBeTruthy();
  });
  it("renders Arabic RTL, state legend, keyboard-selectable course details and English LTR", async () => {
    const user = userEvent.setup();
    const { container } = render(<RoadmapPage />);
    expect(await screen.findByRole("heading", { name: "خارطتي الأكاديمية" })).toBeTruthy();
    expect(container.querySelector("section[lang='ar'][dir='rtl']")).not.toBeNull();
    expect(screen.getByRole("button", { name: /مقدمة تجريبية/ })).toBeTruthy();
    expect(screen.getAllByText(/الصعوبة العامة/).length).toBeGreaterThan(0);
    screen.getByRole("button", { name: /دراسة متقدمة/ }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("heading", { name: /دراسة متقدمة/ })).toBeTruthy();
    expect(screen.getAllByText("SYN101").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Switch to English" }));
    expect(container.querySelector("section[lang='en'][dir='ltr']")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "My academic roadmap" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Synthetic Advanced/ })).toBeTruthy();
  });

  it("shows empty and retryable error states", async () => {
    getRoadmap.mockResolvedValueOnce({ ...roadmap, courses: [] });
    const { unmount } = render(<RoadmapPage />);
    expect(await screen.findByText("لا توجد مواد في هذه الخطة أو لا توجد نتائج مطابقة.")).toBeTruthy();
    unmount();
    getRoadmap.mockRejectedValueOnce(new Error("network"));
    render(<RoadmapPage />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "إعادة المحاولة" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "خارطتي الأكاديمية" })).toBeTruthy());
  });
});

describe("P9 modeled report", () => {
  it("states unofficial status in Arabic and English and exposes print structure", async () => {
    const user = userEvent.setup();
    const { container } = render(<ReportPage />);
    expect(await screen.findByRole("heading", { name: /تقرير أكاديمي مُنمذج/ })).toBeTruthy();
    expect(container.querySelector("article[lang='ar'][dir='rtl']")).not.toBeNull();
    expect(screen.getByText(/ليس كشف علامات/)).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("SYN-1")).toBeTruthy();
    expect(screen.getByRole("button", { name: "طباعة / حفظ PDF" })).toBeTruthy();
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    await user.click(screen.getByRole("button", { name: "طباعة / حفظ PDF" }));
    expect(print).toHaveBeenCalledOnce();
    print.mockRestore();
    await user.click(screen.getByRole("button", { name: "Switch to English" }));
    expect(container.querySelector("article[lang='en'][dir='ltr']")).not.toBeNull();
    expect(screen.getByRole("heading", { name: /Modeled Academic Report/ })).toBeTruthy();
    expect(screen.getByText(/No graduation date is guaranteed/)).toBeTruthy();
    expect(getModeledReport).toHaveBeenCalledOnce();
    expect(getRoadmap).not.toHaveBeenCalled();
    expect(screen.getByText("synthetic-report-fingerprint")).toBeTruthy();
  });
});
