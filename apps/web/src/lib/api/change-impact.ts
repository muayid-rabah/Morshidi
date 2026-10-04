import { AuthenticatedApiClient, AuthenticatedApiError } from "@/lib/api/authenticated-client";

export type ChangeType =
  | "PREREQUISITE_GROUP_CHANGE"
  | "REQUIREMENT_GROUP_CREDIT_CHANGE"
  | "COURSE_CREDIT_HOURS_CHANGE"
  | "POLICY_VERSION_CHANGE";

type Common = {
  old_version: string;
  new_version: string;
  provenance_reference: string;
};

export type ChangeDelta =
  | (Common & { change_type: "PREREQUISITE_GROUP_CHANGE"; study_plan_id: string;
      target_course_code: string; group_number: number; dependency_type: "prerequisite" | "corequisite";
      old_option_course_codes: string[]; new_option_course_codes: string[] })
  | (Common & { change_type: "REQUIREMENT_GROUP_CREDIT_CHANGE"; study_plan_id: string;
      requirement_group_code: string; old_required_credits: string; new_required_credits: string })
  | (Common & { change_type: "COURSE_CREDIT_HOURS_CHANGE"; study_plan_id: string;
      course_code: string; old_credit_hours: string; new_credit_hours: string })
  | (Common & { change_type: "POLICY_VERSION_CHANGE"; document_code: string; affected_topic: string });

export type ImpactStatus = "UNCHANGED" | "CHANGED" | "REVIEW_REQUIRED" | "UNKNOWN";

export interface ChangeImpactReport {
  change_id: string;
  change_type: ChangeType;
  change_authority: "PROPOSED_ANALYST_CHANGE";
  old_version: string;
  new_version: string;
  impact_status: ImpactStatus;
  affected_facts: { fact_type: string; reference: string; before: string | null; after: string | null }[];
  affected_decision_types: string[];
  structurally_affected_courses: string[];
  affected_requirement_groups: string[];
  comparisons: { decision_class: string; reference: string; before: string; after: string;
    status: ImpactStatus }[];
  requires_human_review: boolean;
  limitations: string[];
  audit_status: "LEDGER_PERSISTED";
  replay_status: "NOT_REPLAYABLE";
  historical_basis: "NOT_REWRITTEN";
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 404) throw new AuthenticatedApiError("VALIDATION_ERROR", 404);
  if (!response.ok) throw new AuthenticatedApiError("SERVER_ERROR", response.status);
  return await response.json() as T;
}

export class ChangeImpactApi {
  constructor(private readonly client: AuthenticatedApiClient) {}

  async access(): Promise<string[]> {
    const response = await this.client.request("/api/v1/institutional/change-impact/access");
    return (await readResponse<{ university_ids: string[] }>(response)).university_ids;
  }

  async evaluate(universityId: string, delta: ChangeDelta): Promise<ChangeImpactReport> {
    const response = await this.client.request("/api/v1/institutional/change-impact/evaluate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ university_id: universityId, delta }),
    });
    return readResponse<ChangeImpactReport>(response);
  }
}
