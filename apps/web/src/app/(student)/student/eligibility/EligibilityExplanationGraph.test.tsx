import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EligibilityExplanationGraphPanel } from "./EligibilityExplanationGraph";
import type {
  EligibilityExplanationGraph, EligibilityGraphNode,
} from "@/lib/api/student-types";

function node(fields: Partial<EligibilityGraphNode> & Pick<EligibilityGraphNode, "id" | "type">): EligibilityGraphNode {
  return {
    decision: null, reason: null, course_code: null, group_number: null,
    dependency_type: null, option_course_codes: [], passed_option_course_codes: [],
    non_passed_option_course_codes: [], academic_state: null, limitation: null,
    ...fields,
  };
}

function graph(decision: "ELIGIBLE" | "NOT_ELIGIBLE" | "REVIEW_REQUIRED" = "NOT_ELIGIBLE"): EligibilityExplanationGraph {
  return {
    graph_id: `eligibility:AI402:${decision}:why`, subject_type: "ELIGIBILITY",
    subject_reference: "AI402", root_node_id: "decision:AI402", mode: "why",
    target_decision: null, generated_at: "2026-09-29T00:00:00Z",
    policy_versions: [], source_versions: [],
    limitations: ["CURRENT_STORED_STATE", "EXACT_SOURCE_VERSION_UNAVAILABLE"],
    nodes: [
      node({ id: "decision:AI402", type: "DECISION", decision }),
      node({ id: "reason:MISSING_PREREQUISITE_GROUP", type: "REASON", reason: "MISSING_PREREQUISITE_GROUP" }),
      node({ id: "prereq-group:AI402:1", type: "PREREQUISITE_GROUP", group_number: 1,
        dependency_type: "prerequisite", option_course_codes: ["CS301", "CS302"],
        passed_option_course_codes: [], non_passed_option_course_codes: ["CS301", "CS302"] }),
    ],
    edges: [
      { from_node_id: "decision:AI402", to_node_id: "reason:MISSING_PREREQUISITE_GROUP", relation: "DECIDED_BY" },
      { from_node_id: "reason:MISSING_PREREQUISITE_GROUP", to_node_id: "prereq-group:AI402:1", relation: "BLOCKED_BY" },
    ],
  };
}

function renderPanel(overrides: Partial<Parameters<typeof EligibilityExplanationGraphPanel>[0]> = {}) {
  const onRetry = vi.fn();
  const onModeChange = vi.fn();
  render(<EligibilityExplanationGraphPanel graph={graph()} mode="why" loading={false}
    error={false} canAskWhyNot onRetry={onRetry} onModeChange={onModeChange} {...overrides} />);
  return { onRetry, onModeChange };
}

describe("EligibilityExplanationGraphPanel", () => {
  it("renders Arabic decision, blocked OR options, semantic structure and limitations", () => {
    renderPanel();
    expect(screen.getByRole("heading", { name: "لماذا هذا القرار؟" })).toBeDefined();
    expect(screen.getByText("غير مؤهل")).toBeDefined();
    expect(screen.getByText("خيارات بديلة (أو)")).toBeDefined();
    expect(screen.getByText("CS301")).toBeDefined();
    expect(screen.getByText("CS302")).toBeDefined();
    expect(screen.getByText(/لا يتضمن ناتج الأهلية الحالي معرف نسخة مصدر دقيقاً/)).toBeDefined();
    expect(document.querySelector("section[dir='rtl'] ol")).not.toBeNull();
    expect(document.querySelector(".md\\:grid-cols-2")).not.toBeNull();
    expect(document.body.textContent).not.toContain("11111111-1111");
    expect(document.body.textContent).not.toContain("chain_of_thought");
    expect(document.body.textContent).not.toContain("prereq-group:AI402:1");
  });

  it("renders eligible and review decisions without changing the authoritative result", () => {
    renderPanel({ graph: graph("ELIGIBLE"), canAskWhyNot: false });
    expect(screen.getByText("مؤهل")).toBeDefined();
    expect(screen.getByRole("button", { name: "لماذا ليس مؤهلاً؟" }).hasAttribute("disabled")).toBe(true);
  });

  it("represents review-required uncertainty", () => {
    const reviewed = graph("REVIEW_REQUIRED");
    reviewed.nodes = [
      node({ id: "decision:AI402", type: "DECISION", decision: "REVIEW_REQUIRED" }),
      node({ id: "reason:PREREQUISITE_SOURCE_CONFLICT", type: "REASON", reason: "PREREQUISITE_SOURCE_CONFLICT" }),
    ];
    reviewed.edges = [];
    renderPanel({ graph: reviewed });
    expect(screen.getByText("تتطلب مراجعة")).toBeDefined();
    expect(screen.getByText("مصادر المتطلبات السابقة متعارضة")).toBeDefined();
  });

  it("shows loading, failure/retry, and empty states", async () => {
    const { rerender } = render(<EligibilityExplanationGraphPanel graph={null} mode="why"
      loading error={false} canAskWhyNot onRetry={vi.fn()} onModeChange={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toContain("جارٍ تحميل التفسير");
    const retry = vi.fn();
    rerender(<EligibilityExplanationGraphPanel graph={null} mode="why"
      loading={false} error canAskWhyNot onRetry={retry} onModeChange={vi.fn()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "إعادة المحاولة" }));
    expect(retry).toHaveBeenCalledOnce();
    rerender(<EligibilityExplanationGraphPanel graph={null} mode="why"
      loading={false} error={false} canAskWhyNot onRetry={retry} onModeChange={vi.fn()} />);
    expect(screen.getByText("لا يتوفر رسم تفسيري لهذا الفحص.")).toBeDefined();
  });

  it("supports an accessible WHY_NOT switch", async () => {
    const { onModeChange } = renderPanel();
    await userEvent.setup().click(screen.getByRole("button", { name: "لماذا ليس مؤهلاً؟" }));
    expect(onModeChange).toHaveBeenCalledWith("why_not");
    expect(screen.getByRole("group", { name: "طريقة عرض التفسير" })).toBeDefined();
  });
});
