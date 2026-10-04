import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";
import { LoginForm } from "@/auth/login-form";
import { MorshidiLogo } from "@/components/ui/Icons";
import { AstrolabeMark } from "@/components/ui/VisualPrimitives";

export default function LoginPage() {
  return (
    <main data-page="login" className="login-page flex items-center justify-center" dir="rtl">
      <div className="login-layout grid w-full max-w-6xl overflow-hidden md:min-h-[660px] md:grid-cols-2">
        <section className="login-art flex min-h-[320px] flex-col items-center justify-between gap-8 px-6 py-8 sm:px-10 md:min-h-full md:py-12" aria-label="مرشدي">
          <AstrolabeMark className="hero-astrolabe astrolabe-mark text-[#C9A45C]" />
          <div className="relative z-10 flex items-center gap-3 self-start">
            <span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#C9A45C]/45 bg-[#14201B] text-[#D9884A]">
              <MorshidiLogo className="h-7 w-7" aria-hidden="true" />
            </span>
            <span className="text-xl font-bold text-[#F3E9D8]">مرشدي</span>
          </div>
          <div className="login-portrait z-10">
            <Image src="/brand/morshidi-guide-cutout.png" alt="مرشدي، دليلك الأكاديمي" fill priority sizes="(max-width: 768px) 72vw, 360px" className="object-contain" />
          </div>
          <span className="login-orbit-note relative z-10 self-end" aria-hidden="true">م</span>
        </section>

        <section className="flex flex-col justify-center px-6 py-10 sm:px-10 md:px-14 lg:px-16" aria-labelledby="login-title">
          <div className="mb-8">
            <h1 id="login-title" className="text-3xl font-bold tracking-tight text-[#F3E9D8]">أهلاً بعودتك</h1>
          </div>

          <Suspense fallback={<p className="rounded-xl border border-[#C9A45C]/25 bg-[#101915] px-4 py-3 text-sm text-[#C6B69C]" role="status">لحظة من فضلك…</p>}>
            <LoginForm />
          </Suspense>

          <Link href="/" className="mt-8 inline-flex min-h-11 items-center justify-center self-start rounded-full px-4 text-sm font-semibold text-[#C6B69C] transition-colors hover:text-[#D9884A]">
            العودة للرئيسية
          </Link>
        </section>
      </div>
    </main>
  );
}
