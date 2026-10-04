import { AuthenticatedApiClient, AuthenticatedApiError } from "@/lib/api/authenticated-client";

export interface SkillItem {
  skill_id: string; name_ar: string; name_en: string;
  state: "NOT_EVIDENCED" | "EXPOSED" | "EVIDENCED";
  source_courses: string[]; evidence_dates: Record<string, string | null>;
  mapping_provenance: string[]; limitation: string;
}
export interface StudentIntelligenceView {
  source_type: "SYNTHETIC" | "UNAVAILABLE"; validation_status: string;
  strength_difficulty: { strengths: { status: string; policy_version: string;
    signals: { rule_id: string; value: string; count: number | null; course_codes: string[] }[];
    limitations: string[] }; difficulty: { status: string; policy_version: string;
    signals: { rule_id: string; value: string; count: number | null; course_codes: string[] }[];
    limitations: string[] } }; risk: string; limitation: string;
  workload: { status: "RANGE" | "UNKNOWN"; low_hours_per_week: number | null;
    high_hours_per_week: number | null; coverage: string; uncertainty: string;
    source_version: string | null; assumptions: string[]; synthetic: boolean };
  skills: { status: "AVAILABLE" | "UNRESOLVED"; taxonomy_version: string | null;
    source_at?: string; synthetic?: boolean; items: SkillItem[]; limitation: string };
  careers: { career_id: string; title_ar: string; title_en: string; status: string;
    evidenced: string[]; exposed: string[]; gaps: string[]; unresolved: string[];
    stale: boolean; source_at: string; source_version: string; synthetic: boolean;
    uncertainty: string; limitation: string }[];
  internships: { partner_id: string; title_ar: string; title_en: string;
    status: "READY" | "GAP" | "UNRESOLVED"; expires_at: string;
    source_version: string; synthetic: boolean; limitation: string;
    criteria: { criterion_id: string; requirement_ar: string; requirement_en: string;
      status: string; evidence: string | null }[] }[];
}

export interface CohortView {
  status: "AVAILABLE" | "SUPPRESSED" | "UNAVAILABLE";
  definition: { university_id: string; study_plan_id: string; entry_period: string;
    period: string; minimum_level: number; maximum_level: number };
  size?: number | null; metrics?: { completion_distribution: Record<string, number> | null;
    repeated_course_count: number | null; observed_structural_signal_count: number | null;
    mean_completion_ratio: number | null; completion_evidence_count: number;
    credit_load_evidence_count: number } | null;
  causal_limits: string[]; source_version: string | null; synthetic?: boolean;
  provenance?: string; fingerprint: string | null;
  comparison_period?: string; comparison?: { status: "DESCRIPTIVE" | "UNAVAILABLE";
    difference: number | null; causal_limits: string[] };
}

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) throw new AuthenticatedApiError("SERVER_ERROR", response.status);
  return await response.json() as T;
}

export class P11IntelligenceApi {
  constructor(private readonly client: AuthenticatedApiClient) {}
  async student(): Promise<StudentIntelligenceView> {
    return decode<StudentIntelligenceView>(await this.client.request("/api/v1/me/intelligence"));
  }
  async cohort(scope: { university_id: string; study_plan_id: string;
    entry_period: string; period: string; comparison_period?: string }): Promise<CohortView> {
    const query = new URLSearchParams(scope).toString();
    return decode<CohortView>(await this.client.request(`/api/v1/institutional/cohorts?${query}`));
  }
}
