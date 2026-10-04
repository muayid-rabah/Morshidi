import { AuthenticatedApiClient } from "@/lib/api/authenticated-client";

export interface ConsentView {
  consent_id: string; purpose: string; consent_version: string; policy_reference: string;
  scopes: string[]; status: string; granted_at: string; withdrawn_at: string | null;
}
export interface RequestView {
  request_id: string; kind: string; category: string; status: string;
  retained_reason: string | null; effective_at: string | null;
}
export interface StudyView {
  study_id: string; title_ar: string; title_en: string; version: string;
  consent_version: string; label: string;
  tasks: { task_id: string; instruction_ar: string; instruction_en: string; accessibility_note: string }[];
}
export interface PrivacySummary {
  status: "LOCAL_MODEL_ONLY"; purposes: string[]; consents: ConsentView[];
  participation: { study_id: string; status: string }[];
  requests: RequestView[]; feedback: { feedback_id: string; study_id: string }[];
  retention: { category: string; period: string; status: string }[];
  study_label: string; limitations: string[];
}

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`PRIVACY_UNAVAILABLE_${response.status}`);
  return response.json() as Promise<T>;
}

export class PrivacyP14Api {
  constructor(private readonly client: AuthenticatedApiClient) {}
  private async post<T>(path: string, body?: object): Promise<T> {
    return decode<T>(await this.client.request(`/api/v1/me/privacy${path}`, {
      method: "POST", ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
    }));
  }
  async summary(): Promise<PrivacySummary> {
    return decode<PrivacySummary>(await this.client.request("/api/v1/me/privacy"));
  }
  async studies(): Promise<{ studies: StudyView[] }> {
    return decode<{ studies: StudyView[] }>(await this.client.request("/api/v1/me/privacy/studies"));
  }
  grant(study: StudyView): Promise<ConsentView> {
    return this.post("/consents", { study_id: study.study_id });
  }
  withdraw(consentId: string): Promise<ConsentView> { return this.post(`/consents/${encodeURIComponent(consentId)}/withdraw`); }
  join(studyId: string): Promise<unknown> { return this.post(`/studies/${encodeURIComponent(studyId)}/join`); }
  feedback(studyId: string, values: { clarity: number; usefulness: number; understanding: number;
    workload: number; accessibility_issue: boolean }): Promise<unknown> {
    return this.post(`/studies/${encodeURIComponent(studyId)}/feedback`, values);
  }
  request(kind: "CORRECTION" | "DELETION", category: string, reason: string): Promise<RequestView> {
    return this.post("/requests", { kind, category, reason });
  }
  requestChatDeletion(threadId: string, reason: string): Promise<RequestView> {
    return this.post("/requests", { kind: "DELETION", category: "DELETABLE_OPTIONAL_DATA",
      source_kind: "CONVERSATION_THREAD", source_reference: threadId, reason });
  }
  export(): Promise<object> { return this.post("/export"); }
}
