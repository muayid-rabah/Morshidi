import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

process.env.NEXT_PUBLIC_API_BASE_URL = 'https://api.morshidi.test';

import ProfilePage from '@/app/(student)/student/profile/page';
import ProgressPage from '@/app/(student)/student/progress/page';
import CoursesPage from '@/app/(student)/student/courses/page';
import EligibilityPage from '@/app/(student)/student/eligibility/page';
import RecommendationsPage from '@/app/(student)/student/recommendations/page';
import PlannerPage from '@/app/(student)/student/planner/page';
import DegreePathPage from '@/app/(student)/student/degree-path/page';
import MockRegistrationPage from '@/app/(student)/student/mock-registration/page';
import AdvisorPage from '@/app/(student)/student/advisor/page';
import PoliciesPage from '@/app/(student)/student/policies/page';
import DecisionHistoryPage from '@/app/(student)/student/decision-history/page';

import { AuthProvider } from '@/auth/auth-provider';
import { FakeAuthClient, fakeSession } from '@/test/fake-auth-client';
import type {
  AcademicProfileResponse,
  AcademicProgressResponse,
  AdvisorResponse,
  CanTakeDecisionResponse,
  EligibilityExplanationGraph,
  CourseAttemptResponse,
  DegreePathResponse,
  RecommendationResponse,
  SemesterPlannerResponse,
  StudentIntentResponse,
  StudentPolicyDocumentDetail,
  StudentPolicyDocumentSummary,
} from '@/lib/api/student-types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/student',
}));

