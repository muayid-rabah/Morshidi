import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RecommendationsPage from "./page";
import type { RecommendationResponse } from "@/lib/api/student-types";

const getRecommendations = vi.fn();
const getAdaptiveCourseIntelligence = vi.fn();
const getRecommendationGraph = vi.fn();
const client = { request: async () => new Response("[]") };
vi.mock("@/auth/auth-provider", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@/lib/api/use-authenticated-api", () => ({ useAuthenticatedApi: () => client }));
vi.mock("@/lib/api/student-api", () => ({ StudentApiService: class {
  getRecommendations = getRecommendations;
  getAdaptiveCourseIntelligence = getAdaptiveCourseIntelligence;
  getRecommendationGraph = getRecommendationGraph;
} }));

const recommendation: RecommendationResponse = {
  study_plan_id: "synthetic-plan", recommendation_policy_version: "1.0",
  ranked_recommendations: [{
    course_code: "SYN101", course_name_ar: "مادة تجريبية", credit_hours: 3,
    requirement_group_code: "CORE", requirement_type: "required", course_state: "NOT_ATTEMPTED",
    eligibility_decision: "ELIGIBLE", effective_credit_contribution: 3,
    group_remaining_credits_before: 3, group_remaining_credits_after: 0,
    completes_requirement_group: true, newly_eligible_count: 0,
    newly_eligible_course_codes: [], rank: 1, reason_codes: [], previously_attempted: false,
  }],
  review_required_courses: [], excluded_in_progress: [], methodology_note: "Modeled only", limitations: [],
};

beforeEach(() => {
  getRecommendations.mockReset().mockResolvedValue(recommendation);
  getRecommendationGraph.mockReset().mockResolvedValue(null);
  getAdaptiveCourseIntelligence.mockReset().mockResolvedValue({
    profile: { cumulative_gpa: null, gpa_scale: null, earned_completed_credits: 0,
      completed_courses: [], grade_scale_provenance: "UNVERIFIED_GRADE_SCALE" },
    courses: [{ course_code: "SYN101", general: { score: 65, level: "HARD", provenance: "MODEL_BASED", model_version: "GENERAL_DIFFICULTY_MODEL_V1" },
      personalized: { score: 65, level: "HARD", confidence: "LOW", provenance: "MODELED_STRUCTURAL_FALLBACK_NO_GRADE_MASTERY", model_version: "PERSONAL_DIFFICULTY_MODEL_V1", reason_codes: ["UNVERIFIED_GRADE_SCALE"], contributing_skills: [], risk_factors: [] } }],
    recommendations: [{ course_code: "SYN101", rank: 1, recommendation_score: 72, confidence: "LOW" }],
  });
});

describe("student adaptive recommendation presentation", () => {
  it("shows modeled difficulty, score, and weak-evidence disclosure", async () => {
    render(<RecommendationsPage />);
    expect(await screen.findByText(/الصعوبة العامة/)).toBeTruthy();
    expect(screen.getByText(/الصعوبة المتوقعة بالنسبة لك/)).toBeTruthy();
    expect(screen.getByText(/ثقة منخفضة/)).toBeTruthy();
    expect(screen.getByText(/Modeled score: 72/)).toBeTruthy();
  });

  it("labels a generic fallback instead of silently implying personalization", async () => {
    getAdaptiveCourseIntelligence.mockRejectedValueOnce(new Error("unavailable"));
    render(<RecommendationsPage />);
    expect(await screen.findByText(/the displayed order is generic/)).toBeTruthy();
    expect(screen.getByText(/تقدير الصعوبة غير متاح حالياً/)).toBeTruthy();
  });
});
