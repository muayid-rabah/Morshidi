import type {
  AcademicExplanationGraph, AcademicGraphFact, EligibilityGraphNode,
  EligibilityGraphEdgeRelation,
} from "@/lib/api/student-types";
import { CourseIdentity } from "./CourseIdentity";
import type { CourseIdentityMap } from "@/lib/api/use-course-identities";

const factLabels: Record<string, string> = {
  RANK: "الترتيب", STATUS: "الحالة", REASON_CODE: "سبب حتمي",
  REQUIREMENT_TYPE: "نوع المتطلب", COURSE_STATE: "حالة المادة",
  ELIGIBILITY_DECISION: "قرار الأهلية", CREDIT_HOURS: "الساعات المعتمدة",
  EFFECTIVE_CREDIT_CONTRIBUTION: "مساهمة الساعات الفعلية",
  GROUP_REMAINING_BEFORE: "المتبقي للمجموعة قبلها",
  GROUP_REMAINING_AFTER: "المتبقي للمجموعة بعدها",
  COMPLETES_REQUIREMENT_GROUP: "تُكمل مجموعة المتطلبات",
  NEWLY_ELIGIBLE_COUNT: "مواد تصبح مؤهلة", PREVIOUSLY_ATTEMPTED: "محاولة سابقة",
  MAX_CREDIT_HOURS: "الحد الأقصى للساعات", MAX_COURSES: "الحد الأقصى للمواد",
  MAX_OPTIONS: "الحد الأقصى للخيارات", MAX_SEMESTERS_AHEAD: "أقصى عدد فصول مستقبلية",
  MAX_PATHS: "الحد الأقصى للمسارات", TOTAL_CREDIT_HOURS: "إجمالي الساعات",
  TOTAL_COURSES: "إجمالي المواد", MANDATORY_COURSE_COUNT: "مواد إلزامية",
  COMPLETED_PLAN_CREDIT_DELTA: "زيادة ساعات الخطة النموذجية",
  NEWLY_SATISFIED_GROUP_COUNT: "مجموعات مستوفاة حديثاً",
  RECOMMENDATION_RANK_SUM: "مجموع رتب التوصيات", SEMESTER_INDEX: "الفصل النموذجي",
  SEMESTER_COUNT: "عدد الفصول", TOTAL_PLANNED_COURSES: "إجمالي المواد المخططة",
  TOTAL_PLANNED_CREDITS: "إجمالي الساعات المخططة",
  FINAL_COMPLETED_CREDITS: "ساعات الخطة المكتملة نموذجياً",
  FINAL_REMAINING_CREDITS: "الساعات المتبقية نموذجياً",
  AGGREGATE_SEMESTER_RANK_SUM: "مجموع رتب الفصول", BLOCKER_CODE: "عائق قائم",
  POLICY_VERSION: "نسخة سياسة المحرك",
};

