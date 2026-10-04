"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import { useAuthenticatedApi } from "@/lib/api/use-authenticated-api";
import { StudentApiService } from "@/lib/api/student-api";
import { useCourseIdentities } from "@/lib/api/use-course-identities";
import { CourseDifficulty } from "@/components/academic/CourseDifficulty";
import { CourseIdentity } from "@/components/academic/CourseIdentity";
import { AcademicGraphExplanation } from "@/components/academic/AcademicGraphExplanation";
import type { AcademicExplanationGraph, AdaptiveCourseResponse, CreditTimelineResponse, CreditComparisonResponse,
  CreditTimelineRequest } from "@/lib/api/student-types";
import type {
  DegreePathOptionResponse,
  DegreePathRequest,
  DegreePathResponse,
  ModeledSemesterResponse,
  PlannedCourseEntryResponse,
} from "@/lib/api/student-types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { LoadingSkeletonCard } from "@/components/ui/LoadingSkeleton";
import { StatCard } from "@/components/ui/StatCard";
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  ClockIcon,
  CoursesIcon,
  DegreePathIcon,
  InfoIcon,
  CompassIcon,
} from "@/components/ui/Icons";

const PATH_STAGES = [
  "قراءة الخطة الدراسية والسجل الأكاديمي",
  "فحص المتطلبات السابقة والمواد المتبقية",
  "محاكاة المسارات الفصلية وترتيبها",
  "تجهيز نتيجة مسار التخرج",
] as const;

