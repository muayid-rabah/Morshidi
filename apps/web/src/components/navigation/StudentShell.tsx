"use client";

import type { ComponentType, ReactNode, SVGProps } from "react";
import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/auth/auth-provider";
import {
  AdvisorIcon,
  CoursesIcon,
  DegreePathIcon,
  EligibilityIcon,
  HomeIcon,
  MenuIcon,
  MockRegistrationIcon,
  PlannerIcon,
  PoliciesIcon,
  ProfileIcon,
  ProgressIcon,
  RecommendationsIcon,
  CloseIcon,
} from "@/components/ui/Icons";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

type NavigationItem = {
  href: string;
  label: string;
  icon: IconComponent;
};

const navigationGroups: { label: string; items: NavigationItem[] }[] = [
  {
    label: "حسابي الأكاديمي",
    items: [
      { href: "/student/profile", label: "الملف الأكاديمي", icon: ProfileIcon },
      { href: "/student/progress", label: "التقدم الدراسي", icon: ProgressIcon },
      { href: "/student/courses", label: "المواد والدرجات", icon: CoursesIcon },
      { href: "/student/offerings", label: "المواد المطروحة", icon: MockRegistrationIcon },
    ],
  },
  {
    label: "التخطيط والإرشاد",
    items: [
      { href: "/student/planner", label: "خطة الفصل", icon: PlannerIcon },
      { href: "/student/advisor", label: "مرشدي", icon: AdvisorIcon },
      { href: "/student/recommendations", label: "توصيات المواد", icon: RecommendationsIcon },
      { href: "/student/eligibility", label: "أهلية التسجيل", icon: EligibilityIcon },
      { href: "/student/degree-path", label: "مسار التخرج", icon: DegreePathIcon },
    ],
  },
  {
    label: "مراجع وخدمات",
    items: [
      { href: "/student/roadmap", label: "الخطة الدراسية", icon: CoursesIcon },
      { href: "/student/policies", label: "اللوائح والسياسات", icon: PoliciesIcon },
      { href: "/student/mock-registration", label: "محاكاة التسجيل", icon: MockRegistrationIcon },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/student" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

function SidebarContent({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const auth = useAuth();

  return (
    <div className="flex h-full flex-col">
      <Link href="/student" onClick={onNavigate} aria-label="نظرة عامة" className="flex items-center gap-3 rounded-2xl p-3 transition-colors hover:bg-[#192720]">
        <span className="relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[#C9A45C]/40 bg-[#14201B]">
          <Image src="/brand/morshidi-guide.png" alt="مرشدي" fill sizes="44px" className="object-cover object-left" />
        </span>
        <span className="sidebar-brand-copy min-w-0">
          <span className="block text-sm font-extrabold text-[#F3E9D8]">مرشدي</span>
          <span className="block text-[11px] text-[#B7A78E]">المساحة الأكاديمية</span>
        </span>
      </Link>

      <div className="sidebar-brand-copy mx-3 mt-3 rounded-2xl border border-[#C9A45C]/20 bg-[#101915] p-3">
        <p className="text-[10px] font-bold tracking-wide text-[#B7A78E]">الحساب الحالي</p>
        <p className="mt-1 truncate text-xs font-semibold text-[#F3E9D8]" dir="ltr">{auth.user?.email ?? "حساب الطالب"}</p>
      </div>

      <nav className="mt-5 flex-1 space-y-5 overflow-y-auto px-2 pb-3" aria-label="التنقل الأكاديمي">
        <Link
          href="/student"
          onClick={onNavigate}
          aria-current={isActive(pathname, "/student") ? "page" : undefined}
          aria-label="نظرة عامة"
          title="نظرة عامة"
          className={`sidebar-nav-link flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-semibold transition-colors ${isActive(pathname, "/student") ? "bg-[#0E5A4F] text-white shadow-sm" : "text-[#E5D6C0] hover:bg-[#192720]"}`}
        >
          <HomeIcon className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
          <span className="sidebar-label">نظرة عامة</span>
        </Link>

        {navigationGroups.map((group) => (
          <section key={group.label} aria-label={group.label}>
            <h2 className="sidebar-section-label px-3 pb-2 text-[10px] font-bold tracking-wide text-[#948B79]">{group.label}</h2>
            <ul className="space-y-1">
              {group.items.map(({ href, label, icon: Icon }) => {
                const active = isActive(pathname, href);
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      aria-label={label}
                      title={label}
                      className={`sidebar-nav-link flex min-h-10 items-center gap-3 rounded-xl px-3 text-[13px] font-medium transition-colors ${active ? "bg-[#16362E] text-[#F3E9D8] ring-1 ring-inset ring-[#C9A45C]/35" : "text-[#C6B69C] hover:bg-[#0F1A17] hover:text-[#F3E9D8]"}`}
                    >
                      <Icon className={`h-[18px] w-[18px] shrink-0 ${active ? "text-[#D9884A]" : "text-[#948B79]"}`} aria-hidden="true" />
                      <span className="sidebar-label">{label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </nav>

      <div className="sidebar-brand-copy border-t border-[#C9A45C]/20 px-3 py-4">
        <p className="text-[10px] leading-5 text-[#B7A78E]">القرارات الأكاديمية تُحسب وفق القواعد المسجلة في خطتك.</p>
      </div>
    </div>
  );
}

export function StudentShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMobileOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const currentLabel = navigationGroups.flatMap((group) => group.items).find((item) => isActive(pathname, item.href))?.label
    ?? (pathname === "/student" ? "نظرة عامة" : "حسابي الأكاديمي");

  return (
    <div className="student-shell mx-auto w-full max-w-[1600px] px-3 pb-8 sm:px-5 lg:px-7" dir="rtl">
      <div className="flex items-center justify-between gap-4 border-b border-[#C9A45C]/20 py-4 lg:hidden">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="فتح القائمة الأكاديمية"
            aria-expanded={mobileOpen}
            aria-controls="student-mobile-navigation"
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[#C9A45C]/25 bg-[#14201B] text-[#E5D6C0] shadow-sm transition-colors hover:bg-[#0F1A17]"
          >
            <MenuIcon className="h-5 w-5" aria-hidden="true" />
          </button>
          <div className="min-w-0">
            <p className="truncate text-[11px] text-[#B7A78E]">المساحة الأكاديمية</p>
            <h1 className="truncate text-base font-bold text-[#F3E9D8]">{currentLabel}</h1>
          </div>
        </div>
        <Link href="/student/advisor" className="inline-flex min-h-10 shrink-0 items-center gap-2 rounded-xl bg-[#0E5A4F] px-3 text-xs font-semibold text-white transition-colors hover:bg-[#103D35]">
          <AdvisorIcon className="h-4 w-4" aria-hidden="true" />
          <span>اسأل مرشدي</span>
        </Link>
      </div>

      <div className="grid gap-5 py-5 lg:grid-cols-[5.1rem_minmax(0,1fr)] lg:gap-7" dir="rtl">
        <aside className="student-sidebar sticky top-[5.25rem] hidden h-[calc(100vh-6.5rem)] min-h-[38rem] rounded-2xl border border-[#C9A45C]/25 p-2 shadow-sm lg:block" aria-label="القائمة الأكاديمية">
          <SidebarContent pathname={pathname} />
        </aside>
        <section className="min-w-0">
          <div className="mb-5 hidden items-center justify-between rounded-2xl border border-[#C9A45C]/25 bg-[#14201B] px-5 py-4 shadow-sm lg:flex">
            <div>
              <p className="text-[11px] font-semibold text-[#B7A78E]">بوابتك الأكاديمية</p>
              <h1 className="mt-1 text-xl font-bold tracking-tight text-[#F3E9D8]">{currentLabel}</h1>
            </div>
            <Link href="/student/advisor" className="button-primary min-h-10 px-4 text-sm">
              <AdvisorIcon className="h-4 w-4" aria-hidden="true" />
              <span>اسأل مرشدي</span>
            </Link>
          </div>
          {children}
        </section>
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-[60] lg:hidden">
          <button type="button" className="absolute inset-0 h-full w-full cursor-default bg-slate-950/45" onClick={() => setMobileOpen(false)} aria-label="إغلاق القائمة الأكاديمية" />
          <aside id="student-mobile-navigation" className="absolute inset-y-0 right-0 w-[min(19rem,88vw)] overflow-y-auto bg-[#14201B] p-2 shadow-2xl" aria-label="القائمة الأكاديمية">
            <div className="mb-1 flex justify-end px-2 pt-2">
              <button type="button" onClick={() => setMobileOpen(false)} aria-label="إغلاق القائمة" className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-[#B7A78E] transition-colors hover:bg-[#192720] hover:text-[#F3E9D8]">
                <CloseIcon className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <SidebarContent pathname={pathname} onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
    </div>
  );
}