const valueLabels: Record<string, string> = {
  true: "نعم", false: "لا", required: "إلزامي", elective: "اختياري",
  RANKED: "توصية مرتبة", REVIEW_REQUIRED: "تتطلب مراجعة",
  EXCLUDED_IN_PROGRESS: "مستبعدة لأنها قيد الدراسة", MODELED_RESULT: "نتيجة نموذجية",
  AUTHORITATIVE_RESULT: "نتيجة المحرك الحتمي", ELIGIBLE: "مؤهل",
  NOT_ELIGIBLE: "غير مؤهل", NOT_ATTEMPTED: "لم تُحاول", ATTEMPTED_NOT_COMPLETED: "محاولة سابقة غير مكتملة",
  MODELED_COMPLETE: "مكتمل نموذجياً", HORIZON_REACHED: "بلغ حد الفصول",
  BLOCKED_BY_REVIEW_REQUIRED: "متوقف لحاجة إلى مراجعة",
  BLOCKED_BY_CURRENT_IN_PROGRESS: "متوقف بسبب مادة قيد الدراسة",
  NO_VALID_NEXT_PLAN: "لا يوجد فصل تالٍ صالح ضمن القيود",
  REQUIRED_PLAN_COURSE: "مادة مطلوبة في الخطة",
  MANDATORY_ZERO_CREDIT_COURSE: "مادة إلزامية بلا ساعات",
  ADVANCES_REQUIRED_GROUP: "تُقدّم مجموعة إلزامية",
  ADVANCES_ELECTIVE_REQUIREMENT: "تُقدّم متطلباً اختيارياً",
  COMPLETES_REQUIREMENT_GROUP: "تُكمل مجموعة متطلبات",
  UNLOCKS_FUTURE_COURSE: "تفتح مادة لاحقة",
  UNLOCKS_MULTIPLE_FUTURE_COURSES: "تفتح مواد لاحقة",
  NO_REMAINING_GROUP_NEED: "لا حاجة متبقية في المجموعة",
  PREVIOUSLY_ATTEMPTED: "لها محاولة سابقة",
  NO_DIRECT_PREREQUISITE_IMPACT: "لا تفتح متطلباً مباشراً",
  CONTAINS_MANDATORY_COURSES: "تتضمن مواد إلزامية",
  INCLUDES_ZERO_CREDIT_REQUIRED: "تتضمن مادة إلزامية بلا ساعات",
  COMPLETES_MULTIPLE_REQUIREMENT_GROUPS: "تُكمل عدة مجموعات",
  MAXIMIZES_MODELED_CREDIT_PROGRESS: "أعلى تقدم ساعات نموذجي",
  USES_FULL_CREDIT_PREFERENCE: "تستخدم سقف الساعات المطلوب",
  INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE: "تتضمن مادة ذات محاولة سابقة",
  REACHES_MODELED_PLAN_COMPLETION: "تبلغ إكمال الخطة نموذجياً",
  FEWER_MODELED_SEMESTERS: "فصول نموذجية أقل",
  MAXIMIZES_PROGRESS_WITHIN_HORIZON: "أعلى تقدم ضمن الأفق",
  COMPLETES_ALL_REQUIREMENT_GROUPS: "تُكمل كل المجموعات نموذجياً",
  NO_VALID_NEXT_SEMESTER: "لا يوجد فصل تالٍ صالح",
  REVIEW_REQUIRED_BLOCKER: "متطلب يحتاج مراجعة",
  CURRENT_IN_PROGRESS_BLOCKER: "مادة قيد الدراسة",
  PREREQUISITES_LOCKED: "متطلبات سابقة غير مستوفاة",
  PLAN_CONSTRAINTS_TOO_RESTRICTIVE: "قيود الخطة تمنع التقدم",
  CANDIDATE_WINDOW_EXCLUSION: "المرشح خارج نافذة البحث",
  PREREQUISITE_LOGIC_UNRESOLVED: "منطق المتطلبات غير محسوم",
  PREREQUISITE_SOURCE_CONFLICT: "مصادر المتطلبات متعارضة",
  VERIFIED_PREREQUISITE_MODEL_INCOMPLETE: "نموذج المتطلبات المعتمد غير مكتمل",
};

const nodeLabels: Record<string, string> = {
  RECOMMENDATION: "توصية", COURSE: "مادة", REASON: "سبب",
  REQUIREMENT_GROUP: "مجموعة متطلبات", CONSTRAINT: "قيد",
  SEMESTER: "خيار فصل", DEGREE_PATH: "مسار نموذجي",
  POLICY_VERSION: "نسخة سياسة", ACADEMIC_STATE: "حالة أكاديمية",
  LIMITATION: "حد التفسير", DECISION: "قرار", PREREQUISITE_GROUP: "مجموعة متطلبات سابقة",
};

const edgeLabels: Record<EligibilityGraphEdgeRelation, string> = {
  DECIDED_BY: "حُسم بسبب", REFERENCES: "يشير إلى", SUPPORTED_BY: "مدعوم بـ",
  SATISFIED_BY: "استوفي بواسطة", BLOCKED_BY: "متوقف بسبب", LIMITED_BY: "محدود بـ",
  CONTRIBUTES_TO: "يسهم في", CONSTRAINED_BY: "مقيّد بـ", SELECTED_IN: "يتضمن",
  LEADS_TO: "قد يفتح نموذجياً", VERSIONED_BY: "محسوب وفق", RANKED_AS: "يعرض",
};

const limitationLabels: Record<string, string> = {
  SOURCE_DOCUMENT_VERSION_UNAVAILABLE: "لا تتوفر نسخة وثيقة مصدر دقيقة من ناتج هذا المحرك.",
  WHY_NOT_EVIDENCE_UNAVAILABLE: "لا يتضمن الناتج الحالي سبباً موثوقاً لغياب هذه المادة عن نافذة التوصيات.",
  CURRENT_STORED_STATE: "يعكس الشرح الحالة الأكاديمية المخزنة حالياً.",
  NOT_OFFICIAL_REGISTRATION: "هذا تخطيط استرشادي، وليس تسجيلاً رسمياً.",
  MODELED_OUTCOME_NOT_HISTORICAL: "المواد والفصول المستقبلية نموذجية، وليست إنجازاً تاريخياً.",
};

