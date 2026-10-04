import {
  AuthenticatedApiClient,
  AuthenticatedApiError,
} from "@/lib/api/authenticated-client";
import type {
  AcademicProfileResponse,
  AdaptiveCourseResponse,
  AcademicProgressResponse,
  AcademicRoadmapResponse,
  ModeledAcademicReportResponse,
  AdvisorRequest,
  AdvisorResponse,
  ConversationThread, ConversationMessage, ConversationReply,
  CreditTimelineRequest, CreditTimelineResponse, CreditComparisonResponse,
  AttemptCreateRequest,
  AttemptUpdateRequest,
  CanTakeDecisionResponse,
  EligibilityExplanationGraph,
  EligibilityGraphMode,
  AcademicExplanationGraph,
  CourseAttemptResponse,
  DegreePathRequest,
  DegreePathResponse,
  RecommendationResponse,
  SemesterPlanRequest,
  SemesterPlannerResponse,
  StudentIntentResponse,
  StudentPolicyDocumentDetail,
  StudentPolicyDocumentSummary,
  StudentPolicyAnswerResponse,
  StudentPolicySearchResult,
  StudentDecisionHistoryItem,
  StudentDecisionHistoryDetail,
  SubmitIntentRequest,
  WithdrawIntentRequest,
} from "@/lib/api/student-types";

async function parseJson<T>(response: Response): Promise<T> {
  if (response.status === 404) {
    throw new Error("NOT_FOUND");
  }
  if (!response.ok) {
    if (response.status === 403) throw new AuthenticatedApiError("FORBIDDEN", 403);
    if (response.status === 422) throw new AuthenticatedApiError("VALIDATION_ERROR", 422);
    if (response.status === 503) throw new AuthenticatedApiError("SERVICE_UNAVAILABLE", 503);
    if (response.status >= 500) throw new AuthenticatedApiError("SERVER_ERROR", response.status);
    throw new Error(`HTTP_${response.status}`);
  }
  return (await response.json()) as T;
}

export class StudentApiService {
  constructor(private readonly client: AuthenticatedApiClient) {}

  async getProfile(): Promise<AcademicProfileResponse> {
    const res = await this.client.request("/api/v1/me/academic-profile");
    return parseJson<AcademicProfileResponse>(res);
  }

  async getProgress(): Promise<AcademicProgressResponse> {
    const res = await this.client.request("/api/v1/me/academic-progress");
    return parseJson<AcademicProgressResponse>(res);
  }

  async listAttempts(): Promise<CourseAttemptResponse[]> {
    const res = await this.client.request("/api/v1/me/academic-profile/attempts");
    return parseJson<CourseAttemptResponse[]>(res);
  }

