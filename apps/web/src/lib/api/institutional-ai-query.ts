import { AuthenticatedApiClient, AuthenticatedApiError } from "@/lib/api/authenticated-client";

export type QueryResultStatus = "AVAILABLE" | "SUPPRESSED" | "INSUFFICIENT_DATA" |
  "REVIEW_REQUIRED" | "NOT_APPLICABLE";

export interface QueryResponse {
  status: "ANSWERED" | "ABSTAINED";
  interpretation: null | {
    metric_id: string; metric_label: string; metric_catalog_version: string;
    question_language: "ar" | "en"; target_period_id: string; target_period_key: string;
    study_plan_id: string; course_code: string;
  };
  result: null | {
    status: QueryResultStatus; value: number | string | null; unit: string;
    quality_flags: string[]; answer_text: string;
  };
  provenance: null | {
    catalog_version: string; prerequisite_version: string;
    demand_source_version: string; policy_version: string; computed_at: string | null;
  };
  query_fingerprint: string | null;
  limitations: string[];
  abstention_reason: string | null;
}

export interface QueryRequest {
  question: string; target_period_id: string; study_plan_id: string;
  course_code: string; university_id: string;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) throw new AuthenticatedApiError("SERVER_ERROR", response.status);
  return await response.json() as T;
}

export class InstitutionalAIQueryApi {
  constructor(private readonly client: AuthenticatedApiClient) {}

  async access(): Promise<string[]> {
    const response = await this.client.request("/api/v1/institutional/ai-query/access");
    return (await readResponse<{ university_ids: string[] }>(response)).university_ids;
  }

  async evaluate(request: QueryRequest): Promise<QueryResponse> {
    const response = await this.client.request("/api/v1/institutional/ai-query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return readResponse<QueryResponse>(response);
  }
}
