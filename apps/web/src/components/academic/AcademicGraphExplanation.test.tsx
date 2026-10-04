import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AcademicGraphExplanation } from "./AcademicGraphExplanation";
import { courseIdentityMap } from "@/lib/api/use-course-identities";
import type {
  AcademicExplanationGraph, EligibilityGraphNode, EligibilityGraphNodeType,
} from "@/lib/api/student-types";

function node(id: string, type: EligibilityGraphNodeType, facts: EligibilityGraphNode["facts"] = []): EligibilityGraphNode {
  return {
    id, type, facts, decision: null, reason: null, course_code: null,
    group_number: null, dependency_type: null, option_course_codes: [],
    passed_option_course_codes: [], non_passed_option_course_codes: [],
    academic_state: null, limitation: null,
  };
}

const graph: AcademicExplanationGraph = {
  graph_id: "recommendations:why:stable", subject_type: "COURSE_RECOMMENDATIONS",
  subject_reference: "current", root_node_id: "recommendations:result", mode: "why",
  target_decision: null, generated_at: "2026-09-29T00:00:00Z",
  policy_versions: ["1.0"], source_versions: [],
  limitations: ["SOURCE_DOCUMENT_VERSION_UNAVAILABLE"],
  nodes: [
    node("recommendations:result", "RECOMMENDATION"),
    node("recommendation:1:CS401", "RECOMMENDATION", [
      { key: "RANK", value: 1 }, { key: "EFFECTIVE_CREDIT_CONTRIBUTION", value: "3" },
      { key: "STATUS", value: "RANKED" },
    ]),
    { ...node("course:CS401", "COURSE"), course_code: "CS401" },
    node("constraint:eligibility", "CONSTRAINT", [{ key: "ELIGIBILITY_DECISION", value: "ELIGIBLE" }]),
    node("policy-version:1.0", "POLICY_VERSION", [{ key: "POLICY_VERSION", value: "1.0" }]),
  ],
  edges: [
    { from_node_id: "recommendation:1:CS401", to_node_id: "course:CS401", relation: "REFERENCES" },
    { from_node_id: "recommendation:1:CS401", to_node_id: "constraint:eligibility", relation: "CONSTRAINED_BY" },
    { from_node_id: "recommendation:1:CS401", to_node_id: "policy-version:1.0", relation: "VERSIONED_BY" },
  ],
};

describe("AcademicGraphExplanation", () => {
  it("shows canonical name before code without rewriting trace node identity", () => {
    const before = JSON.stringify(graph);
    render(<AcademicGraphExplanation graph={graph} focusId="recommendation:1:CS401"
      identities={courseIdentityMap([{ course_id: "id-401", course_code: "CS401",
        name_ar: "تحليل البيانات", name_en: "Data Analysis" }])}
      loading={false} error={false} onRetry={vi.fn()} />);
    expect(screen.getByText("تحليل البيانات").parentElement!.textContent).toBe("تحليل البياناتCS401");
    expect(JSON.stringify(graph)).toBe(before);
  });
  it("renders Arabic typed facts, constraints, version and relationship labels without IDs", () => {
    const { container } = render(<AcademicGraphExplanation graph={graph} focusId="recommendation:1:CS401"
      loading={false} error={false} onRetry={vi.fn()} />);
    expect(screen.getByRole("region", { name: "لماذا هذه النتيجة؟" })).toBeDefined();
    expect(screen.getByText("مساهمة الساعات الفعلية:")).toBeDefined();
    expect(screen.getByText("مقيّد بـ")).toBeDefined();
    expect(screen.getByText("نسخة سياسة المحرك:")).toBeDefined();
    expect(container.firstElementChild?.getAttribute("dir")).toBe("rtl");
    expect(container.firstElementChild?.className).toContain("min-w-0");
    expect(container.textContent).not.toContain("recommendation:1:CS401");
    expect(container.textContent).not.toContain("chain_of_thought");
  });

  it("renders modeled path-to-semester hierarchy and uncertainty", () => {
    const pathGraph: AcademicExplanationGraph = {
      ...graph, subject_type: "DEGREE_PATH", root_node_id: "degree-path:result",
      nodes: [
        node("degree-path:result", "DEGREE_PATH"),
        node("degree-path:1", "DEGREE_PATH", [{ key: "RANK", value: 1 }, { key: "STATUS", value: "HORIZON_REACHED" }]),
        node("degree-path:1:semester:1:option:1", "SEMESTER", [{ key: "SEMESTER_INDEX", value: 1 }]),
        { ...node("course:CS401", "COURSE"), course_code: "CS401" },
      ],
      edges: [
        { from_node_id: "degree-path:1", to_node_id: "degree-path:1:semester:1:option:1", relation: "SELECTED_IN" },
        { from_node_id: "degree-path:1:semester:1:option:1", to_node_id: "course:CS401", relation: "SELECTED_IN" },
      ],
      limitations: ["MODELED_OUTCOME_NOT_HISTORICAL"],
    };
    render(<AcademicGraphExplanation graph={pathGraph} focusId="degree-path:1"
      loading={false} error={false} onRetry={vi.fn()} />);
    expect(screen.getByText("بلغ حد الفصول")).toBeDefined();
    expect(screen.getByText("الفصل النموذجي:")).toBeDefined();
    expect(screen.getByText(/المواد والفصول المستقبلية نموذجية/)).toBeDefined();
  });

  it("announces loading, safe empty and error with keyboard retry", async () => {
    const retry = vi.fn();
    const props = { graph: null, focusId: "none", onRetry: retry };
    const view = render(<AcademicGraphExplanation {...props} loading error={false} />);
    expect(screen.getByRole("status")).toBeDefined();
    view.rerender(<AcademicGraphExplanation {...props} loading={false} error />);
    expect(screen.getByRole("alert")).toBeDefined();
    await userEvent.setup().click(screen.getByRole("button", { name: "إعادة المحاولة" }));
    expect(retry).toHaveBeenCalledOnce();
    view.rerender(<AcademicGraphExplanation {...props} loading={false} error={false} />);
    expect(screen.getByText("لا تتوفر تفاصيل تفسيرية لهذا العنصر.")).toBeDefined();
  });
});