  async createAttempt(data: AttemptCreateRequest): Promise<CourseAttemptResponse> {
    const res = await this.client.request("/api/v1/me/academic-profile/attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return parseJson<CourseAttemptResponse>(res);
  }

  async updateAttempt(
    attemptId: string,
    data: AttemptUpdateRequest,
  ): Promise<CourseAttemptResponse> {
    const res = await this.client.request(
      `/api/v1/me/academic-profile/attempts/${encodeURIComponent(attemptId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      },
    );
    return parseJson<CourseAttemptResponse>(res);
  }

  async deleteAttempt(attemptId: string): Promise<void> {
    const res = await this.client.request(
      `/api/v1/me/academic-profile/attempts/${encodeURIComponent(attemptId)}`,
      { method: "DELETE" },
    );
    if (res.status !== 204 && !res.ok) {
      if (res.status === 404) throw new Error("NOT_FOUND");
      throw new Error(`HTTP_${res.status}`);
    }
  }

  async checkEligibility(courseCode: string): Promise<CanTakeDecisionResponse> {
    const res = await this.client.request(
      `/api/v1/me/eligibility/${encodeURIComponent(courseCode.trim().toUpperCase())}`,
    );
    return parseJson<CanTakeDecisionResponse>(res);
  }

  async getRecommendations(limit?: number): Promise<RecommendationResponse> {
    const query = limit ? `?limit=${encodeURIComponent(limit)}` : "";
    const res = await this.client.request(
      `/api/v1/me/course-recommendations${query}`,
    );
    return parseJson<RecommendationResponse>(res);
  }

  async getAdaptiveCourseIntelligence(): Promise<AdaptiveCourseResponse> {
    const res = await this.client.request("/api/v1/me/adaptive-course-intelligence", { cache: "no-store" });
    return parseJson<AdaptiveCourseResponse>(res);
  }

  async getRoadmap(): Promise<AcademicRoadmapResponse> {
    const res = await this.client.request("/api/v1/me/academic-roadmap", { cache: "no-store" });
    return parseJson<AcademicRoadmapResponse>(res);
  }

  async generateModeledRoadmap(request: DegreePathRequest, signal?: AbortSignal): Promise<AcademicRoadmapResponse> {
    const res = await this.client.request("/api/v1/me/academic-roadmap/modeled-path", {
      method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    return parseJson<AcademicRoadmapResponse>(res);
  }

  async getModeledReport(): Promise<ModeledAcademicReportResponse> {
    const res = await this.client.request("/api/v1/me/academic-report", { cache: "no-store" });
    return parseJson<ModeledAcademicReportResponse>(res);
  }

  async getRecommendationGraph(limit?: number): Promise<AcademicExplanationGraph> {
    const query = limit ? `?limit=${encodeURIComponent(limit)}` : "";
    const res = await this.client.request(`/api/v1/me/course-recommendations/explanation-graph${query}`);
    return parseJson<AcademicExplanationGraph>(res);
  }

  async createSemesterPlans(
    request: SemesterPlanRequest,
  ): Promise<SemesterPlannerResponse> {
    const res = await this.client.request("/api/v1/me/semester-plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return parseJson<SemesterPlannerResponse>(res);
  }

  async createSemesterPlanGraph(request: SemesterPlanRequest): Promise<AcademicExplanationGraph> {
    const res = await this.client.request("/api/v1/me/semester-plans/explanation-graph", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    return parseJson<AcademicExplanationGraph>(res);
  }

  async createDegreePaths(
    request: DegreePathRequest,
    signal?: AbortSignal,
  ): Promise<DegreePathResponse> {
    const res = await this.client.request("/api/v1/me/degree-paths", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const data = await parseJson<DegreePathResponse>(res);
    if (!data || !Array.isArray(data.paths) || data.paths.some((path) =>
      !path || !Array.isArray(path.semesters) || path.semesters.some((semester) =>
        !semester || !semester.plan_option || !Array.isArray(semester.plan_option.courses) ||
        !Array.isArray(semester.newly_satisfied_requirement_group_codes)
      )
    )) throw new Error("INVALID_DEGREE_PATH_RESPONSE");
    return data;
  }

  async createDegreePathGraph(request: DegreePathRequest): Promise<AcademicExplanationGraph> {
    const res = await this.client.request("/api/v1/me/degree-paths/explanation-graph", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
    return parseJson<AcademicExplanationGraph>(res);
  }

  async getCurrentMockRegistration(
    targetPeriodId: string,
  ): Promise<StudentIntentResponse> {
    const res = await this.client.request(
      `/api/v1/me/mock-registration/current?target_period_id=${encodeURIComponent(targetPeriodId)}`,
    );
    return parseJson<StudentIntentResponse>(res);
  }

  async submitMockRegistration(
    request: SubmitIntentRequest,
  ): Promise<StudentIntentResponse> {
    const res = await this.client.request("/api/v1/me/mock-registration/revisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return parseJson<StudentIntentResponse>(res);
  }

  async withdrawMockRegistration(
    request: WithdrawIntentRequest,
  ): Promise<StudentIntentResponse> {
    const res = await this.client.request(
      "/api/v1/me/mock-registration/withdrawals",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      },
    );
    return parseJson<StudentIntentResponse>(res);
  }

  async askAdvisor(request: AdvisorRequest, signal?: AbortSignal): Promise<AdvisorResponse> {
    const res = await this.client.request("/api/v1/me/advisor", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return parseJson<AdvisorResponse>(res);
  }

  async listPolicies(): Promise<StudentPolicyDocumentSummary[]> {
    const res = await this.client.request("/api/v1/me/policies");
    return parseJson<StudentPolicyDocumentSummary[]>(res);
  }

  async getPolicyDetail(documentId: string): Promise<StudentPolicyDocumentDetail> {
    const res = await this.client.request(`/api/v1/me/policies/${encodeURIComponent(documentId)}`);
    return parseJson<StudentPolicyDocumentDetail>(res);
  }

  async listConversations(offset = 0): Promise<ConversationThread[]> {
    return parseJson<ConversationThread[]>(await this.client.request(
      `/api/v1/me/conversations?offset=${offset}`, { cache: "no-store" }));
  }

  async createConversation(title = "New conversation"): Promise<ConversationThread> {
    return parseJson<ConversationThread>(await this.client.request("/api/v1/me/conversations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }),
    }));
  }

  async getConversationMessages(id: string, offset = 0): Promise<ConversationMessage[]> {
    return parseJson<ConversationMessage[]>(await this.client.request(
      `/api/v1/me/conversations/${encodeURIComponent(id)}/messages?offset=${offset}`, { cache: "no-store" }));
  }

  async continueConversation(id: string, message: string, signal?: AbortSignal): Promise<ConversationReply> {
    return parseJson<ConversationReply>(await this.client.request(
      `/api/v1/me/conversations/${encodeURIComponent(id)}/messages`, {
        method: "POST", signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      }));
  }

  async archiveConversation(id: string): Promise<ConversationThread> {
    return parseJson<ConversationThread>(await this.client.request(
      `/api/v1/me/conversations/${encodeURIComponent(id)}/archive`, { method: "POST" }));
  }

  async getConversationPreferences(): Promise<Record<string, string>> {
    return parseJson<Record<string, string>>(await this.client.request(
      "/api/v1/me/conversations/preferences", { cache: "no-store" }));
  }

  async simulateCreditTimeline(request: CreditTimelineRequest): Promise<CreditTimelineResponse> {
    const result = await parseJson<CreditTimelineResponse>(await this.client.request(
      "/api/v1/me/degree-paths/credit-timeline", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
      }));
    if (!result || !Array.isArray(result.terms) || !Array.isArray(result.warnings)) {
      throw new Error("Malformed credit timeline response");
    }
    return result;
  }

  async compareCreditTimelines(request: {
    start_year: number; start_term: CreditTimelineRequest["start_term"];
    preferred_regular_load?: number; preferred_summer_enabled?: boolean;
    preferred_summer_load?: number;
    graduation_pace?: "FASTEST" | "BALANCED" | "LOWER_LOAD";
  }): Promise<CreditComparisonResponse> {
    const result = await parseJson<CreditComparisonResponse>(await this.client.request(
      "/api/v1/me/degree-paths/credit-comparison", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      }));
    if (!result || !Array.isArray(result.scenarios) || result.scenarios.length !== 3) {
      throw new Error("Malformed credit comparison response");
    }
    return result;
  }

  async getEligibilityExplanationGraph(
    courseCode: string, mode: EligibilityGraphMode = "why",
  ): Promise<EligibilityExplanationGraph> {
    const query = mode === "why_not" ? "?mode=why_not&target=ELIGIBLE" : "?mode=why";
    const res = await this.client.request(
      `/api/v1/me/eligibility/${encodeURIComponent(courseCode.trim().toUpperCase())}/explanation-graph${query}`,
    );
    return parseJson<EligibilityExplanationGraph>(res);
  }

  async searchPolicies(query: string, limit = 10, mode: "lexical" | "semantic" | "hybrid" = "lexical"): Promise<StudentPolicySearchResult[]> {
    const res = await this.client.request(`/api/v1/me/policies/search?q=${encodeURIComponent(query)}&limit=${limit}&mode=${mode}`);
    return parseJson<StudentPolicySearchResult[]>(res);
  }

  async answerPolicyQuestion(question: string, limit = 6): Promise<StudentPolicyAnswerResponse> {
    const res = await this.client.request("/api/v1/me/policies/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, limit }),
    });
    return parseJson<StudentPolicyAnswerResponse>(res);
  }

  async listDecisionHistory(
    limit = 20,
    before?: Pick<StudentDecisionHistoryItem, "created_at" | "ledger_entry_id">,
  ): Promise<StudentDecisionHistoryItem[]> {
    const query = new URLSearchParams({ limit: String(limit) });
    if (before) {
      query.set("before_created_at", before.created_at);
      query.set("before_entry_id", before.ledger_entry_id);
    }
    const res = await this.client.request(`/api/v1/me/decision-history?${query}`);
    return parseJson<StudentDecisionHistoryItem[]>(res);
  }

  async getDecisionHistoryEntry(ledgerEntryId: string): Promise<StudentDecisionHistoryDetail> {
    const res = await this.client.request(
      `/api/v1/me/decision-history/${encodeURIComponent(ledgerEntryId)}`,
    );
    return parseJson<StudentDecisionHistoryDetail>(res);
  }
}
