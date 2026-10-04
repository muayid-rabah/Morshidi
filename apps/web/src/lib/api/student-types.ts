export type AttemptOutcome = "PASSED" | "FAILED" | "IN_PROGRESS" | "WITHDRAWN";

export type RecordSource =
  | "manual_entry"
  | "transcript_import"
  | "university_integration"
  | "admin_correction";

export type CourseProgressState =
  | "COMPLETED"
  | "IN_PROGRESS"
  | "ATTEMPTED_NOT_COMPLETED"
  | "NOT_ATTEMPTED";

export type RequirementType = "required" | "elective" | "MANDATORY" | "ELECTIVE";

export type Decision = "ELIGIBLE" | "NOT_ELIGIBLE" | "REVIEW_REQUIRED";

export type PrerequisiteLogicStatus =
  | "not_applicable"
  | "verified"
  | "unresolved"
  | "source_conflict";

export type DependencyType = "prerequisite" | "corequisite";

export type DecisionReason =
  | "NO_PREREQUISITES"
  | "PREREQUISITES_SATISFIED"
  | "MISSING_PREREQUISITE_GROUP"
  | "PREREQUISITE_LOGIC_UNRESOLVED"
  | "PREREQUISITE_SOURCE_CONFLICT"
  | "VERIFIED_PREREQUISITE_MODEL_INCOMPLETE"
  | "TARGET_ALREADY_COMPLETED"
  | "TARGET_CURRENTLY_ENROLLED"
  | string;