const mockProfile: AcademicProfileResponse = {
  id: 'test-profile-uuid',
  study_plan_id: 'test-plan-uuid',
  reported_cumulative_gpa: 3.75,
  reported_gpa_scale: 4.0,
  reported_earned_credit_hours: 60,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const mockProgress: AcademicProgressResponse = {
  study_plan_id: 'test-plan-uuid',
  plan_total_required_credits: 132,
  completed_plan_credits: 60,
  in_progress_plan_credits: 15,
  remaining_plan_credits: 57,
  satisfied_requirement_group_count: 2,
  total_requirement_group_count: 4,
  all_modeled_plan_requirements_satisfied: false,
  requirement_groups: [
    {
      group_id: 'grp-1',
      group_code: 'REQ-COMP',
      name_ar: 'متطلبات كلية الحاسوب الإجبارية',
      name_en: 'IT College Mandatory',
      scope: 'COLLEGE',
      requirement_type: 'MANDATORY',
      required_credits: 24,
      listed_credits: 24,
      completed_listed_credits: 24,
      credited_toward_requirement: 24,
      in_progress_listed_credits: 0,
      remaining_required_credits: 0,
      completed_course_count: 8,
      in_progress_course_count: 0,
      attempted_not_completed_count: 0,
      not_attempted_count: 0,
      total_listed_course_count: 8,
      is_satisfied: true,
    },
  ],
  courses: [
    {
      course_code: '1501110',
      credit_hours: 3,
      requirement_group_id: 'grp-1',
      requirement_group_code: 'REQ-COMP',
      state: 'COMPLETED',
    },
  ],
  reported_cumulative_gpa: 3.75,
  reported_gpa_scale: 4.0,
  reported_earned_credit_hours: 60,
};

const mockAttempts: CourseAttemptResponse[] = [
  {
    id: 'attempt-1',
    course_code: '1501110',
    status: 'PASSED',
    attempt_sequence: 1,
    term_label: '2023-1',
    attempted_on: '2023-09-01',
    raw_grade_text: 'A',
    record_source: 'manual_entry',
    created_at: '2023-09-01T00:00:00Z',
    updated_at: '2023-09-01T00:00:00Z',
  },
];

const mockEligibility: CanTakeDecisionResponse = {
  kind: 'decision',
  decision: 'ELIGIBLE',
  study_plan_id: 'test-plan-uuid',
  target_course_code: '1501211',
  prerequisite_logic_status: 'verified',
  target_attempt_state: {
    has_passed_target: false,
    has_in_progress_target: false,
  },
  satisfied_dependency_groups: [
    {
      group_number: 1,
      dependency_type: 'prerequisite',
      option_course_codes: ['1501110'],
      passed_option_course_codes: ['1501110'],
      non_passed_option_course_codes: [],
    },
  ],
  missing_dependency_groups: [],
  reasons: ['PREREQUISITES_SATISFIED'],
  review_reasons: [],
  raw_prerequisite_text: '1501110',
  target_name_ar: 'برمجة كينونية',
};

const mockEligibilityGraph = {
  graph_id: 'eligibility:1501211:ELIGIBLE:why',
  subject_type: 'ELIGIBILITY', subject_reference: '1501211',
  root_node_id: 'decision:1501211', mode: 'why', target_decision: null,
  nodes: [
    {
      id: 'decision:1501211', type: 'DECISION', decision: 'ELIGIBLE', reason: null,
      course_code: null, group_number: null, dependency_type: null,
      option_course_codes: [], passed_option_course_codes: [], non_passed_option_course_codes: [],
      academic_state: null, limitation: null,
    },
    {
      id: 'reason:PREREQUISITES_SATISFIED', type: 'REASON', decision: null,
      reason: 'PREREQUISITES_SATISFIED', course_code: null, group_number: null,
      dependency_type: null, option_course_codes: [], passed_option_course_codes: [],
      non_passed_option_course_codes: [], academic_state: null, limitation: null,
    },
  ],
  edges: [{ from_node_id: 'decision:1501211', to_node_id: 'reason:PREREQUISITES_SATISFIED', relation: 'DECIDED_BY' }],
  limitations: ['CURRENT_STORED_STATE', 'EXACT_SOURCE_VERSION_UNAVAILABLE'],
  policy_versions: [], source_versions: [], generated_at: '2026-09-29T00:00:00Z',
} satisfies EligibilityExplanationGraph;

function materialGraph(
  subject_type: EligibilityExplanationGraph['subject_type'],
  root_node_id: string,
  type: 'RECOMMENDATION' | 'SEMESTER' | 'DEGREE_PATH',
): EligibilityExplanationGraph {
  const base = mockEligibilityGraph.nodes[0];
  return {
    ...mockEligibilityGraph, subject_type, root_node_id, graph_id: `${subject_type}:test`,
    policy_versions: ['2026-p7'], source_versions: [],
    limitations: ['SOURCE_DOCUMENT_VERSION_UNAVAILABLE'],
    nodes: [{ ...base, id: root_node_id, type, decision: null, facts: [
      { key: 'RANK', value: 1 }, { key: 'STATUS', value: 'RANKED' },
    ] }],
    edges: [],
  };
}

const mockRecommendationGraph = materialGraph('COURSE_RECOMMENDATIONS', 'recommendation:1:1501211', 'RECOMMENDATION');
const mockPlannerGraph = materialGraph('SEMESTER_PLANNER', 'semester-planner:option:1', 'SEMESTER');
const mockPathGraph = materialGraph('DEGREE_PATH', 'degree-path:1', 'DEGREE_PATH');

const mockRecommendations: RecommendationResponse = {
  study_plan_id: 'test-plan-uuid',
  recommendation_policy_version: '2026-p7',
  ranked_recommendations: [
    {
      course_code: '1501211',
      course_name_ar: 'برمجة كينونية',
      credit_hours: 3,
      requirement_group_code: 'REQ-COMP',
      requirement_type: 'MANDATORY',
      course_state: 'NOT_ATTEMPTED',
      eligibility_decision: 'ELIGIBLE',
      effective_credit_contribution: 3,
      group_remaining_credits_before: 12,
      group_remaining_credits_after: 9,
      completes_requirement_group: false,
      newly_eligible_count: 2,
      newly_eligible_course_codes: ['1501221', '1501332'],
      rank: 1,
      reason_codes: ['PRIORITY_CORE'],
      previously_attempted: false,
    },
  ],
  review_required_courses: [],
  excluded_in_progress: [],
  methodology_note: 'ترتيب يعتمد أولوية متطلبات التخصص وفتح المواد اللاحقة.',
  limitations: ['يخضع للشعب المطروحة'],
};

const mockSemesterPlanner: SemesterPlannerResponse = {
  study_plan_id: 'test-plan-uuid',
  semester_planner_policy_version: '2026-p7',
  planning_scope: 'UPCOMING_SEMESTER',
  constraints: {
    max_credit_hours: 15,
    max_courses: 5,
    max_options: 3,
  },
  candidate_window_size: 10,
  eligible_ranked_candidate_count: 5,
  evaluated_candidate_count: 5,
  valid_combination_count: 1,
  plan_options: [
    {
      rank: 1,
      courses: [
        {
          course_code: '1501211',
          course_name_ar: 'برمجة كينونية',
          course_name_en: 'Object-Oriented Programming',
          credit_hours: 3,
          requirement_group_code: 'REQ-COMP',
          requirement_type: 'MANDATORY',
          phase7_rank: 1,
          previously_attempted: false,
        },
      ],
      total_credit_hours: 3,
      total_courses: 1,
      mandatory_course_count: 1,
      zero_credit_required_count: 0,
      completed_plan_credit_delta: 3,
      newly_satisfied_requirement_group_codes: [],
      newly_satisfied_requirement_group_count: 0,
      newly_eligible_course_codes: ['1501221'],
      newly_eligible_count: 1,
      recommendation_rank_sum: 1,
      reason_codes: [],
    },
  ],
  review_required_courses: [],
  excluded_in_progress: [],
  methodology_note: 'توليد خيارات مثلى',
  limitations: [],
};

const mockDegreePath: DegreePathResponse = {
  study_plan_id: 'test-plan-uuid',
  degree_path_policy_version: '2026-p7',
  planning_scope: 'GRADUATION_SIMULATION',
  constraints: {
    max_credit_hours_per_semester: 15,
    max_courses_per_semester: 5,
    max_semesters_ahead: 8,
    max_paths: 1,
  },
  paths: [
    {
      rank: 1,
      status: 'COMPLETE',
      semesters: [
        {
          semester_index: 1,
          plan_option: mockSemesterPlanner.plan_options[0],
          completed_plan_credits_after: 63,
          remaining_plan_credits_after: 54,
          newly_satisfied_requirement_group_codes: [],
        },
      ],
      semester_count: 1,
      total_planned_courses: 1,
      total_planned_credits: 3,
      completed_plan_credit_delta: 3,
      final_completed_plan_credits: 132,
      final_remaining_plan_credits: 0,
      newly_satisfied_requirement_group_count: 1,
      newly_satisfied_requirement_group_codes: ['REQ-COMP'],
      remaining_required_course_codes: [],
      unresolved_blocker_codes: [],
      aggregate_semester_rank_sum: 1,
      reason_codes: [],
    },
  ],
  initial_completed_credits: 60,
  initial_remaining_credits: 72,
  initial_satisfied_group_count: 2,
  total_requirement_group_count: 4,
  unresolved_review_required_courses: [],
  persisted_in_progress_courses: [],
  total_parent_states_expanded: 5,
  methodology_note: 'محاكاة التخرج',
  limitations: [],
};

const mockIntent: StudentIntentResponse = {
  kind: 'mock_registration_intent',
  intent_id: 'intent-123',
  target_period_id: '2024-1',
  target_period_class: 'REGULAR',
  revision: 1,
  lifecycle_status: 'SUBMITTED',
  course_codes: ['1501211'],
  submission_validation_status: 'VALID',
  submission_reason_codes: ['VALID_SELECTION'],
  current_validity: 'VALID',
  revalidation_status: 'VALID',
  current_reason_codes: [],
  idempotent_replay: false,
  created_at: '2026-01-01T00:00:00Z',
  non_binding: true,
  limitations: ['غير ملزم'],
};

const mockAdvisor: AdvisorResponse = {
  policy_version: '2026-p7',
  intent: 'COURSE_ELIGIBILITY_INQUIRY',
  answer_authority: 'DETERMINISTIC_RULES_ENGINE',
  clarification: null,
  out_of_scope_reason: null,
  evidence: [
    {
      source: 'STUDY_PLAN_RULES',
      course_codes: ['1501211'],
      policy_version: '2026-p7',
    },
  ],
  trace: {
    authoritative_sources: ['STUDY_PLAN_12'],
    course_codes: ['1501211'],
    policy_versions: [{ source: 'RULES', version: '2026-p7' }],
    option_references: [],
  },
  result: {},
  explanation: 'أنت مؤهل لتسجيل مادة برمجة كينونية (1501211) بعد اجتيازك لمادتها السابقة بنجاح.',
  explanation_status: 'SUCCESS',
  explanation_language: 'ar',
};

const mockPolicySummary: StudentPolicyDocumentSummary = {
  id: 'doc-policy-1',
  university_id: 'univ-1',
  document_code: 'BYLAW-2026',
  title: 'تعليمات منح درجة البكالوريوس',
  authority_level: 'university_council',
  category: 'academic_bylaws',
  language: 'ar',
  active_version_tag: '1.0',
  passage_count: 1,
};

const mockPolicyDetail: StudentPolicyDocumentDetail = {
  id: 'doc-policy-1',
  university_id: 'univ-1',
  document_code: 'BYLAW-2026',
  title: 'تعليمات منح درجة البكالوريوس',
  authority_level: 'university_council',
  category: 'academic_bylaws',
  language: 'ar',
  active_version: {
    id: 'ver-1',
    version_tag: '1.0',
    status: 'verified',
    effective_start_date: '2026-09-01T00:00:00Z',
  },
  passages: [
    {
      id: 'pas-1',
      locator_text: 'المادة 5',
      passage_text: 'الحد الأدنى للعبء الدراسي في الفصل الاعتيادي هو 12 ساعة معتمدة.',
      article_number: '5',
      sequence_order: 0,
    },
  ],
};

function setupMockFetch() {
  const thread = { id: 'thread-1', title: 'Academic question', status: 'ACTIVE',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    last_message_at: null, summary_text: null };
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/v1/me/adaptive-course-intelligence')) {
      return new Response('{}', { status: 503 });
    }
    if (url.includes('/api/v1/me/conversations/preferences')) {
      return new Response(JSON.stringify({}), { status: 200 });
    }
    if (url.includes('/api/v1/me/conversations/')) {
      if (init?.method !== 'POST') return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({ thread_id: thread.id,
        user_message: { id: 'message-1', thread_id: thread.id, role: 'USER', content: 'Question',
          message_type: 'TEXT', provenance: 'STUDENT', created_at: '2026-01-01T00:00:00Z' },
        assistant_message: { id: 'message-2', thread_id: thread.id, role: 'ASSISTANT',
          content: mockAdvisor.explanation, message_type: 'TEXT', provenance: 'ADVISOR',
          created_at: '2026-01-01T00:00:01Z' }, advisor: mockAdvisor }), { status: 200 });
    }
    if (url.includes('/api/v1/me/conversations')) {
      return new Response(JSON.stringify(init?.method === 'POST' ? thread : []), { status: 200 });
    }

    if (url.includes('/api/v1/me/policies/')) {
      return new Response(JSON.stringify(mockPolicyDetail), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/policies')) {
      return new Response(JSON.stringify([mockPolicySummary]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/academic-profile/attempts')) {
      return new Response(JSON.stringify(mockAttempts), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/academic-profile')) {
      return new Response(JSON.stringify(mockProfile), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/academic-progress')) {
      return new Response(JSON.stringify(mockProgress), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/course-recommendations/explanation-graph')) {
      return new Response(JSON.stringify(mockRecommendationGraph), { status: 200 });
    }
    if (url.includes('/semester-plans/explanation-graph')) {
      return new Response(JSON.stringify(mockPlannerGraph), { status: 200 });
    }
    if (url.includes('/degree-paths/explanation-graph')) {
      return new Response(JSON.stringify(mockPathGraph), { status: 200 });
    }
    if (url.includes('/explanation-graph')) {
      return new Response(JSON.stringify(mockEligibilityGraph), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/eligibility')) {
      return new Response(JSON.stringify(mockEligibility), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/course-recommendations')) {
      return new Response(JSON.stringify(mockRecommendations), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/semester-plans')) {
      return new Response(JSON.stringify(mockSemesterPlanner), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/degree-paths')) {
      return new Response(JSON.stringify(mockDegreePath), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/mock-registration/current')) {
      return new Response(JSON.stringify(mockIntent), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/api/v1/me/advisor')) {
      return new Response(JSON.stringify(mockAdvisor), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
}

function renderWithAuth(ui: React.ReactElement) {
  const authClient = new FakeAuthClient(fakeSession());
  return render(
    <AuthProvider client={authClient}>
      {ui}
    </AuthProvider>,
  );
}

describe('Morshidi Student Portal Pages Suite', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = setupMockFetch();
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('renders ProfilePage with GPA and academic details', async () => {
    renderWithAuth(<ProfilePage />);
    expect(screen.getByText('ملفي الأكاديمي')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('3.75')).toBeDefined();
    });
    expect(screen.getByText('حساب معتمد')).toBeDefined();
  });

  it('renders ProgressPage with credit progress and requirement groups', async () => {
    renderWithAuth(<ProgressPage />);
    expect(screen.getByText('التقدم الأكاديمي')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('متطلبات كلية الحاسوب الإجبارية')).toBeDefined();
    });
    expect(screen.getByText('1501110')).toBeDefined();
  });

  it('renders CoursesPage with attempts list and stats', async () => {
    renderWithAuth(<CoursesPage />);
    expect(screen.getByText('المواد وسجل المحاولات')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('1501110')).toBeDefined();
    });
    expect(screen.getByText('ناجح / مستوفى')).toBeDefined();
  });

  it('renders EligibilityPage and checks course eligibility', async () => {
    const user = userEvent.setup();
    renderWithAuth(<EligibilityPage />);
    expect(screen.getByText('فحص أهلية تسجيل مادة')).toBeDefined();
    expect(screen.queryByRole('button', { name: '1501332' })).toBeNull();

    const input = screen.getByPlaceholderText('أدخل رمز المادة هنا...');
    await user.type(input, '1501211');
    const checkBtn = screen.getByRole('button', { name: 'فحص الأهلية' });
    await user.click(checkBtn);

    await waitFor(() => {
      expect(screen.getByText(/مؤهل لتسجيل المادة/)).toBeDefined();
    });
    expect(screen.getAllByText(/برمجة كينونية/).length).toBeGreaterThan(0);
  });

  it('renders the graph beneath the authoritative eligibility result', async () => {
    const user = userEvent.setup();
    renderWithAuth(<EligibilityPage />);
    await user.type(screen.getByPlaceholderText('أدخل رمز المادة هنا...'), '1501211');
    await user.click(screen.getByRole('button', { name: 'فحص الأهلية' }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'لماذا هذا القرار؟' })).toBeDefined();
      expect(screen.getByText('استوفيت المتطلبات السابقة')).toBeDefined();
    });
  });

  it('loads clarification names in one batch only after academic clarification and preserves submitted codes', async () => {
    const normalFetch = fetchSpy.getMockImplementation()!;
    fetchSpy.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/course-identities')) return new Response(JSON.stringify([
        { course_id: 'one', course_code: 'CS101', name_ar: 'مقدمة البرمجة', name_en: 'Programming Introduction' },
        { course_id: 'two', course_code: 'CS201', name_ar: 'برمجة متقدمة', name_en: 'Advanced Programming' },
      ]));
      const response = await normalFetch(input, init);
      if (url.includes('/conversations/') && init?.method === 'POST') {
        const body = await response.json();
        body.advisor = { ...mockAdvisor, clarification: { reason: 'AMBIGUOUS_COURSE',
          message_key: 'clarify', candidate_course_codes: ['CS101', 'CS201'] } };
        return new Response(JSON.stringify(body));
      }
      return response;
    });
    renderWithAuth(<AdvisorPage />);
    const user = userEvent.setup();
    const prompt = await screen.findByRole('textbox', { name: 'الاستفسار الأكاديمي' });
    await waitFor(() => expect(prompt.hasAttribute('disabled')).toBe(false));
    expect(fetchSpy.mock.calls.some(([url]: [RequestInfo | URL]) => String(url).endsWith('/course-identities'))).toBe(false);
    await user.type(prompt, 'What about programming?');
    await user.keyboard('{Enter}');
    const option = await screen.findByRole('button', { name: /مقدمة البرمجة.*CS101/ });
    expect(option.textContent).toBe('مقدمة البرمجةCS101');
    await user.click(option);
    await waitFor(() => expect(fetchSpy.mock.calls.some(([, init]: [RequestInfo | URL, RequestInit?]) =>
      typeof init?.body === 'string' && init.body.includes('CS101'))).toBe(true));
    expect(fetchSpy.mock.calls.filter(([url]: [RequestInfo | URL]) => String(url).endsWith('/course-identities'))).toHaveLength(1);
  });

  it('prefills stored planning preferences, compares three modeled strategies, and permits explicit override', async () => {
    const normalFetch = fetchSpy.getMockImplementation()!;
    fetchSpy.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/conversations/preferences')) return new Response(JSON.stringify({
        regular_load: '15', summer_enabled: 'true', summer_load: '6', graduation_pace: 'BALANCED',
      }));
      if (url.endsWith('/credit-comparison')) return new Response(JSON.stringify({
        policy_version: 'P15_6_CREDIT_COMPARISON_V1', evaluated_scenarios: 12,
        limitations: ['Credit-only; future courses are unassigned. MODELED_ACADEMIC_CALENDAR'],
        scenarios: ['FASTEST', 'BALANCED', 'LOWER_LOAD'].map((mode, index) => ({
          scenario_id: `scenario-${index}`, mode, total_modeled_terms: 5 + index,
          timeline: { regular_load: [18, 15, 12][index], summer_enabled: true, summer_load: 6,
            regular_semester_count: 4 + index, summer_count: 1, completion_term: 'FIRST_SEMESTER', completion_year: 2028 },
          workload_indicator: 'MODERATE', preference_match: mode === 'BALANCED',
          provenance: 'MODELED_ACADEMIC_CALENDAR', difficulty_evidence: 'CURRENT_ELIGIBLE_COURSES_ONLY',
          confidence: 'MODELED_CREDIT_ONLY', current_workload_risk: 50,
        })),
      }));
      return normalFetch(input, init);
    });
    renderWithAuth(<DegreePathPage />);
    const user = userEvent.setup();
    const regular = await screen.findByLabelText(/Regular credits/);
    await waitFor(() => expect((screen.getByLabelText(/Include summer/) as HTMLInputElement).checked).toBe(true));
    expect((regular as HTMLSelectElement).value).toBe('15');
    await user.click(screen.getByRole('button', { name: /قارن: الأسرع/ }));
    await screen.findByRole('heading', { name: 'المتوازن / Balanced' });
    expect(screen.getByRole('heading', { name: 'الأسرع / Fastest' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'الحمل الأخف / Lower load' })).toBeTruthy();
    expect(screen.getAllByText(/MODELED_ACADEMIC_CALENDAR/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Matches your stated preference/)).toBeTruthy();
    await user.selectOptions(regular, '18');
    await user.click(screen.getByRole('button', { name: /قارن: الأسرع/ }));
    await waitFor(() => {
      const requests = fetchSpy.mock.calls.filter(([url]: [RequestInfo | URL]) => String(url).endsWith('/credit-comparison'));
      expect(requests).toHaveLength(2);
      expect(JSON.parse(requests[1][1].body)).toMatchObject({ preferred_regular_load: 18,
        preferred_summer_enabled: true, preferred_summer_load: 6, graduation_pace: 'BALANCED' });
    });
  });

  it('renders RecommendationsPage with ranked courses and impact tags', async () => {
    const user = userEvent.setup();
    renderWithAuth(<RecommendationsPage />);
    expect(screen.getByText('التوصيات الأكاديمية الذكية')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('#1')).toBeDefined();
    });
    expect(screen.getByText(/تفتح 2 مواد لاحقة/)).toBeDefined();
    await user.click(screen.getByRole('button', { name: 'لماذا هذه النتيجة؟' }));
    await waitFor(() => expect(screen.getByText('توصية #1')).toBeDefined());
  });

  it('renders PlannerPage and generates plan options', async () => {
    const user = userEvent.setup();
    renderWithAuth(<PlannerPage />);
    expect(screen.getByText('مخطط الفصل الدراسي')).toBeDefined();

    const generateBtn = screen.getByRole('button', { name: /توليد خيارات الفصل/ });
    await user.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByText('الخيار #1 (الأفضل تقييماً)')).toBeDefined();
    });
    expect(screen.getByText('برمجة كينونية')).toBeDefined();
    await waitFor(() => expect(screen.getByText('خيار فصل #1')).toBeDefined());
  });

  it('renders DegreePathPage and simulates path until graduation', async () => {
    const user = userEvent.setup();
    renderWithAuth(<DegreePathPage />);
    expect(screen.getByText('المسار الدراسي حتى التخرج')).toBeDefined();

    const simulateBtn = screen.getByRole('button', { name: /توليد ومحاكاة مسار التخرج/ });
    await user.click(simulateBtn);

    await waitFor(() => {
      expect(screen.getByText('تخرج كامل')).toBeDefined();
    });
    expect(screen.getByText(/الفصل الدراسي القادم #1/)).toBeDefined();
    await waitFor(() => expect(screen.getByText('مسار نموذجي #1')).toBeDefined());
  });

  it('renders MockRegistrationPage with active submitted intent and non-binding notice', async () => {
    renderWithAuth(<MockRegistrationPage />);
    expect(screen.getByText('التسجيل التجريبي والمحاكاة')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('مرسلة ومعتمدة')).toBeDefined();
    });
    expect(screen.getByText(/إشعار الشفافية والمسؤولية الأكاديمية/)).toBeDefined();
  });

  it('renders AdvisorPage with suggested questions and conversational message sending', async () => {
    const user = userEvent.setup();
    renderWithAuth(<AdvisorPage />);
    expect(screen.getByRole('heading', { name: 'مرشدي' })).toBeDefined();

    const quickBtn = screen.getByText('هل يمكنني تسجيل مادة الذكاء الاصطناعي؟');
    await waitFor(() => expect((quickBtn as HTMLButtonElement).disabled).toBe(false));
    await user.click(quickBtn);

    await waitFor(() => {
      expect(screen.getByText(/أنت مؤهل لتسجيل مادة برمجة كينونية/)).toBeDefined();
    });
    expect(screen.getByText('المصدر: DETERMINISTIC_RULES_ENGINE')).toBeDefined();
  });

  it('shows neutral advisor pending copy without claiming a backend stage completed', async () => {
    const normalFetch = fetchSpy.getMockImplementation()!;
    fetchSpy.mockImplementation((input: RequestInfo | URL, init?: RequestInit) =>
      String(input).includes('/api/v1/me/conversations/') && init?.method === 'POST'
        ? new Promise<Response>(() => {}) : normalFetch(input, init));
    const user = userEvent.setup();
    renderWithAuth(<AdvisorPage />);
    expect(screen.getByRole('log')).toBeDefined();
    expect(screen.getByRole('textbox', { name: 'الاستفسار الأكاديمي' })).toBeDefined();
    const questions = screen.getAllByRole('button');
    const quickQuestion = questions.find((button) => button.textContent?.includes('الذكاء الاصطناعي'))!;
    await waitFor(() => expect((quickQuestion as HTMLButtonElement).disabled).toBe(false));
    await user.click(quickQuestion);
    expect(screen.getByText('مرشدي يجهّز الرد...')).toBeDefined();
    expect(screen.queryByText(/جاري استشارة المحرك الحتمي/)).toBeNull();
  });

  it('renders PoliciesPage with real policies from API and opens detail modal', async () => {
    const user = userEvent.setup();
    renderWithAuth(<PoliciesPage />);
    expect(screen.getByText('اللوائح والسياسات الجامعية')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText('تعليمات منح درجة البكالوريوس')).toBeDefined();
      expect(screen.getByText('BYLAW-2026')).toBeDefined();
    });

    const policyCard = screen.getByText('تعليمات منح درجة البكالوريوس');
    await user.click(policyCard);

    await waitFor(() => {
      expect(screen.getByText(/الحد الأدنى للعبء الدراسي في الفصل الاعتيادي/)).toBeDefined();
      expect(screen.getAllByText(/المادة 5/).length).toBeGreaterThan(0);
    });
  });

  it('uses POST only and clears degree-path loading after a server error', async () => {
    const requests: string[] = [];
    fetchSpy.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(`${init?.method ?? 'GET'} ${String(input)}`);
      if (String(input).includes('/degree-paths')) expect(init?.signal).toBeInstanceOf(AbortSignal);
      return new Response('{}', { status: 503 });
    });
    const user = userEvent.setup();
    const { container } = renderWithAuth(<DegreePathPage />);
    await user.click(container.querySelectorAll('form button[type="submit"]')[1] as HTMLButtonElement);
    await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toContain('تعذر إنشاء مسار التخرج الآن');
    expect(screen.getByRole('alert').textContent).not.toContain('استغرق إنشاء');
    expect(screen.queryByRole('status')).toBeNull();
    expect(requests.filter((request) => request.includes('/degree-paths'))).toEqual([
      expect.stringMatching(/^POST .*\/api\/v1\/me\/degree-paths$/),
    ]);
  });

  it('clears degree-path loading when response JSON is malformed', async () => {
    fetchSpy.mockImplementation(async () => new Response('not-json', { status: 200 }));
    const user = userEvent.setup();
    const { container } = renderWithAuth(<DegreePathPage />);
    await user.click(container.querySelectorAll('form button[type="submit"]')[1] as HTMLButtonElement);
    await screen.findByRole('alert');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('rejects a malformed degree-path shape before rendering it', async () => {
    fetchSpy.mockImplementation(async () => new Response('{}', { status: 200 }));
    const user = userEvent.setup();
    const { container } = renderWithAuth(<DegreePathPage />);
    await user.click(container.querySelectorAll('form button[type="submit"]')[1] as HTMLButtonElement);
    await screen.findByRole('alert');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('clears degree-path loading when the request times out', async () => {
    const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort());
    fetchSpy.mockImplementation(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.signal?.aborted) throw new DOMException('Timed out', 'TimeoutError');
      return new Response('{}', { status: 200 });
    });
    try {
      const user = userEvent.setup();
      const { container } = renderWithAuth(<DegreePathPage />);
      await user.click(container.querySelectorAll('form button[type="submit"]')[1] as HTMLButtonElement);
      await screen.findByRole('alert');
      expect(screen.getByRole('alert').textContent).toContain('استغرق إنشاء مسار التخرج وقتًا أطول');
      expect(screen.queryByRole('status')).toBeNull();
    } finally {
      timeout.mockRestore();
    }
  });

  it('shows a list failure and retries the real policy request', async () => {
    let listCalls = 0;
    fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/me/policies')) {
        listCalls += 1;
        if (listCalls === 1) return new Response('{}', { status: 500 });
        return new Response(JSON.stringify([mockPolicySummary]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    });
    const user = userEvent.setup();
    renderWithAuth(<PoliciesPage />);
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('تعذّر تحميل اللوائح'));
    await user.click(screen.getByRole('button', { name: 'إعادة المحاولة' }));
    await waitFor(() => expect(screen.getByText('تعليمات منح درجة البكالوريوس')).toBeDefined());
    expect(listCalls).toBe(2);
  });

  it('shows detail loading, a safe failure state, and retries the selected document', async () => {
    let detailCalls = 0;
    const completeDetail: StudentPolicyDocumentDetail = {
      ...mockPolicyDetail,
      active_version: {
        ...mockPolicyDetail.active_version,
        effective_end_date: '2027-09-01T00:00:00Z',
        content_sha256: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
        verified_at: '2026-09-02T00:00:00Z',
        verified_by: 'policy-office',
        source_url: 'https://university.example.edu/policies/bylaw.pdf',
      },
      passages: [{ ...mockPolicyDetail.passages[0], section_number: '3', page_number: 42, heading: 'العبء الدراسي', passage_sha256: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789' }],
    };
    fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/me/policies/')) {
        detailCalls += 1;
        if (detailCalls === 1) return new Response('{}', { status: 404 });
        return new Response(JSON.stringify(completeDetail), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/v1/me/policies')) return new Response(JSON.stringify([mockPolicySummary]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    const user = userEvent.setup();
    renderWithAuth(<PoliciesPage />);
    await user.click(await screen.findByText('تعليمات منح درجة البكالوريوس'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('لم تعد هذه اللائحة متاحة'));
    expect(screen.queryByText(mockPolicyDetail.passages[0].passage_text)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'إعادة المحاولة' }));
    await waitFor(() => expect(screen.getByText('المصدر والإصدار')).toBeDefined());
    expect(screen.getByText('القسم')).toBeDefined();
    expect(screen.getByText('42')).toBeDefined();
    expect(screen.getByText('العبء الدراسي')).toBeDefined();
    expect(screen.getByRole('link', { name: 'مصدر خارجي ↗' }).getAttribute('rel')).toBe('noopener noreferrer');
    expect(detailCalls).toBe(2);
  });

  it('does not invent absent policy citation metadata', async () => {
    renderWithAuth(<PoliciesPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByText('تعليمات منح درجة البكالوريوس'));
    await screen.findByText(mockPolicyDetail.passages[0].passage_text);
    expect(screen.queryByText('بصمة المحتوى')).toBeNull();
    expect(screen.queryByText('الصفحة')).toBeNull();
    expect(screen.queryByRole('link', { name: 'مصدر خارجي ↗' })).toBeNull();
  });

  it('renders a semantic-only hybrid result as exact citation evidence and opens its document', async () => {
    fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/me/policies/search')) return new Response(JSON.stringify([{
        document_id: mockPolicySummary.id, document_code: mockPolicySummary.document_code,
        document_title: mockPolicySummary.title, category: mockPolicySummary.category,
        version_id: 'ver-1', version_tag: '1.0', status: 'verified', passage_id: 'search-p1',
        lexical_rank: null, semantic_rank: 1, semantic_similarity: 0.91, hybrid_score: 0.016,
        sequence_order: 0, passage_text: 'نص عربي موثق للبحث داخل اللائحة.', locator_text: 'المادة 9',
        article_number: '9', page_number: 11, heading: 'الانسحاب',
      }]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      if (url.includes('/api/v1/me/policies/')) return new Response(JSON.stringify(mockPolicyDetail), { status: 200, headers: { 'Content-Type': 'application/json' } });
      if (url.endsWith('/api/v1/me/policies')) return new Response(JSON.stringify([mockPolicySummary]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    const user = userEvent.setup();
    renderWithAuth(<PoliciesPage />);
    const search = await screen.findByPlaceholderText('ابحث داخل نصوص اللوائح والسياسات...');
    await user.type(search, 'الانسحاب');
    await user.click(screen.getByRole('button', { name: 'بحث' }));
    await screen.findByText('نص عربي موثق للبحث داخل اللائحة.');
    expect(screen.getAllByText(/المادة 9/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: 'فتح اللائحة كاملة' }));
    await screen.findByText(mockPolicyDetail.passages[0].passage_text);
  });

  it('shows honest empty and retryable error states for policy text search', async () => {
    let calls = 0;
    fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/me/policies/search')) {
        calls += 1;
        if (calls === 1) return new Response('{}', { status: 503 });
        if (calls === 2) return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/v1/me/policies')) return new Response(JSON.stringify([mockPolicySummary]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      return new Response(JSON.stringify(mockPolicyDetail), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    const user = userEvent.setup();
    renderWithAuth(<PoliciesPage />);
    await user.type(await screen.findByPlaceholderText('ابحث داخل نصوص اللوائح والسياسات...'), 'انسحاب');
    await user.click(screen.getByRole('button', { name: 'بحث' }));
    await screen.findByRole('alert');
    await user.click(screen.getByRole('button', { name: 'إعادة المحاولة' }));
    await screen.findByText('لم يتم العثور على نص موثق يطابق بحثك.');
    expect(calls).toBe(2);
  });

  it('uses hybrid retrieval for the citation-only policy search experience', async () => {
    const requests: string[] = [];
    fetchSpy.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.includes('/api/v1/me/policies/search')) return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      if (url.endsWith('/api/v1/me/policies')) return new Response(JSON.stringify([mockPolicySummary]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      return new Response(JSON.stringify(mockPolicyDetail), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    const user = userEvent.setup();
    const { container } = renderWithAuth(<PoliciesPage />);
    await waitFor(() => expect(container.querySelector('#policy-text-search')).not.toBeNull());
    const input = container.querySelector('#policy-text-search') as HTMLInputElement;
    await user.type(input, 'withdrawal');
    await user.click(input.closest('form')?.querySelector('button[type="submit"]') as HTMLButtonElement);
    await waitFor(() => expect(requests.some((url) => url.includes('/api/v1/me/policies/search') && url.includes('mode=hybrid'))).toBe(true));
    expect(screen.queryByText(/AI answer/i)).toBeNull();
  });

  it('renders the read-only Decision History page without the old placeholder', () => {
    renderWithAuth(<DecisionHistoryPage />);
    expect(screen.getByRole('heading', { name: 'سجل القرارات الأكاديمية' })).toBeDefined();
    expect(screen.queryByText('سجل القرارات الأكاديمية قيد التجهيز')).toBeNull();
  });
});