export default function DegreePathPage() {
  const auth = useAuth();
  const client = useAuthenticatedApi();
  const identities = useCourseIdentities(auth.isAuthenticated);

  // Constraints
  const [maxCreditsPerSemester, setMaxCreditsPerSemester] = useState<number>(15);
  const [maxSemestersAhead, setMaxSemestersAhead] = useState<number>(8);
  const [maxPaths, setMaxPaths] = useState<number>(2);
  const [regularLoad, setRegularLoad] = useState(15);
  const [summerEnabled, setSummerEnabled] = useState(false);
  const [summerLoad, setSummerLoad] = useState(6);
  const [graduationPace, setGraduationPace] = useState<"FASTEST" | "BALANCED" | "LOWER_LOAD">("BALANCED");
  const preferencesEdited = useRef(false);
  const comparisonRequestId = useRef(0);
  const [startYear, setStartYear] = useState(new Date().getFullYear());
  const [startTerm, setStartTerm] = useState<CreditTimelineRequest["start_term"]>("FIRST_SEMESTER");
  const [creditTimeline, setCreditTimeline] = useState<CreditTimelineResponse | null>(null);
  const [creditComparison, setCreditComparison] = useState<CreditComparisonResponse | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState(false);
  const [creditLoading, setCreditLoading] = useState(false);
  const [creditError, setCreditError] = useState<string | null>(null);

  // States
  const [result, setResult] = useState<DegreePathResponse | null>(null);
  const [adaptive, setAdaptive] = useState<AdaptiveCourseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedPathIndex, setSelectedPathIndex] = useState<number>(0);
  const [graph, setGraph] = useState<AcademicExplanationGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState(false);
  const lastGraphRequest = useRef<DegreePathRequest | null>(null);
  const graphRequestId = useRef(0);
  const requestId = useRef(0);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    let active = true;
    void new StudentApiService(client).getConversationPreferences().then((prefs) => {
      if (!active || preferencesEdited.current) return;
      if (!prefs || typeof prefs !== "object" || Array.isArray(prefs)) return;
      const regular = Number(prefs.regular_load);
      const summer = Number(prefs.summer_load);
      if (Number.isInteger(regular) && regular >= 3 && regular <= 30) setRegularLoad(regular);
      if (prefs.summer_enabled === "true" || prefs.summer_enabled === "false")
        setSummerEnabled(prefs.summer_enabled === "true");
      if (Number.isInteger(summer) && summer >= 3 && summer <= 9) setSummerLoad(summer);
      if (prefs.graduation_pace === "FASTEST" || prefs.graduation_pace === "BALANCED" || prefs.graduation_pace === "LOWER_LOAD")
        setGraduationPace(prefs.graduation_pace);
    }).catch(() => { /* Preferences are optional; no academic assumption is inferred. */ });
    return () => { active = false; };
  }, [auth.isAuthenticated, client]);

  const handleCreditTimeline = async (e: React.FormEvent) => {
    e.preventDefault(); setCreditLoading(true); setCreditError(null); setCreditTimeline(null);
    try {
      setCreditTimeline(await new StudentApiService(client).simulateCreditTimeline({
        regular_load: regularLoad, summer_enabled: summerEnabled,
        summer_load: summerEnabled ? summerLoad : 0,
        start_year: startYear, start_term: startTerm,
      }));
    } catch { setCreditError("تعذّر حساب المسار الائتماني. تأكد من الحمل والفصل المختارين."); }
    finally { setCreditLoading(false); }
  };

  const handleComparison = async () => {
    const currentId = ++comparisonRequestId.current;
    setComparisonLoading(true); setComparisonError(false); setCreditComparison(null);
    try {
      const comparison = await new StudentApiService(client).compareCreditTimelines({
        start_year: startYear, start_term: startTerm,
        preferred_regular_load: regularLoad,
        preferred_summer_enabled: summerEnabled,
        preferred_summer_load: summerEnabled ? summerLoad : undefined,
        graduation_pace: graduationPace,
      });
      if (currentId === comparisonRequestId.current) setCreditComparison(comparison);
    } catch { if (currentId === comparisonRequestId.current) setComparisonError(true); }
    finally { if (currentId === comparisonRequestId.current) setComparisonLoading(false); }
  };

  const loadGraph = async (request: DegreePathRequest) => {
    const currentId = ++graphRequestId.current;
    setGraphLoading(true);
    setGraphError(false);
    try {
      const nextGraph = await new StudentApiService(client).createDegreePathGraph(request);
      if (currentId === graphRequestId.current) setGraph(nextGraph);
    } catch {
      if (currentId === graphRequestId.current) setGraphError(true);
    } finally {
      if (currentId === graphRequestId.current) setGraphLoading(false);
    }
  };

  const handleGeneratePath = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoading(true);
    setErrorMessage(null);
    setResult(null);
    graphRequestId.current += 1;
    setGraph(null);
    setGraphError(false);
    const currentRequest = ++requestId.current;
    let timeoutSignal: AbortSignal | null = null;

    try {
      timeoutSignal = AbortSignal.timeout(60_000);
      const api = new StudentApiService(client);
      void api.getAdaptiveCourseIntelligence().then((intelligence) => {
        if (currentRequest === requestId.current) setAdaptive(intelligence);
      }).catch(() => { if (currentRequest === requestId.current) setAdaptive(null); });
      const req: DegreePathRequest = {
        max_credit_hours_per_semester: maxCreditsPerSemester,
        max_semesters_ahead: maxSemestersAhead,
        max_paths: maxPaths,
      };
      const data = await api.createDegreePaths(req, timeoutSignal);
      if (currentRequest !== requestId.current) return;
      setResult(data);
      setSelectedPathIndex(0);
      lastGraphRequest.current = req;
      void loadGraph(req);
    } catch {
      if (currentRequest !== requestId.current) return;
      setErrorMessage(timeoutSignal?.aborted
        ? "استغرق إنشاء مسار التخرج وقتًا أطول من المتوقع. حاول مرة أخرى."
        : "تعذر إنشاء مسار التخرج الآن. حاول مرة أخرى.");
    } finally {
      if (currentRequest === requestId.current) setLoading(false);
    }
  };

  const selectedPath: DegreePathOptionResponse | null =
    result?.paths && result.paths.length > selectedPathIndex
      ? result.paths[selectedPathIndex]
      : null;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-[#C9A45C]/30 pb-5">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[#0E5A4F]/10 px-2.5 py-0.5 text-xs font-bold text-[#D9884A]">
            محاكاة التخرج المتعددة الفصول
          </span>
          <span className="text-xs text-[#C6B69C]">تخطيط مسار الدرجة العلمية</span>
        </div>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#F3E9D8]">
          المسار الدراسي حتى التخرج
        </h1>
        <p className="text-xs text-[#C6B69C]">
          اختر تقديراً ائتمانياً سريعاً أو مساراً تفصيلياً للمواد. كلاهما نمذجة غير رسمية ولا يضمن التخرج أو توفر المواد.
        </p>
      </div>

      <section className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6" aria-label="محاكاة ائتمانية حتى التخرج">
        <h2 className="text-lg font-bold">مسار ائتماني سريع · Credit-only timeline</h2>
        <p className="text-xs text-[#C6B69C]">لا يلزم اختيار مواد. الحمل العادي افتراض تخطيطي، وليس حد تسجيل معتمداً من الجامعة.</p>
        <form onChange={() => { preferencesEdited.current = true; comparisonRequestId.current += 1; setComparisonLoading(false); setComparisonError(false); setCreditComparison(null); }} onSubmit={(e) => void handleCreditTimeline(e)} className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="text-sm">ساعات الفصل العادي / Regular credits
            <select value={regularLoad} onChange={(e) => setRegularLoad(Number(e.target.value))} className="mt-1 block w-full rounded-lg border p-2">
              {[12, 15, 18].map((value) => <option key={value} value={value}>{value}</option>)}
              {![12, 15, 18].includes(regularLoad) ? <option value={regularLoad}>{regularLoad} (preference)</option> : null}
            </select>
          </label>
          <label className="text-sm">السنة الأكاديمية التقريبية / Start year
            <input type="number" min={2000} max={2200} value={startYear} onChange={(e) => setStartYear(Number(e.target.value))} className="mt-1 block w-full rounded-lg border p-2" />
          </label>
          <label className="text-sm">الفصل القادم / Next term
            <select value={startTerm} onChange={(e) => setStartTerm(e.target.value as CreditTimelineRequest["start_term"])} className="mt-1 block w-full rounded-lg border p-2">
              <option value="FIRST_SEMESTER">الفصل الأول / First</option><option value="SECOND_SEMESTER">الفصل الثاني / Second</option><option value="SUMMER">الصيفي / Summer</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={summerEnabled} onChange={(e) => setSummerEnabled(e.target.checked)} /> تضمين الصيفي / Include summer</label>
          {summerEnabled ? <label className="text-sm">ساعات الصيفي / Summer credits
            <select value={summerLoad} onChange={(e) => setSummerLoad(Number(e.target.value))} className="mt-1 block w-full rounded-lg border p-2">
              {[3, 4, 5, 6, 7, 8, 9].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label> : null}
          <label className="text-sm">تفضيل وتيرة التخرج / Preferred pace
            <select value={graduationPace} onChange={e => setGraduationPace(e.target.value as typeof graduationPace)} className="mt-1 block w-full rounded-lg border p-2">
              <option value="FASTEST">الأسرع / Fastest</option><option value="BALANCED">المتوازن / Balanced</option><option value="LOWER_LOAD">الحمل الأخف / Lower load</option>
            </select>
          </label>
          <button type="submit" disabled={creditLoading} className="rounded-xl bg-[#D9884A] px-4 py-2 text-sm font-bold disabled:opacity-50">{creditLoading ? "جارٍ الحساب..." : "حساب المسار الائتماني"}</button>
        </form>
        {creditError ? <p role="alert" className="mt-3 text-sm text-[#F07869]">{creditError}</p> : null}
        {creditTimeline ? <div className="mt-4 space-y-2 text-sm">
          <p>المتبقي / Remaining: {creditTimeline.initial_remaining_credits} ساعة · فصول عادية / Regular: {creditTimeline.regular_semester_count} · صيفية / Summers: {creditTimeline.summer_count}</p>
          <p>الفصل المتوقع / Projected term: {creditTimeline.completion_term ?? "Already complete"} {creditTimeline.completion_year ?? ""}</p>
          <ol className="list-inside list-decimal">{creditTimeline.terms.map((term, index) => <li key={index}>{term.academic_year} · {term.term} · {term.planned_credits} ساعة · متبقي {term.remaining_after}</li>)}</ol>
          {creditTimeline.warnings.map((warning) => <p key={warning} className="text-amber-900">{warning}</p>)}
        </div> : null}
        <div className="mt-5 border-t pt-4">
          <button type="button" onClick={() => void handleComparison()} disabled={comparisonLoading}
            className="rounded-xl border border-[#D9884A] px-4 py-2 text-sm font-bold disabled:opacity-50">
            {comparisonLoading ? "جارٍ مقارنة السيناريوهات..." : "قارن: الأسرع · المتوازن · الحمل الأخف"}
          </button>
          {comparisonError ? <p role="alert" className="mt-2 text-sm text-[#F07869]">تعذّرت مقارنة السيناريوهات الائتمانية.</p> : null}
          {creditComparison ? <div className="mt-3 grid gap-3 md:grid-cols-3">
            {creditComparison.scenarios.map((scenario) => <article key={scenario.mode}
              className="rounded-xl border border-[#C9A45C]/30 bg-[#0B1210] p-3 text-sm">
              <h3 className="font-bold">{scenario.mode === "FASTEST" ? "الأسرع / Fastest" :
                scenario.mode === "BALANCED" ? "المتوازن / Balanced" : "الحمل الأخف / Lower load"}</h3>
              {scenario.preference_match ? <p className="text-green-800">يطابق تفضيلك المعلن / Matches your stated preference</p> : null}
              <p>{scenario.timeline.regular_load} ساعة عادية · {scenario.timeline.summer_enabled ?
                `${scenario.timeline.summer_load} صيفية` : "بدون صيفي"}</p>
              <p>{scenario.total_modeled_terms} فصل تقويمي تقريبي · {scenario.timeline.regular_semester_count} عادي · {scenario.timeline.summer_count} صيفي</p>
              <p>الاكتمال النموذجي: {scenario.timeline.completion_term ?? "مكتمل"} {scenario.timeline.completion_year ?? ""}</p>
              <p>العبء النموذجي: {scenario.workload_indicator}</p>
              <p>فصول إضافية مقارنة بالأسرع / Extra terms versus fastest: {scenario.total_modeled_terms - creditComparison.scenarios[0].total_modeled_terms}</p>
              <p className="text-xs text-amber-900">{scenario.provenance} · {scenario.confidence}</p>
              <p className="text-xs">{scenario.difficulty_evidence.startsWith("CURRENT_ELIGIBLE_COURSES_ONLY") ? "تراعي الموازنة صعوبة المواد المتاحة الآن؛ لم تُحدد مواد الفصول المستقبلية. Current eligible-course difficulty informs balance; future courses are unassigned." : "لا تتوفر أدلة كافية لتقدير صعوبة المواد المستقبلية. Future course difficulty is unknown."}</p>
            </article>)}
            <p className="md:col-span-3 text-xs text-amber-900">{creditComparison.limitations.join(" ")}</p>
          </div> : null}
        </div>
      </section>

      {/* Constraints Box */}
      <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-7 shadow-xs">
        <form onSubmit={handleGeneratePath} className="space-y-6">
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
            {/* Max Credits */}
            <div>
              <label className="block text-xs font-bold text-[#F3E9D8] mb-2">
                سقف الساعات لكل فصل *
              </label>
              <div className="flex items-center gap-2">
                {[12, 15, 18].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setMaxCreditsPerSemester(preset)}
                    className={`rounded-xl px-3 py-1.5 font-mono text-xs font-bold transition-colors ${
                      maxCreditsPerSemester === preset
                        ? "bg-[#D9884A] text-[#F3E9D8] shadow-xs"
                        : "bg-[#0F1A17] text-[#C6B69C] border border-[#C9A45C]/30 hover:bg-[#16362E]"
                    }`}
                  >
                    {preset} س
                  </button>
                ))}
                <input
                  type="number"
                  min={6}
                  max={21}
                  value={maxCreditsPerSemester}
                  onChange={(e) => setMaxCreditsPerSemester(Number(e.target.value))}
                  className="w-16 rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2 font-mono text-xs font-bold text-center text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
                />
              </div>
            </div>

            {/* Max Semesters Ahead */}
            <div>
              <label className="block text-xs font-bold text-[#F3E9D8] mb-2">
                المدى الزمني للمحاكاة (أقصى فصول)
              </label>
              <select
                value={maxSemestersAhead}
                onChange={(e) => setMaxSemestersAhead(Number(e.target.value))}
                className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 text-xs text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
              >
                <option value={4}>4 فصول دراسية (سنتان)</option>
                <option value={6}>6 فصول دراسية (3 سنوات)</option>
                <option value={8}>8 فصول دراسية (4 سنوات - موصى به)</option>
                <option value={10}>10 فصول دراسية (5 سنوات)</option>
              </select>
            </div>

            {/* Max Paths */}
            <div>
              <label className="block text-xs font-bold text-[#F3E9D8] mb-2">
                عدد سيناريوهات المسار
              </label>
              <select
                value={maxPaths}
                onChange={(e) => setMaxPaths(Number(e.target.value))}
                className="w-full rounded-xl border border-[#C9A45C]/30 bg-[#14201B] p-2.5 text-xs text-[#F3E9D8] focus:border-[#D9884A] focus:outline-hidden"
              >
                <option value={1}>مسار واحد (المسار الأسرع)</option>
                <option value={2}>مساران للمقارنة</option>
                <option value={3}>3 مسارات بديلة</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end pt-2 border-t border-[#C9A45C]/20">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[#D9884A] px-7 py-3 text-xs font-bold text-[#F3E9D8] shadow-xs hover:bg-[#0E5A4F] hover:text-white transition-all disabled:opacity-50"
            >
              <CompassIcon className="h-4 w-4" />
              <span>{loading ? "جاري محاكاة مسار التخرج..." : "توليد ومحاكاة مسار التخرج"}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Error */}
      {errorMessage ? (
        <div role="alert" className="rounded-2xl border border-[#F07869]/40 bg-[#351B17] p-5 text-xs text-[#F07869]">
          <p className="font-bold">{errorMessage}</p>
          <button type="button" onClick={() => void handleGeneratePath()} className="mt-3 rounded-lg border border-[#F07869]/50 px-3 py-1">إعادة المحاولة</button>
        </div>
      ) : null}

      {/* Loading */}
      {loading ? (
        <div role="status" aria-live="polite" className="space-y-6">
          <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-5 text-sm text-[#F3E9D8]">
            <p className="font-bold">جارٍ إعداد مسار التخرج...</p>
            <p className="mt-2 text-[#C6B69C]">يقرأ الخادم خطتك وسجلك الأكاديمي، ويفحص المتطلبات السابقة، ثم يحاكي المسارات. لا تصلنا حالة كل خطوة على حدة؛ سنعرض النتيجة عند اكتمال الحساب.</p>
            <ol className="mt-4 space-y-2" aria-label="مراحل إنشاء المسار">
              {PATH_STAGES.map((stage, index) => (
                <li key={stage} className="flex gap-2 text-[#C6B69C]">
                  <span aria-hidden="true">{index + 1}.</span>
                  <span>{stage} — قيد الانتظار من الخادم</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
            <LoadingSkeletonCard />
          </div>
          <LoadingSkeletonCard />
        </div>
      ) : null}

      {/* Result Path */}
      {!loading && result && result.paths.length > 0 ? (
        <div className="space-y-8">
          <div role="status" className="rounded-2xl border border-[#5B9974]/50 bg-[#16362E] p-4 text-sm text-[#B8DEBF]">
            ✓ اكتملت قراءة البيانات الأكاديمية وفحص المتطلبات ومحاكاة المسارات وتجهيز النتيجة.
          </div>
          {/* Paths Selection */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-[#C6B69C]">سيناريوهات المسار المتاحة:</span>
              {result.paths.map((p, idx) => (
                <button
                  key={p.rank}
                  type="button"
                  onClick={() => setSelectedPathIndex(idx)}
                  className={`rounded-2xl px-4 py-2 text-xs font-bold transition-all ${
                    selectedPathIndex === idx
                      ? "bg-[#D9884A] text-[#F3E9D8] shadow-xs font-extrabold"
                      : "bg-[#14201B] text-[#C6B69C] border border-[#C9A45C]/30 hover:bg-[#0F1A17]"
                  }`}
                >
                  المسار #{p.rank} ({p.semester_count} فصول)
                </button>
              ))}
            </div>

            <div className="text-xs text-[#C6B69C]">
              الساعات المكتسبة الحالية:{" "}
              <strong className="font-mono text-[#F3E9D8]">{result.initial_completed_credits} س</strong>
            </div>
          </div>

          {selectedPath ? (
            <div className="space-y-6">
              {/* Path Overview Cards */}
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <StatCard
                  title="حالة المسار"
                  value={selectedPath.status === "COMPLETE" ? "تخرج كامل" : selectedPath.status}
                  subtitle={
                    selectedPath.status === "COMPLETE"
                      ? "يضمن استيفاء متطلبات التخرج 100%"
                      : "مسار جزئي ضمن سقف الفصول"
                  }
                  icon={<CheckCircleIcon className="h-5 w-5" />}
                  variant={selectedPath.status === "COMPLETE" ? "gold" : "warm"}
                />
                <StatCard
                  title="عدد الفصول المتوقعة"
                  value={`${selectedPath.semester_count} فصول`}
                  subtitle="لإتمام كافة المواد المتبقية"
                  icon={<ClockIcon className="h-5 w-5" />}
                />
                <StatCard
                  title="إجمالي الساعات المخططة"
                  value={`${selectedPath.total_planned_credits} س`}
                  subtitle={`موزعة على ${selectedPath.total_planned_courses} مادة`}
                  icon={<CoursesIcon className="h-5 w-5" />}
                />
                <StatCard
                  title="الرصيد المتبقي عند الانتهاء"
                  value={`${selectedPath.final_remaining_plan_credits} س`}
                  subtitle={
                    selectedPath.final_remaining_plan_credits === 0
                      ? "تصفير كامل لمتطلبات الخطة"
                      : "ساعات متبقية بعد أقصى مدى"
                  }
                  icon={<CompassIcon className="h-5 w-5" />}
                />
              </div>

              {/* Semester Stepper Timeline */}
              <div className="space-y-6">
                <div className="border-b border-[#C9A45C]/30 pb-3">
                  <h2 className="text-base font-bold text-[#F3E9D8]">
                    التوزيع الفصلي المقترح للمسار #{selectedPath.rank}
                  </h2>
                  <p className="text-xs text-[#C6B69C]">
                    تسلسل الفصول القادمة والمواد المجدولة في كل فصل وفق شجرة المتطلبات السابقة.
                  </p>
                </div>

                <div className="relative space-y-6 before:absolute before:right-6 before:top-4 before:bottom-4 before:w-0.5 before:bg-[#C9A45C]">
                  {selectedPath.semesters.map((sem: ModeledSemesterResponse) => (
                    <div key={sem.semester_index} className="relative pr-14">
                      {/* Timeline Dot */}
                      <div className="absolute right-3.5 top-5 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full bg-[#D9884A] font-mono text-xs font-bold text-[#F3E9D8] ring-4 ring-white shadow-xs">
                        {sem.semester_index}
                      </div>

                      {/* Semester Card */}
                      <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-xs space-y-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b border-[#C9A45C]/20 pb-3">
                          <div>
                            <span className="font-mono text-xs font-bold text-[#D9884A]">
                              الفصل الدراسي القادم #{sem.semester_index}
                            </span>
                            <h3 className="text-sm font-bold text-[#F3E9D8]">
                              عبء فصلي: {sem.plan_option.total_credit_hours} ساعات معتمدة ({sem.plan_option.total_courses} مواد)
                            </h3>
                          </div>

                          <div className="flex items-center gap-2 text-xs">
                            <span className="text-[#C6B69C]">الرصيد بعد هذا الفصل:</span>
                            <span className="font-mono font-bold text-[#9DCEA9]">
                              {sem.completed_plan_credits_after} س منجزة
                            </span>
                            <span className="text-[11px] text-[#C6B69C]">
                              (المتبقي: {sem.remaining_plan_credits_after} س)
                            </span>
                          </div>
                        </div>

                        {/* Courses in this semester */}
                        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                          {sem.plan_option.courses.map((course: PlannedCourseEntryResponse) => (
                            <div
                              key={course.course_code}
                              className="flex items-center justify-between rounded-2xl border border-[#C9A45C]/30 bg-[#0B1210] p-3 text-xs"
                            >
                              <div>
                                <CourseIdentity courseCode={course.course_code} nameAr={course.course_name_ar} nameEn={course.course_name_en} />
                                <CourseDifficulty course={adaptive?.courses.find((item) => item.course_code === course.course_code)} />
                              </div>

                              <div className="text-left font-mono">
                                <span className="rounded-md bg-[#16362E] px-2 py-0.5 text-[10px] font-bold text-[#E2B671]">
                                  {course.credit_hours} س
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>

                        {sem.newly_satisfied_requirement_group_codes.length > 0 ? (
                          <div className="flex items-center gap-2 pt-2 text-xs text-[#9DCEA9]">
                            <CheckCircleIcon className="h-4 w-4 shrink-0" />
                            <span>
                              يستوفي هذا الفصل مجموعات المتطلبات:{" "}
                              <strong>{sem.newly_satisfied_requirement_group_codes.join(", ")}</strong>
                            </span>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <AcademicGraphExplanation graph={graph} identities={identities} focusId={`degree-path:${selectedPath.rank}`}
                loading={graphLoading} error={graphError}
                onRetry={() => { if (lastGraphRequest.current) void loadGraph(lastGraphRequest.current); }} />

              {/* Disclaimer */}
              <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-xs text-[#C6B69C] flex items-center gap-3">
                <InfoIcon className="h-5 w-5 text-[#D9884A] shrink-0" />
                <p>
                  <strong>إخلاء مسؤولية تنظيمي:</strong> مسار الدرجة العلمية هو نموذج محاكاة استرشادي مبني على التسلسل المنطقي لفتح المتطلبات السابقة. قد يتغير ترتيب التسجيل الفعلي تبعاً للمواد المطروحة في الجداول الدراسية لكل فصل.
                </p>
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        !loading && (
          <EmptyState
            title="ابدأ محاكاة مسار التخرج"
            description="حدد سقف الساعات الفصلي وعدد الفصول المرغوبة واضغط على 'توليد ومحاكاة مسار التخرج' لحساب الخطة حتى التخرج."
            icon={<DegreePathIcon className="h-7 w-7" />}
          />
        )
      )}
    </div>
  );
}