export interface AcademicProfileResponse {
  id: string;
  study_plan_id: string;
  reported_cumulative_gpa: number | null;
  reported_gpa_scale: number | null;
  reported_earned_credit_hours: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProfileCreateRequest {
  study_plan_id: string;
  reported_cumulative_gpa?: number | null;
  reported_gpa_scale?: number | null;
  reported_earned_credit_hours?: number | null;
}

export interface ProfileUpdateRequest {
  reported_cumulative_gpa?: number | null;
  reported_gpa_scale?: number | null;
  reported_earned_credit_hours?: number | null;
}

export interface CourseAttemptResponse {
  id: string;
  course_code: string;
  course_name_ar?: string | null;
  course_name_en?: string | null;
  status: AttemptOutcome;
  attempt_sequence: number | null;
  term_label: string | null;
  attempted_on: string | null;
  raw_grade_text: string | null;
  record_source: RecordSource;
  created_at: string;
  updated_at: string;
}

export interface AttemptCreateRequest {
  course_code: string;
  status: AttemptOutcome;
  attempt_sequence?: number | null;
  term_label?: string | null;
  attempted_on?: string | null;
  raw_grade_text?: string | null;
  record_source?: RecordSource;
}

export interface AttemptUpdateRequest {
  status?: AttemptOutcome;
  attempt_sequence?: number | null;
  term_label?: string | null;
  attempted_on?: string | null;
  raw_grade_text?: string | null;
  record_source?: RecordSource;
}

export interface RequirementGroupProgressResponse {
  group_id: string;
  group_code: string;
  name_ar: string;
  name_en: string | null;
  scope: string;
  requirement_type: string;
  required_credits: number;
  listed_credits: number;
  completed_listed_credits: number;
  credited_toward_requirement: number;
  in_progress_listed_credits: number;
  remaining_required_credits: number;
  completed_course_count: number;
  in_progress_course_count: number;
  attempted_not_completed_count: number;
  not_attempted_count: number;
  total_listed_course_count: number;
  is_satisfied: boolean;
}

export interface CourseProgressResponse {
  course_code: string;
  course_name_ar?: string | null;
  course_name_en?: string | null;
  credit_hours: number;
  requirement_group_id: string | null;
  requirement_group_code: string | null;
  state: CourseProgressState | string;
}

export interface AcademicProgressResponse {
  study_plan_id: string;
  plan_total_required_credits: number;
  completed_plan_credits: number;
  in_progress_plan_credits: number;
  remaining_plan_credits: number;
  satisfied_requirement_group_count: number;
  total_requirement_group_count: number;
  all_modeled_plan_requirements_satisfied: boolean;
  requirement_groups: RequirementGroupProgressResponse[];
  courses: CourseProgressResponse[];
  reported_cumulative_gpa: number | null;
  reported_gpa_scale: number | null;
  reported_earned_credit_hours: number | null;
}

export interface TargetAttemptStateResponse {
  has_passed_target: boolean;
  has_in_progress_target: boolean;
}

export interface DependencyGroupEvidenceResponse {
  group_number: number;
  dependency_type: DependencyType;
  option_course_codes: string[];
  passed_option_course_codes: string[];
  non_passed_option_course_codes: string[];
}

export interface CanTakeDecisionResponse {
  kind: "decision";
  decision: Decision;
  study_plan_id: string;
  target_course_code: string;
  prerequisite_logic_status: PrerequisiteLogicStatus;
  target_attempt_state: TargetAttemptStateResponse;
  satisfied_dependency_groups: DependencyGroupEvidenceResponse[];
  missing_dependency_groups: DependencyGroupEvidenceResponse[];
  reasons: DecisionReason[];
  review_reasons: DecisionReason[];
  raw_prerequisite_text: string | null;
  target_name_ar: string | null;
  target_name_en?: string | null;
  academic_rule_traces?: Array<{ rule_id: string; rule_version: string; provenance: string;
    required_credits: number; earned_completed_credits: number | null; result: string;
    reason_ar: string; reason_en: string }>;
}

export interface AdaptiveCourseResponse {
  profile: {
    cumulative_gpa: number | null; gpa_scale: number | null; gpa_provenance: string;
    grade_scale_version: string | null; grade_scale_provenance: string;
    earned_completed_credits: number; completed_courses: string[]; strong_courses: string[];
    weak_courses: string[]; academic_stage: string; freshness: string;
  };
  courses: Array<{ course_code: string; course_name_ar?: string | null; general: { score: number; level: string; provenance: string; model_version: string };
    personalized: { score: number; level: string; confidence: string; provenance: string;
      model_version: string; reason_codes: string[];
      contributing_skills: string[]; risk_factors: string[] } }>;
  recommendations: Array<{ course_code: string; rank: number; recommendation_score: number;
    eligible: boolean; fit_score: number; confidence: string; deterministic_reasons: string[];
    risk_factors: string[] }>;
  model_version: string;
  limitations: string[];
}

export type RoadmapState = "COMPLETED" | "IN_PROGRESS" | "ELIGIBLE" | "BLOCKED" | "PLANNED" | "REVIEW_REQUIRED";

export interface RoadmapCourse {
  course_code: string;
  name_ar: string;
  name_en: string | null;
  credit_hours: number;
  requirement_group_code: string;
  state: RoadmapState;
  reasons: string[];
  missing_prerequisite_groups: string[][];
  prerequisite_logic_status: PrerequisiteLogicStatus;
  structural_criticality: boolean;
  structural_impact_count: number;
  planned_semester: number | null;
  planned_order: number | null;
  critical_path: boolean;
  critical_path_reason: string | null;
  critical_path_length: number;
  critical_path_downstream_codes: string[];
  critical_path_evidence_chain: string[];
}

export interface AcademicRoadmapResponse {
  study_plan_id: string;
  plan_number: string | null;
  effective_year: number | null;
  plan_updated_at: string | null;
  generated_at: string;
  plan_total_required_credits: number;
  completed_plan_credits: number;
  in_progress_plan_credits: number;
  remaining_plan_credits: number;
  courses: RoadmapCourse[];
  edges: { prerequisite_code: string; target_code: string; dependency_type: DependencyType; group_number: number; option_count: number }[];
  limitations: string[];
  snapshot_fingerprint: string;
  snapshot_contract_version: string;
  critical_path_policy_version: string;
  modeling_status: "NOT_REQUESTED" | "NO_VALID_PATH" | "MODELED_PATH";
  modeled_plan_policy_version: string | null;
  source_type: string | null;
  source_retrieved_at: string | null;
  source_content_hash: string | null;
  source_snapshot_ref: string | null;
  source_status: string | null;
}

export interface ModeledAcademicReportResponse {
  report_schema_version: string;
  modeled_state_marker: "MODELED_UNOFFICIAL";
  study_plan_id: string;
  plan_number: string | null;
  effective_year: number | null;
  plan_updated_at: string | null;
  source_type: string | null;
  source_retrieved_at: string | null;
  source_content_hash: string | null;
  source_snapshot_ref: string | null;
  source_status: string | null;
  snapshot_contract_version: string;
  snapshot_fingerprint: string;
  critical_path_policy_version: string;
  modeled_plan_policy_version: string | null;
  modeling_status: string;
  generated_at: string;
  plan_total_required_credits: number;
  completed_plan_credits: number;
  in_progress_plan_credits: number;
  remaining_plan_credits: number;
  courses: Pick<RoadmapCourse, "course_code" | "name_ar" | "name_en" | "state" | "credit_hours" | "planned_semester" | "planned_order" | "critical_path">[];
  limitations: string[];
  content_fingerprint: string;
}

export type EligibilityGraphMode = "why" | "why_not";
export type EligibilityGraphNodeType =
  | "DECISION" | "COURSE" | "REASON" | "PREREQUISITE_GROUP"
  | "ACADEMIC_STATE" | "LIMITATION" | "RECOMMENDATION" | "CONSTRAINT"
  | "REQUIREMENT_GROUP" | "SEMESTER" | "DEGREE_PATH" | "POLICY_VERSION";
export type EligibilityGraphEdgeRelation =
  | "DECIDED_BY" | "REFERENCES" | "SUPPORTED_BY" | "SATISFIED_BY"
  | "BLOCKED_BY" | "LIMITED_BY" | "CONTRIBUTES_TO" | "CONSTRAINED_BY"
  | "SELECTED_IN" | "LEADS_TO" | "VERSIONED_BY" | "RANKED_AS";

export interface AcademicGraphFact {
  key: string;
  value: string | number | boolean;
}

export interface EligibilityGraphNode {
  id: string;
  type: EligibilityGraphNodeType;
  decision: Decision | null;
  reason: DecisionReason | null;
  course_code: string | null;
  reference_code?: string | null;
  group_number: number | null;
  dependency_type: DependencyType | null;
  option_course_codes: string[];
  passed_option_course_codes: string[];
  non_passed_option_course_codes: string[];
  academic_state: "PASSED" | "NOT_PASSED" | "TARGET_COMPLETED" | "TARGET_IN_PROGRESS" | null;
  limitation: string | null;
  facts?: AcademicGraphFact[];
}

export interface EligibilityGraphEdge {
  from_node_id: string;
  to_node_id: string;
  relation: EligibilityGraphEdgeRelation;
}

export interface EligibilityExplanationGraph {
  graph_id: string;
  subject_type: "ELIGIBILITY" | "COURSE_RECOMMENDATIONS" | "SEMESTER_PLANNER" | "DEGREE_PATH";
  subject_reference: string;
  root_node_id: string;
  mode: EligibilityGraphMode;
  target_decision: Decision | null;
  nodes: EligibilityGraphNode[];
  edges: EligibilityGraphEdge[];
  generated_at: string;
  policy_versions: string[];
  source_versions: string[];
  limitations: string[];
}

export type AcademicExplanationGraph = EligibilityExplanationGraph;

export interface RecommendationCandidateResponse {
  course_code: string;
  course_name_ar: string | null;
  course_name_en?: string | null;
  credit_hours: number;
  requirement_group_code: string;
  requirement_type: string;
  course_state: string;
  eligibility_decision: string;
  effective_credit_contribution: number;
  group_remaining_credits_before: number;
  group_remaining_credits_after: number;
  completes_requirement_group: boolean;
  newly_eligible_count: number;
  newly_eligible_course_codes: string[];
  rank: number;
  reason_codes: string[];
  previously_attempted: boolean;
}

export interface ReviewRequiredCourseResponse {
  course_code: string;
  course_name_ar: string | null;
  course_name_en?: string | null;
  credit_hours: number;
  requirement_group_code: string;
  requirement_type: string;
  review_reason: string;
  previously_attempted: boolean;
}

export interface RecommendationResponse {
  study_plan_id: string;
  recommendation_policy_version: string;
  ranked_recommendations: RecommendationCandidateResponse[];
  review_required_courses: ReviewRequiredCourseResponse[];
  excluded_in_progress: string[];
  methodology_note: string;
  limitations: string[];
}

export interface SemesterPlanRequest {
  max_credit_hours: number;
  max_courses?: number | null;
  max_options?: number;
  accept_heavy_balance?: boolean;
}

export interface PlannedCourseEntryResponse {
  course_code: string;
  course_name_ar: string | null;
  course_name_en: string | null;
  credit_hours: number;
  requirement_group_code: string;
  requirement_type: string;
  phase7_rank: number;
  previously_attempted: boolean;
}

export interface SemesterPlanOptionResponse {
  rank: number;
  courses: PlannedCourseEntryResponse[];
  total_credit_hours: number;
  total_courses: number;
  mandatory_course_count: number;
  zero_credit_required_count: number;
  completed_plan_credit_delta: number;
  newly_satisfied_requirement_group_codes: string[];
  newly_satisfied_requirement_group_count: number;
  newly_eligible_course_codes: string[];
  newly_eligible_count: number;
  recommendation_rank_sum: number;
  reason_codes: string[];
  memorization_heavy_count?: number;
  learning_type_counts?: Array<[string, number]>;
  estimated_workload?: string;
  balance_warning?: string | null;
}

export interface PlannerConstraintsResponse {
  max_credit_hours: number;
  max_courses: number | null;
  max_options: number;
}

export interface SemesterPlannerResponse {
  study_plan_id: string;
  semester_planner_policy_version: string;
  planning_scope: string;
  constraints: PlannerConstraintsResponse;
  candidate_window_size: number;
  eligible_ranked_candidate_count: number;
  evaluated_candidate_count: number;
  valid_combination_count: number;
  plan_options: SemesterPlanOptionResponse[];
  review_required_courses: string[];
  excluded_in_progress: string[];
  methodology_note: string;
  limitations: string[];
  balance_relaxation_required?: boolean;
}

export interface DegreePathRequest {
  max_credit_hours_per_semester: number;
  max_courses_per_semester?: number | null;
  max_semesters_ahead?: number;
  max_paths?: number;
}

export interface ModeledSemesterResponse {
  semester_index: number;
  plan_option: SemesterPlanOptionResponse;
  completed_plan_credits_after: number;
  remaining_plan_credits_after: number;
  newly_satisfied_requirement_group_codes: string[];
}

export interface DegreePathOptionResponse {
  rank: number;
  status: "COMPLETE" | "INCOMPLETE_MAX_SEMESTERS" | "INCOMPLETE_BLOCKED" | string;
  semesters: ModeledSemesterResponse[];
  semester_count: number;
  total_planned_courses: number;
  total_planned_credits: number;
  completed_plan_credit_delta: number;
  final_completed_plan_credits: number;
  final_remaining_plan_credits: number;
  newly_satisfied_requirement_group_count: number;
  newly_satisfied_requirement_group_codes: string[];
  remaining_required_course_codes: string[];
  unresolved_blocker_codes: string[];
  aggregate_semester_rank_sum: number;
  reason_codes: string[];
}

export interface DegreePathConstraintsResponse {
  max_credit_hours_per_semester: number;
  max_courses_per_semester: number | null;
  max_semesters_ahead: number;
  max_paths: number;
}

export interface DegreePathResponse {
  study_plan_id: string;
  degree_path_policy_version: string;
  planning_scope: string;
  constraints: DegreePathConstraintsResponse;
  paths: DegreePathOptionResponse[];
  initial_completed_credits: number;
  initial_remaining_credits: number;
  initial_satisfied_group_count: number;
  total_requirement_group_count: number;
  unresolved_review_required_courses: string[];
  persisted_in_progress_courses: string[];
  total_parent_states_expanded: number;
  methodology_note: string;
  limitations: string[];
}

export interface StudentIntentResponse {
  kind: "mock_registration_intent";
  intent_id: string;
  target_period_id: string;
  target_period_class: string;
  revision: number;
  lifecycle_status: string;
  course_codes: string[];
  submission_validation_status: "VALID" | "REVIEW_REQUIRED" | "INVALID" | string;
  submission_reason_codes: string[];
  current_validity: string | null;
  revalidation_status: string;
  current_reason_codes: string[];
  idempotent_replay: boolean;
  created_at: string;
  non_binding: true;
  limitations: string[];
}

export interface SubmitIntentRequest {
  target_period_id: string;
  course_codes: string[];
  expected_current_revision?: number | null;
  transparency_notice_version: string;
}

export interface WithdrawIntentRequest {
  target_period_id: string;
  expected_current_revision: number;
  transparency_notice_version: string;
}

export interface AdvisorRequest {
  message: string;
}

export interface AdvisorEvidenceResponse {
  source: string;
  course_codes: string[];
  policy_version: string | null;
}

export interface PolicyVersionResponse {
  source: string;
  version: string;
}

export interface AdvisorTraceResponse {
  authoritative_sources: string[];
  course_codes: string[];
  policy_versions: PolicyVersionResponse[];
  option_references: number[];
}

export interface AdvisorResponse {
  policy_version: string;
  intent: string;
  answer_authority: string;
  clarification: { reason: string; message_key: string; candidate_course_codes: string[] } | null;
  out_of_scope_reason: string | null;
  evidence: AdvisorEvidenceResponse[];
  trace: AdvisorTraceResponse;
  result: Record<string, unknown> | null;
  explanation: string | null;
  explanation_status: string;
  explanation_language: string | null;
}

export type DashboardError =
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "VALIDATION_ERROR"
  | "SERVICE_UNAVAILABLE"
  | "SERVER_ERROR"
  | "NETWORK_ERROR"
  | "CONFIGURATION_ERROR"
  | "UNKNOWN";

export interface AcademicPeriodOption {
  id: string;
  code: string;
  label: string;
  is_current: boolean;
}

export interface StudentPolicyPassage {
  id: string;
  locator_text: string;
  passage_text: string;
  article_number?: string | null;
  section_number?: string | null;
  page_number?: number | null;
  heading?: string | null;
  sequence_order: number;
  passage_sha256?: string | null;
}

export interface StudentPolicyDocumentSummary {
  id: string;
  university_id: string;
  document_code: string;
  title: string;
  authority_level: string;
  category: string;
  language: string;
  active_version_tag: string;
  effective_start_date?: string | null;
  passage_count: number;
}

export interface StudentPolicyVersionDetail {
  id: string;
  version_tag: string;
  status: string;
  effective_start_date?: string | null;
  effective_end_date?: string | null;
  content_sha256?: string | null;
  verified_at?: string | null;
  verified_by?: string | null;
  source_url?: string | null;
}

export interface StudentPolicyDocumentDetail {
  id: string;
  university_id: string;
  document_code: string;
  title: string;
  authority_level: string;
  category: string;
  language: string;
  active_version: StudentPolicyVersionDetail;
  passages: StudentPolicyPassage[];
}

export interface ConversationThread {
  id: string; title: string; status: "ACTIVE" | "ARCHIVED";
  created_at: string; updated_at: string; last_message_at: string | null;
  summary_text: string | null;
}

export interface ConversationMessage {
  id: string; thread_id: string; role: "USER" | "ASSISTANT";
  content: string; message_type: string; provenance: string; created_at: string;
}

export interface ConversationReply {
  thread_id: string; user_message: ConversationMessage;
  assistant_message: ConversationMessage; advisor: AdvisorResponse;
}

export interface CreditTimelineRequest {
  regular_load: number; summer_enabled: boolean; summer_load: number;
  start_year: number; start_term: "FIRST_SEMESTER" | "SECOND_SEMESTER" | "SUMMER";
}

export interface CreditTimelineResponse {
  policy_version: string; total_required_credits: number; earned_credits: number;
  initial_remaining_credits: number; regular_load: number; summer_enabled: boolean;
  summer_load: number; regular_semester_count: number; summer_count: number;
  completion_year: number | null; completion_term: CreditTimelineRequest["start_term"] | null;
  terms: Array<{ academic_year: number; term: CreditTimelineRequest["start_term"];
    planned_credits: number; remaining_after: number }>;
  assumptions: string[]; warnings: string[];
}

export interface CreditComparisonResponse {
  policy_version: string; evaluated_scenarios: number; limitations: string[];
  scenarios: Array<{ scenario_id: string; mode: "FASTEST" | "BALANCED" | "LOWER_LOAD";
    timeline: CreditTimelineResponse; total_modeled_terms: number;
    workload_indicator: string; preference_match: boolean;
    provenance: string; difficulty_evidence: string; confidence: string;
    current_workload_risk: number | null }>;
}

export interface StudentPolicySearchResult {
  document_id: string; document_code: string; document_title: string; category: string;
  version_id: string; version_tag: string; status: string; source_url?: string | null;
  passage_id: string; sequence_order: number; passage_text: string; locator_text: string;
  article_number?: string | null; section_number?: string | null; page_number?: number | null;
  heading?: string | null; passage_sha256?: string | null;
  lexical_rank?: number | null; semantic_rank?: number | null;
  semantic_similarity?: number | null; hybrid_score?: number | null;
}

export interface StudentPolicyAnswerCitation {
  document_id: string; document_code: string; document_title: string;
  version_id: string; version_tag: string; passage_id: string;
  locator_text: string; passage_text: string;
  article_number: string | null; section_number: string | null;
  page_number: number | null; heading: string | null;
  source_url: string | null; passage_sha256: string | null;
}

export interface StudentPolicyAnswerResponse {
  status: "ANSWERED" | "ABSTAINED" | "HANDOFF_REQUIRED";
  answer: string | null;
  language: "ar" | "en" | null;
  citations: StudentPolicyAnswerCitation[];
  retrieval_mode: "hybrid";
  abstention_reason: string | null;
  handoff: {
    target_engine: "ELIGIBILITY_ENGINE" | "PROGRESS_ENGINE" |
      "SEMESTER_PLANNER_ENGINE" | "DEGREE_PATH_ENGINE" | "MOCK_REGISTRATION_ENGINE" |
      "ADVISOR_AUTHORIZATION_ENGINE";
    query_topic: string;
    reason: string;
  } | null;
}

export interface StudentDecisionHistoryItem {
  ledger_entry_id: string;
  decision_type: string;
  decision_status: string;
  created_at: string;
  source_engine: string;
  source_engine_version: string;
  policy_version: string;
  replay_status: string;
  supersedes_entry_id: string | null;
  is_superseded: boolean;
  limitations: string[];
  integrity_status: "VERIFIED";
}

export interface StudentDecisionEvidence {
  source: string;
  identifier: string;
  version: string;
  locator: string | null;
  uri: string | null;
}

export interface StudentDecisionHistoryDetail extends StudentDecisionHistoryItem {
  source_versions: string[];
  provenance_class: string;
  evidence: StudentDecisionEvidence[];
}
