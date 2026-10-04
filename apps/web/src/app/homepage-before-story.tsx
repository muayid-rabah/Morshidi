"use client";

import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { useAuth } from "@/auth/auth-provider";
import {
  AdvisorIcon,
  DegreePathIcon,
  EligibilityIcon,
  PlannerIcon,
  ProgressIcon,
  CompassIcon,
  MockRegistrationIcon,
} from "@/components/ui/Icons";
import { AstrolabeMark, PathNode } from "@/components/ui/VisualPrimitives";

interface DemoTrack {
  id: string;
  name: string;
  courseCompleted: { code: string; name: string; grade: string; state: "منجزة بنجاح" };
  courseEligible: { code: string; name: string; credits: number; state: "مؤهل للتسجيل الآن" };
  courseLocked: { code: string; name: string; missing: string; state: "غير متاحة حالياً" };
  explanation: string;
}

const DEMO_TRACKS: DemoTrack[] = [
  {
    id: "ai",
    name: "مسار الذكاء الاصطناعي والخوارزميات",
    courseCompleted: { code: "CS-101", name: "مقدمة في البرمجة", grade: "A", state: "منجزة بنجاح" },
    courseEligible: { code: "CS-201", name: "تراكيب البيانات والخوارزميات", credits: 3, state: "مؤهل للتسجيل الآن" },
    courseLocked: { code: "CS-401", name: "تعلم الآلة والذكاء الاصطناعي", missing: "يتطلب اجتياز CS-201 أولاً", state: "غير متاحة حالياً" },
    explanation: "قررت القواعد الحتمية أهلية CS-201 لاجتياز المتطلب السابق (CS-101)، بينما قُفلت CS-401 حتى استيفاء تراكيب البيانات بنجاح.",
  },
  {
    id: "data",
    name: "مسار قواعد البيانات وهندسة النظم",
    courseCompleted: { code: "CS-105", name: "أساسيات نظم المعلومات", grade: "B+", state: "منجزة بنجاح" },
    courseEligible: { code: "CS-220", name: "إدارة قواعد البيانات ونمذجتها", credits: 3, state: "مؤهل للتسجيل الآن" },
    courseLocked: { code: "CS-350", name: "الأنظمة الموزعة والسحابية", missing: "يتطلب اجتياز CS-220 أولاً", state: "غير متاحة حالياً" },
    explanation: "المادة CS-220 متاحة لأن متطلبها الأساسي مستوفى، ولا يمكن الانتقال للأنظمة السحابية قبل تسجيل واجتياز قواعد البيانات.",
  },
  {
    id: "security",
    name: "مسار الأمن السيبراني والشبكات",
    courseCompleted: { code: "CS-110", name: "مبادئ شبكات الحاسب", grade: "A-", state: "منجزة بنجاح" },
    courseEligible: { code: "CS-230", name: "أمن الشبكات والبروتوكولات", credits: 3, state: "مؤهل للتسجيل الآن" },
    courseLocked: { code: "CS-440", name: "التحليل الجنائي الرقمي واختبار الاختراق", missing: "يتطلب اجتياز CS-230 أولاً", state: "غير متاحة حالياً" },
    explanation: "استوفيت متطلب شبكات الحاسب ففتحت لك مادة أمن الشبكات، وتبقى مادة الاختبار الجنائي مقفلة نظامياً حتى إتمام متطلبها.",
  },
];

