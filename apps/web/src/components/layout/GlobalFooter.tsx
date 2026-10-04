import Link from "next/link";
import Image from "next/image";

export function GlobalFooter() {
  return (
    <footer className="border-t border-[#C9A45C]/20 bg-[#0F1A17] text-[#C6B69C]" dir="rtl">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-5 px-4 py-7 sm:flex-row sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2.5 rounded-lg focus-visible:outline-offset-4">
          <Image src="/brand/morshidi-guide.png" alt="مرشدي" width={30} height={30} className="h-8 w-8 rounded-full border border-[#C9A45C]/35 object-cover object-left" />
          <span className="text-sm font-semibold text-[#F3E9D8]">مرشدي</span>
        </Link>
        <p className="max-w-xl text-center text-[11px] leading-5 text-[#B7A78E]">المرجع النهائي للقرارات الأكاديمية هو أنظمة الجامعة المعتمدة.</p>
        <p className="text-[10px] text-[#948B79]">© 2026 مرشدي</p>
      </div>
    </footer>
  );
}
