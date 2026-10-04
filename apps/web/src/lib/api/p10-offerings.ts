import { AuthenticatedApiClient, AuthenticatedApiError } from "@/lib/api/authenticated-client";

export interface SectionView {
  section_id: string; course_code: string; status: string | null;
  modality: "IN_PERSON" | "ONLINE" | "HYBRID" | "UNKNOWN";
  campus: string | null; location: string | null;
  meetings: { day: number; starts_at: string; ends_at: string; timezone: string }[];
  capacity: number | null; enrolled: number | null; available: number | null;
  waitlist: number | null; capacity_state: string; provenance: string;
}

export interface OfferingView {
  course_code: string; academic_decision: string; operational_state: string;
  source_type: "SYNTHETIC" | "INSTITUTIONAL" | null;
  source_version: string | null; fresh_until: string | null;
  coverage_complete: boolean | null; provenance: string | null;
  sections: SectionView[];
}

export interface CapacityView {
  status: string; observed_intent_demand: number | null;
  supplied_section_capacity: number | null; seat_gap: number | null;
  demand_to_capacity_ratio: string | null; full_sections: number | null;
  unknown_capacity_sections: number | null; source_version: string | null;
  source_type: "SYNTHETIC" | "INSTITUTIONAL" | null; provenance: string | null;
  freshness_status: "FRESH" | "STALE" | "UNAVAILABLE";
  fresh_until: string | null; coverage_complete: boolean | null;
  demand_status: string; demand_quality_flags: string[]; observed_only: boolean;
  population_coverage_ratio: string | null;
}

export interface ScenarioView {
  base_fingerprint: string; scenario_fingerprint: string;
  base_supplied_seats: number | null; modeled_supplied_seats: number | null;
  seat_delta: number | null; modeled_demand_delta: number;
  section_delta: number; label: string;
  base_course_supplied_seats: number | null; modeled_course_supplied_seats: number | null;
  modeled_course_seat_delta: number | null;
  base_observed_gap: number | null; modeled_assumed_gap: number | null;
  source_type: "SYNTHETIC" | "INSTITUTIONAL"; source_version: string; provenance: string;
  freshness_status: "FRESH" | "STALE"; fresh_until: string; coverage_complete: boolean;
  demand_status: string; observed_only: boolean;
}

export interface SensitivityView {
  base_fingerprint: string; kind: "CAPACITY" | "DEMAND_DELTA" | "ADDED_SECTION_COUNT";
  base_course_supplied_seats: number | null; base_observed_demand: number | null;
  points: { assumption_value: number; scenario_fingerprint: string;
    modeled_course_supplied_seats: number | null; modeled_demand: number | null;
    modeled_gap: number | null; supply_status: string }[];
  source_type: "SYNTHETIC" | "INSTITUTIONAL"; provenance: string;
  freshness_status: "FRESH" | "STALE"; demand_status: string; label: string;
}

export interface OfferingPlannerView {
  academic_planner: { plan_options: { rank: number; courses: { course_code: string }[] }[] };
  offering_overlay: { academic_rank: number; course_codes: string[];
    selected_section_ids: string[] | null; operational_status: string;
    possible_pair_conflicts: { reason: string; first_section_id: string; second_section_id: string;
      day: number; starts_at: string | null; ends_at: string | null; timezone: string | null }[] }[];
  source_type: "SYNTHETIC" | "INSTITUTIONAL" | null;
  source_version: string | null; provenance: string | null; fresh_until: string | null;
  planning_scope: string;
}

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) throw new AuthenticatedApiError("SERVER_ERROR", response.status);
  return await response.json() as T;
}

export class P10OfferingsApi {
  constructor(private readonly client: AuthenticatedApiClient) {}

  async student(courseCode: string, periodKey: string): Promise<OfferingView> {
    const path = `/api/v1/me/offerings/${encodeURIComponent(courseCode)}?period_key=${encodeURIComponent(periodKey)}` as const;
    return decode<OfferingView>(await this.client.request(path));
  }

  async planner(periodKey: string, maxCreditHours: number): Promise<OfferingPlannerView> {
    return decode<OfferingPlannerView>(await this.client.request(
      `/api/v1/me/semester-plans/offerings?period_key=${encodeURIComponent(periodKey)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_credit_hours: maxCreditHours, max_options: 3 }),
      }));
  }

  async capacity(universityId: string, periodId: string, courseCode: string): Promise<CapacityView> {
    const params = new URLSearchParams({ university_id: universityId,
      target_period_id: periodId, course_code: courseCode });
    return decode<CapacityView>(await this.client.request(`/api/v1/institutional/capacity?${params}`));
  }

  async simulate(input: { university_id: string; target_period_id: string;
                         kind: string; section_id: string; course_code?: string; capacity?: number }): Promise<ScenarioView> {
    return decode<ScenarioView>(await this.client.request("/api/v1/institutional/capacity/simulation", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
    }));
  }

  async sensitivity(input: { university_id: string; target_period_id: string;
    kind: "CAPACITY" | "DEMAND_DELTA" | "ADDED_SECTION_COUNT";
    course_code: string; section_id?: string; start: number; stop: number;
    step: number; section_capacity?: number }): Promise<SensitivityView> {
    return decode<SensitivityView>(await this.client.request("/api/v1/institutional/capacity/sensitivity", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
    }));
  }
}
