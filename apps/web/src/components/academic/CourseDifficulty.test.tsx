import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CourseDifficulty } from "./CourseDifficulty";

const modeled = {
  course_code: "SYN101",
  general: { score: 68, level: "HARD", provenance: "MODEL_BASED", model_version: "GENERAL_DIFFICULTY_MODEL_V1" },
  personalized: { score: 55, level: "MODERATE", confidence: "LOW", provenance: "MODELED_STRUCTURAL_FALLBACK_NO_GRADE_MASTERY", model_version: "PERSONAL_DIFFICULTY_MODEL_V1", reason_codes: ["INSUFFICIENT_VERIFIED_GRADE_EVIDENCE"], contributing_skills: [], risk_factors: [] },
};

describe("modeled course difficulty", () => {
  it("shows general, personal, and low-confidence labels in Arabic", () => {
    render(<CourseDifficulty course={modeled} />);
    expect(screen.getByText(/الصعوبة العامة/)).toBeTruthy();
    expect(screen.getByText(/الصعوبة المتوقعة بالنسبة لك/)).toBeTruthy();
    expect(screen.getByText(/ثقة منخفضة/)).toBeTruthy();
  });

  it("shows English labels and an honest unavailable state", () => {
    const { rerender } = render(<CourseDifficulty course={modeled} locale="en" />);
    expect(screen.getByText(/General difficulty/)).toBeTruthy();
    expect(screen.getByText(/Estimated difficulty for you/)).toBeTruthy();
    rerender(<CourseDifficulty course={undefined} locale="en" />);
    expect(screen.getByText("Difficulty estimate unavailable")).toBeTruthy();
  });
});