export default function Home() {
  const auth = useAuth();
  const [activeTrack, setActiveTrack] = useState<DemoTrack>(DEMO_TRACKS[0]);

  return (
    <div className="morshidi-home space-y-20 pb-20">
      {/* 1. Hero Section with 3D Mascot */}
      <section className="morshidi-hero relative overflow-hidden border-b border-[#C9A45C]/30 bg-gradient-to-b from-[#0F1A17] via-[#0B1210] to-[#0B1210] pt-12 pb-20 sm:pt-16 sm:pb-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" dir="rtl">
          {/* Personalized banner if logged in */}
          {auth.isAuthenticated && (
            <div className="mb-8 rounded-2xl border border-[#C9A45C]/30 bg-[#16362E]/70 p-4 shadow-xs">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#0E5A4F] text-white">
                    <CompassIcon className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-sm font-bold text-[#F3E9D8]">
                      مرحباً بك مجدداً،{" "}
                      <span className="font-mono text-[#E2B671]" dir="ltr">
                        {auth.user?.email}
                      </span>
                    </h2>
                    <p className="text-xs text-[#C6B69C]">
                      أدواتك الأكاديمية جاهزة ومحدثة وفق سجلك الفعلي في النظام.
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Link
                    href="/student"
                    className="inline-flex items-center gap-1.5 rounded-xl bg-[#0E5A4F] px-4 py-2 text-xs font-bold text-white shadow-2xs hover:bg-[#14796B] transition-colors"
                  >
                    <span>افتح حسابي الأكاديمي</span>
                    <span>←</span>
                  </Link>
                  <Link
                    href="/student/planner"
                    className="inline-flex items-center gap-1.5 rounded-xl border border-[#C9A45C]/30 bg-[#14201B] px-3 py-2 text-xs font-semibold text-[#F3E9D8] hover:bg-[#0F1A17] transition-colors"
                  >
                    <span>خطط لفصلك</span>
                  </Link>
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-8">
            {/* Right Column: Copy & Value Proposition */}
            <div className="lg:col-span-7">
              <div className="inline-flex items-center gap-2 rounded-full border border-[#C9A45C]/30 bg-[#16362E] px-4 py-1.5 text-xs font-bold text-[#E2B671]">
                <CompassIcon className="h-4 w-4 text-[#D9884A]" />
                <span>دليلك الأكاديمي</span>
              </div>

              <h1 className="mt-5 text-3xl font-extrabold tracking-tight text-[#F3E9D8] sm:text-4xl lg:text-5xl lg:leading-tight">
                مسارك الجامعي، أوضح.
              </h1>

              <p className="mt-5 text-base leading-relaxed text-[#C6B69C] sm:text-lg">
                خطة أوضح، وخطوة أقرب نحو التخرج.
              </p>

              {/* CTAs */}
              <div className="mt-8 flex flex-wrap items-center gap-4">
                {auth.isAuthenticated ? (
                  <>
                    <Link
                      href="/student"
                      className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#0E5A4F] px-6 py-3 text-sm font-bold text-white shadow-sm hover:bg-[#14796B] transition-all active:scale-95"
                    >
                      <span>الانتقال إلى حسابي</span>
                      <span>←</span>
                    </Link>
                    <Link
                      href="/student/progress"
                      className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-[#C9A45C]/30 bg-[#14201B] px-6 py-3 text-sm font-bold text-[#F3E9D8] shadow-2xs hover:bg-[#0F1A17] transition-colors"
                    >
                      <span>متابعة خطتي الأكاديمية</span>
                    </Link>
                  </>
                ) : (
                  <>
                    <Link
                      href="/login"
                      className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-[#0E5A4F] px-6 py-3 text-sm font-bold text-white shadow-sm hover:bg-[#14796B] transition-all active:scale-95"
                    >
                      <span>دخول الطالب</span>
                      <span>←</span>
                    </Link>
                    <a
                      href="#demo"
                      className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-[#C9A45C]/30 bg-[#14201B] px-6 py-3 text-sm font-bold text-[#F3E9D8] shadow-2xs hover:bg-[#0F1A17] transition-colors"
                    >
                      <span>جرّب محاكي الأهلية التفاعلي</span>
                    </a>
                  </>
                )}
              </div>

              {/* Trust Indicators */}
              <div className="mt-10 grid grid-cols-3 gap-4 border-t border-[#C9A45C]/20 pt-6 text-right">
                <div>
                  <div className="text-xl font-extrabold text-[#D9884A] sm:text-2xl">100%</div>
                  <div className="mt-1 text-xs font-medium text-[#C6B69C]">قواعد حتمية لا تهلوس</div>
                </div>
                <div>
                  <div className="text-xl font-extrabold text-[#D9884A] sm:text-2xl">SHA-256</div>
                  <div className="mt-1 text-xs font-medium text-[#C6B69C]">سجل قرارات مشفر للتدقيق</div>
                </div>
                <div>
                  <div className="text-xl font-extrabold text-[#D9884A] sm:text-2xl">عربي أولاً</div>
                  <div className="mt-1 text-xs font-medium text-[#C6B69C]">بنية جامعية مخصصة بالكامل</div>
                </div>
              </div>
            </div>

            {/* Left Column: Mascot & Interactive Floating Cards */}
            <div className="relative flex items-center justify-center lg:col-span-5">
              <div className="relative flex w-full max-w-sm flex-col items-center">
                <AstrolabeMark className="hero-astrolabe astrolabe-mark text-[#C9A45C]" />

                <div className="guide-portrait relative z-10 h-[min(70svh,39rem)] w-full max-w-[21rem] overflow-visible sm:max-w-[24rem]">
                  <Image
                    src="/brand/morshidi-guide-cutout.png"
                    alt="مرشدي، دليلك الأكاديمي"
                    fill
                    sizes="(max-width: 640px) 78vw, 384px"
                    className="h-full w-full object-contain"
                    priority
                  />
                </div>

                <div className="degree-path-preview relative z-20 -mt-8 flex w-full items-center justify-center gap-2 px-1 sm:-mt-10" aria-label="مراحل المسار الدراسي">
                  <PathNode code={activeTrack.courseCompleted.code} state="complete" label="منجزة" />
                  <PathNode code={activeTrack.courseEligible.code} hours={activeTrack.courseEligible.credits} state="current" label="متاحة" />
                  <PathNode code={activeTrack.courseLocked.code} state="locked" label="لاحقًا" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Interactive Prerequisite Simulator Section */}
      <section id="demo" className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" dir="rtl">
        <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-sm sm:p-10">
          <div className="text-center">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-[#16362E] px-3.5 py-1 text-xs font-bold text-[#E2B671]">
              <CompassIcon className="h-3.5 w-3.5 text-[#D9884A]" />
              <span>محاكاة تفاعلية حية</span>
            </div>
            <h2 className="mt-3 text-2xl font-bold text-[#F3E9D8] sm:text-3xl">
              شاهد كيف تحسب القواعد الحتمية أهليتك للمواد
            </h2>
            <p className="mx-auto mt-2 max-w-2xl text-xs leading-relaxed text-[#C6B69C] sm:text-sm">
              اختر مساراً تخصصياً وشاهد كيف تترابط المواد تسلسلياً: مادة اجتزتها، ومادة فُتحت للتسجيل، ومادة أُغلقت لعدم اكتمال متطلبها.
            </p>
          </div>

          {/* Track selector buttons */}
          <div className="mt-8 flex flex-wrap justify-center gap-2">
            {DEMO_TRACKS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTrack(t)}
                className={`rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                  activeTrack.id === t.id
                    ? "bg-[#0E5A4F] text-white shadow-xs"
                    : "border border-[#C9A45C]/30 bg-[#0F1A17] text-[#F3E9D8] hover:bg-[#16362E]"
                }`}
              >
                {t.name}
              </button>
            ))}
          </div>

          {/* Dependency Chain Display */}
          <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
            {/* Step 1: Completed Course */}
            <div className="relative rounded-2xl border border-[#5B9974]/50 bg-[#16362E]/60 p-5">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-[#1A4738] px-2.5 py-0.5 text-[10px] font-bold text-[#9DCEA9]">
                  {activeTrack.courseCompleted.state}
                </span>
                <span className="font-mono text-xs font-bold text-[#B8DEBF]" dir="ltr">
                  درجة: {activeTrack.courseCompleted.grade}
                </span>
              </div>
              <h3 className="mt-3 text-base font-bold text-[#F3E9D8]">
                {activeTrack.courseCompleted.name}
              </h3>
              <p className="mt-1 font-mono text-xs font-semibold text-[#C6B69C]" dir="ltr">
                {activeTrack.courseCompleted.code}
              </p>
              <div className="mt-3 text-[11px] text-[#9DCEA9]">
                ✓ متطلب أساسي تم إنجازه بنجاح.
              </div>
            </div>

            {/* Step 2: Eligible Course */}
            <div className="relative rounded-2xl border-2 border-[#D9884A] bg-[#16362E]/40 p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-[#D9884A]/30 px-2.5 py-0.5 text-[10px] font-bold text-[#E2B671]">
                  {activeTrack.courseEligible.state}
                </span>
                <span className="font-mono text-xs font-bold text-[#E2B671]">
                  {activeTrack.courseEligible.credits} ساعات
                </span>
              </div>
              <h3 className="mt-3 text-base font-bold text-[#F3E9D8]">
                {activeTrack.courseEligible.name}
              </h3>
              <p className="mt-1 font-mono text-xs font-semibold text-[#C6B69C]" dir="ltr">
                {activeTrack.courseEligible.code}
              </p>
              <div className="mt-3 text-[11px] font-semibold text-[#E2B671]">
                ★ مفتوحة للتسجيل الفصلي القادم مباشرة.
              </div>
            </div>

            {/* Step 3: Locked Course */}
            <div className="relative rounded-2xl border border-[#F07869]/40 bg-[#351B17]/50 p-5 opacity-90">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-[#47231D] px-2.5 py-0.5 text-[10px] font-bold text-[#F07869]">
                  {activeTrack.courseLocked.state}
                </span>
                <span className="text-xs font-bold text-[#F07869]">مغلقة 🔒</span>
              </div>
              <h3 className="mt-3 text-base font-bold text-[#F3E9D8]">
                {activeTrack.courseLocked.name}
              </h3>
              <p className="mt-1 font-mono text-xs font-semibold text-[#C6B69C]" dir="ltr">
                {activeTrack.courseLocked.code}
              </p>
              <div className="mt-3 text-[11px] text-[#F07869]">
                ⚠ {activeTrack.courseLocked.missing}
              </div>
            </div>
          </div>

          {/* Engine Rationale Banner */}
          <div className="mt-6 rounded-xl border border-[#C9A45C]/30 bg-[#0F1A17] p-4 text-xs">
            <div className="flex items-center gap-2 font-bold text-[#E2B671]">
              <CompassIcon className="h-4 w-4" />
              <span>حكم المحرك الحتمي:</span>
            </div>
            <p className="mt-1 leading-relaxed text-[#F3E9D8]">
              {activeTrack.explanation}
            </p>
            <div className="mt-2 text-[10px] text-[#C6B69C]">
              * هذه محاكاة تفاعلية تجريبية. عند تسجيل الدخول، يقرأ مرشدي سجلك الفعلي ويُطبّق القواعد على خطتك الدراسية مباشرة.
            </div>
          </div>
        </div>
      </section>

      {/* 3. Core Capabilities Section */}
      <section id="features" className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" dir="rtl">
        <div className="text-center">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-[#16362E] px-3.5 py-1 text-xs font-bold text-[#E2B671]">
            <CompassIcon className="h-3.5 w-3.5 text-[#D9884A]" />
            <span>منظومة متكاملة في مكان واحد</span>
          </div>
          <h2 className="mt-3 text-2xl font-bold text-[#F3E9D8] sm:text-3xl">
            أدواتك الأكاديمية كجزء طبيعي من الموقع
          </h2>
          <p className="mx-auto mt-2 max-w-2xl text-xs leading-relaxed text-[#C6B69C] sm:text-sm">
            لا داعي للتنقل بين أنظمة منفصلة ولوحات إدارة معقدة. كل أداة صُممت لتخدم رحلتك نحو التخرج.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {/* Feature 1 */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs hover:shadow-xs transition-shadow">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#16362E] text-[#D9884A]">
              <ProgressIcon className="h-6 w-6" />
            </div>
            <h3 className="mt-4 text-base font-bold text-[#F3E9D8]">
              متابعة التقدم في الخطة
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              تحليل شامل لكل متطلبات كليتك وقسمك؛ يبيّن لك المجموعات المستوفاة، الساعات المتبقية، والنسبة المئوية لإنجاز الدرجة.
            </p>
            <div className="mt-4">
              <Link href="/student/progress" className="text-xs font-bold text-[#D9884A] hover:underline">
                استعرض خطتك الأكاديمية ←
              </Link>
            </div>
          </div>

          {/* Feature 2 */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs hover:shadow-xs transition-shadow">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#16362E] text-[#D9884A]">
              <EligibilityIcon className="h-6 w-6" />
            </div>
            <h3 className="mt-4 text-base font-bold text-[#F3E9D8]">
              فحص أهلية المواد قطيعاً
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              أدخل رمز أي مادة ترغب بتسجيلها، وتلقَّ قراراً قطعياً مدعوماً بسند المتطلبات الأكاديمية واللوائح الجامعية.
            </p>
            <div className="mt-4">
              <Link href="/student/eligibility" className="text-xs font-bold text-[#D9884A] hover:underline">
                افحص أهلية مادة ←
              </Link>
            </div>
          </div>

          {/* Feature 3 */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs hover:shadow-xs transition-shadow">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#16362E] text-[#D9884A]">
              <PlannerIcon className="h-6 w-6" />
            </div>
            <h3 className="mt-4 text-base font-bold text-[#F3E9D8]">
              مخطط الفصل الدراسي الذكي
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              حدد سقف الساعات والعبء الدراسي الأنسب لك، وسيقوم المحرك باقتراح أفضل باقة مواد متوافقة مع شجرة تخرجك.
            </p>
            <div className="mt-4">
              <Link href="/student/planner" className="text-xs font-bold text-[#D9884A] hover:underline">
                ابدأ تخطيط فصلك ←
              </Link>
            </div>
          </div>

          {/* Feature 4 */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs hover:shadow-xs transition-shadow">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#16362E] text-[#D9884A]">
              <DegreePathIcon className="h-6 w-6" />
            </div>
            <h3 className="mt-4 text-base font-bold text-[#F3E9D8]">
              مسار التخرج المتوقع
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              توقع خط زمني فصلاً بفصل حتى التخرج. يحسب الفصول المطلوبة لتفادي التأخر ومعرفة المواد الحرجة في كل مرحلة.
            </p>
            <div className="mt-4">
              <Link href="/student/degree-path" className="text-xs font-bold text-[#D9884A] hover:underline">
                استكشف مسار التخرج ←
              </Link>
            </div>
          </div>

          {/* Feature 5 */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs hover:shadow-xs transition-shadow">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#16362E] text-[#D9884A]">
              <MockRegistrationIcon className="h-6 w-6" />
            </div>
            <h3 className="mt-4 text-base font-bold text-[#F3E9D8]">
              محاكاة التسجيل التجريبي
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              جرّب باقاتك المفضلة وسجل رغباتك غير الملزمة، مما يتيح لك وللكلية معرفة حجم الإقبال على الشُعب مسبقاً.
            </p>
            <div className="mt-4">
              <Link href="/student/mock-registration" className="text-xs font-bold text-[#D9884A] hover:underline">
                جرّب التسجيل التجريبي ←
              </Link>
            </div>
          </div>

          {/* Feature 6 */}
          <div className="rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs hover:shadow-xs transition-shadow">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#16362E] text-[#D9884A]">
              <AdvisorIcon className="h-6 w-6" />
            </div>
            <h3 className="mt-4 text-base font-bold text-[#F3E9D8]">
              مرشدي
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              يفسر أهليتك ويشير إلى مصادرها.
            </p>
            <div className="mt-4">
              <Link href="/student/advisor" className="text-xs font-bold text-[#D9884A] hover:underline">
                اسأل مرشدي ←
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* 4. How Morshidi Works (4 Steps) */}
      <section id="how-it-works" className="border-y border-[#C9A45C]/30 bg-[#0F1A17]/50 py-16" dir="rtl">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-[#16362E] px-3.5 py-1 text-xs font-bold text-[#E2B671]">
              <CompassIcon className="h-3.5 w-3.5 text-[#D9884A]" />
              <span>خطوات واضحة وبسيطة</span>
            </div>
            <h2 className="mt-3 text-2xl font-bold text-[#F3E9D8] sm:text-3xl">
              كيف يعمل مرشدي في رحلتك الدراسية؟
            </h2>
          </div>

          <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs">
              <div className="text-2xl font-extrabold text-[#D9884A]">01</div>
              <h3 className="mt-3 text-base font-bold text-[#F3E9D8]">سجل دخولك</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              بحسابك الجامعي.
              </p>
            </div>

            <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs">
              <div className="text-2xl font-extrabold text-[#D9884A]">02</div>
              <h3 className="mt-3 text-base font-bold text-[#F3E9D8]">قراءة مسارك</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              خطتك وسجلك.
              </p>
            </div>

            <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs">
              <div className="text-2xl font-extrabold text-[#D9884A]">03</div>
              <h3 className="mt-3 text-base font-bold text-[#F3E9D8]">التحليل الحتمي</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              فحص المتطلبات السابقة.
              </p>
            </div>

            <div className="rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-6 shadow-2xs">
              <div className="text-2xl font-extrabold text-[#D9884A]">04</div>
              <h3 className="mt-3 text-base font-bold text-[#F3E9D8]">اتخاذ القرار بثقة</h3>
              <p className="mt-2 text-xs leading-relaxed text-[#C6B69C]">
              خيارات فصل أوضح.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 5. Governance & Invariant Section */}
      <section id="about" className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" dir="rtl">
        <div className="overflow-hidden rounded-3xl border border-[#C9A45C]/30 bg-[#14201B] p-8 shadow-xs sm:p-12">
          <div className="max-w-3xl">
            <span className="rounded-full bg-[#0E5A4F]/10 px-3 py-1 text-xs font-bold text-[#D9884A]">
              وضوح أكاديمي
            </span>
            <h2 className="mt-4 text-2xl font-extrabold text-[#F3E9D8] sm:text-3xl lg:text-4xl">
              القواعد الأكاديمية هي المرجع.
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-[#C6B69C] sm:text-base">
              خطتك وسجلك ولوائح جامعتك في مكان واحد.
            </p>

          </div>
        </div>
      </section>

      {/* 6. Final Call to Action with Mascot */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" dir="rtl">
        <div className="relative overflow-hidden rounded-3xl border border-[#C9A45C]/30 bg-[#16362E] p-8 text-center shadow-sm sm:p-12">
          <div className="mx-auto flex h-24 w-24 items-center justify-center overflow-hidden rounded-2xl border border-[#C9A45C]/30 bg-[#14201B] p-2 shadow-2xs">
            <Image
              src="/brand/morshidi-guide.png"
              alt="مرشدي"
              width={80}
              height={80}
              className="object-contain"
            />
          </div>
          <h2 className="mt-4 text-2xl font-bold text-[#F3E9D8] sm:text-3xl">
            جاهز لبدء تجربة أكاديمية أوضح؟
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-xs text-[#C6B69C] sm:text-sm">
            انضم لمرشدي اليوم، واجعل كل قرار دراسي مدعوماً باليقين والسند الموثق.
          </p>
          <div className="mt-6 flex justify-center gap-4">
            {auth.isAuthenticated ? (
              <Link
                href="/student"
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[#0E5A4F] px-6 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#14796B] transition-colors"
              >
                <span>الانتقال إلى حسابي</span>
                <span>←</span>
              </Link>
            ) : (
              <Link
                href="/login"
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[#0E5A4F] px-6 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#14796B] transition-colors"
              >
                <span>دخول الطالب الآن</span>
                <span>←</span>
              </Link>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