function readableValue(fact: AcademicGraphFact): string {
  const raw = String(fact.value);
  if (/^\d+(\.\d+)?$/.test(raw)) return raw;
  return valueLabels[raw] ?? (fact.key === "POLICY_VERSION" ? raw : "قيمة معتمدة من المحرك");
}

function title(node: EligibilityGraphNode): string {
  const prefix = nodeLabels[node.type] ?? "حقيقة";
  const rank = node.facts?.find((fact) => fact.key === "RANK")?.value;
  const reference = node.course_code ?? node.reference_code;
  return `${prefix}${rank ? ` #${rank}` : ""}${reference ? `: ${reference}` : ""}`;
}

type Props = {
  graph: AcademicExplanationGraph | null;
  focusId: string;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  identities?: CourseIdentityMap;
};

export function AcademicGraphExplanation({ graph, focusId, loading, error, onRetry, identities }: Props) {
  const nodes = new Map(graph?.nodes.map((node) => [node.id, node]) ?? []);
  const root = nodes.get(focusId);

  const branch = (node: EligibilityGraphNode, depth: number, visited: Set<string>): React.ReactNode => {
    const relations = graph?.edges.filter((edge) => edge.from_node_id === node.id) ?? [];
    return <div className="space-y-2">
      <h4 className="text-sm font-bold text-[#F3E9D8]">{node.course_code || (node.type === "COURSE" && node.reference_code)
        ? <CourseIdentity courseCode={node.course_code ?? node.reference_code!} identities={identities} /> : title(node)}</h4>
      {node.facts?.length ? <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        {node.facts.map((fact, index) => <div key={`${fact.key}-${index}`} className="flex flex-wrap gap-1">
          <dt className="font-bold text-[#C6B69C]">{factLabels[fact.key] ?? "حقيقة"}:</dt>
          <dd className="text-[#F3E9D8]"><bdi>{readableValue(fact)}</bdi></dd>
        </div>)}
      </dl> : null}
      {depth < 3 && relations.length ? <ul className="space-y-2 border-r-2 border-[#C9A45C]/30 pr-3">
        {relations.map((edge) => {
          const child = nodes.get(edge.to_node_id);
          if (!child || visited.has(edge.to_node_id) || child.type === "LIMITATION") return null;
          return <li key={`${edge.relation}:${edge.to_node_id}`} className="rounded-xl border border-[#C9A45C]/30 bg-[#0B1210] p-3">
            <p className="mb-1 text-xs font-bold text-[#E2B671]">{edgeLabels[edge.relation]}</p>
            {branch(child, depth + 1, new Set([...visited, child.id]))}
          </li>;
        })}
      </ul> : null}
    </div>;
  };

  return <section dir="rtl" aria-label="لماذا هذه النتيجة؟"
    className="min-w-0 rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-4 text-right sm:p-5">
    <h3 className="text-sm font-bold text-[#F3E9D8]">لماذا هذه النتيجة؟</h3>
    {loading ? <p role="status" className="mt-2 text-xs">جارٍ تحميل التفسير...</p> : null}
    {!loading && error ? <div role="alert" className="mt-2 text-xs">
      <p>تعذر تحميل التفسير؛ النتيجة الأصلية أعلاه لا تتغير.</p>
      <button type="button" onClick={onRetry} className="mt-2 rounded-xl border px-3 py-2 font-bold">إعادة المحاولة</button>
    </div> : null}
    {!loading && !error && !root ? <p className="mt-2 text-xs">لا تتوفر تفاصيل تفسيرية لهذا العنصر.</p> : null}
    {!loading && !error && root ? <div className="mt-3 space-y-3">{branch(root, 0, new Set([root.id]))}</div> : null}
    {!loading && !error && graph?.limitations.length ? <div className="mt-4 border-t pt-3">
      <h4 className="text-xs font-bold">حدود التفسير</h4>
      <ul className="mt-1 list-inside list-disc space-y-1 text-xs text-[#C6B69C]">
        {graph.limitations.map((item) => <li key={item}>{limitationLabels[item] ?? "يوجد حد غير متاح للعرض."}</li>)}
      </ul>
    </div> : null}
  </section>;
}
