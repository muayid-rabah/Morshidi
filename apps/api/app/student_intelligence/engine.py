from app.student_intelligence.difficulty import evaluate_difficulty
from app.student_intelligence.models import *
from app.student_intelligence.observations import evaluate_performance
from app.student_intelligence.readiness import evaluate_readiness
from app.student_intelligence.strengths import evaluate_strengths
from app.student_intelligence.structural_risk import evaluate_structural_risk, predictive_risk_boundary


def evaluate_student_intelligence(context: StudentIntelligenceContext, readiness: ReadinessContext | None = None) -> StudentIntelligenceBundle:
    return StudentIntelligenceBundle(POLICY_VERSION,evaluate_performance(context),evaluate_strengths(context),evaluate_difficulty(context),evaluate_structural_risk(context),predictive_risk_boundary(),evaluate_readiness(readiness) if readiness else None)
