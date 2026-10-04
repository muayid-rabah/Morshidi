import { AuthenticatedApiClient } from "@/lib/api/authenticated-client";

export type PlanKey = [string, string, string, string, string];
export interface PlanSummary {
  plan_key: PlanKey; institution_id: string; program_id: string; major_id: string;
  plan_id: string; version_id: string; effective_from: string; effective_to: string | null;
  source_version: string; content_fingerprint: string; source_fingerprint: string;
  source: string; synthetic: boolean; label: "MODELED_UNOFFICIAL";
  display_course_codes?: Record<string, string>;
}
export interface TargetList {
  status: "AVAILABLE" | "TARGET_PLAN_UNAVAILABLE"; current: PlanSummary;
  targets: PlanSummary[]; label: "MODELED_UNOFFICIAL"; write_performed: false;
}
export interface RuleEvidence {
  rule_id: string; rule_version: string; effective_from: string; effective_to: string | null;
  source_plan_key: PlanKey; target_plan_key: PlanKey; authority: string;
  provenance: string; status: string;
}
export interface TransitionLine {
  source_course_id: string | null; target_course_id: string | null; status: string;
  recognized_credits: string; unresolved_credits: string; rule_ids: string[];
  explanation: string; rule_evidence: RuleEvidence[];
}
export interface TransitionView {
  status: "MODELED" | "EQUIVALENCY_UNRESOLVED" | "EQUIVALENCY_CONFLICT" | "REVIEW_REQUIRED";
  kind: "PLAN_VERSION_TRANSITION" | "CROSS_MAJOR_PROJECTION";
  label: "MODELED_UNOFFICIAL"; evaluated_on: string; current: PlanSummary; target: PlanSummary;
  projection: { source_plan_key: PlanKey; target_plan_key: PlanKey;
    lines: TransitionLine[]; recognized_credits: string; unresolved_credits: string;
    remaining_target_credits: string; new_requirements: string[];
    removed_requirements: string[]; changed_groups: string[];
    changed_prerequisites: string[]; fingerprint: string; label: string };
  unmapped_attempt_codes: string[]; write_performed: false; limitation: string;
}

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "TARGET_PLAN_UNAVAILABLE";
    try { const body = await response.json() as { detail?: string }; detail = body.detail ?? detail; }
    catch { /* Keep safe generic status. */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export class PlanTransitionsApi {
  constructor(private readonly client: AuthenticatedApiClient) {}
  async targets(): Promise<TargetList> {
    return decode<TargetList>(await this.client.request("/api/v1/me/plan-transitions"));
  }
  async evaluate(target_plan_key: PlanKey): Promise<TransitionView> {
    return decode<TransitionView>(await this.client.request("/api/v1/me/plan-transitions/evaluate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_plan_key }),
    }));
  }
}
