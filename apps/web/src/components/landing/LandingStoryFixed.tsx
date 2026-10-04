"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useAuth } from "@/auth/auth-provider";
import { AstrolabeDial, AstrolabeMark, PathNode } from "@/components/ui/VisualPrimitives";

const scenes = [
  { id: "story-hero", label: "البداية" },
  { id: "journey-path", label: "المسار" },
  { id: "story-gate", label: "الأهلية" },
  { id: "story-dial", label: "البوصلة" },
  { id: "story-board", label: "الفصل" },
  { id: "story-timeline", label: "الرحلة" },
  { id: "story-trust", label: "المرشد" },
  { id: "story-start", label: "انطلق" },
];

export function LandingStoryFixed() {
  const rootRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef(1);
  const [active, setActive] = useState(1);
  const [track, setTrack] = useState(0);
  const auth = useAuth();
  const tracks = [
    { name: "الذكاء الاصطناعي", done: "مقدمة في البرمجة", next: "تراكيب البيانات", locked: "تعلم الآلة", code: "CS-201", reason: "المتطلب السابق غير مكتمل." },
    { name: "قواعد البيانات", done: "أساسيات نظم المعلومات", next: "إدارة قواعد البيانات", locked: "الأنظمة السحابية", code: "CS-220", reason: "تفتح المادة التالية بعد اجتياز المتطلب." },
    { name: "الأمن السيبراني", done: "مبادئ الشبكات", next: "أمن الشبكات", locked: "التحليل الجنائي الرقمي", code: "CS-230", reason: "يعتمد التسلسل على متطلبات الخطة." },
  ];

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      const index = scenes.findIndex((scene) => scene.id === visible.target.id) + 1;
      if (index > 0) { activeRef.current = index; setActive(index); }
    }, { threshold: [0.45, 0.65] });
    root.querySelectorAll<HTMLElement>("[data-story-scene]").forEach((scene) => observer.observe(scene));

    gsap.registerPlugin(ScrollTrigger);
    const media = gsap.matchMedia();
    media.add("(min-width: 900px) and (prefers-reduced-motion: no-preference)", () => {
      const ctx = gsap.context(() => {
        root.querySelectorAll<HTMLElement>("[data-scene-content]").forEach((content) => {
          gsap.fromTo(content, { autoAlpha: 0.7, y: 16 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: "power2.out", scrollTrigger: { trigger: content, start: "top 80%", once: true } });
        });
        const road = root.querySelector<SVGPathElement>(".journey-road-line");
        if (road) gsap.fromTo(road, { strokeDashoffset: 1 }, { strokeDashoffset: 0, ease: "none", scrollTrigger: { trigger: "#journey-path", start: "top 70%", end: "bottom 35%", scrub: 0.7 } });
        const stage = root.querySelector<HTMLElement>("[data-path-stage]");
        if (stage) ScrollTrigger.create({ trigger: "#journey-path", start: "top top", end: "+=55%", pin: stage });
      }, root);
      return () => ctx.revert();
    });

    const onKey = (event: KeyboardEvent) => {
      if (!["ArrowDown", "ArrowUp", "PageDown", "PageUp"].includes(event.key)) return;
      if (event.target instanceof HTMLElement && event.target.closest("a, button, input, textarea, select")) return;
      event.preventDefault();
      const step = event.key === "ArrowDown" || event.key === "PageDown" ? 1 : -1;
      const target = Math.max(0, Math.min(scenes.length - 1, activeRef.current - 1 + step));
      document.getElementById(scenes[target].id)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    };
    window.addEventListener("keydown", onKey);
    return () => { observer.disconnect(); media.revert(); window.removeEventListener("keydown", onKey); };
  }, []);

  const href = auth.isAuthenticated ? "/student" : "/login";
  const cta = auth.isAuthenticated ? "تابع مسارك" : "ابدأ رحلتك";
  const demo = tracks[track];

  return <div ref={rootRef} className="landing-story" dir="rtl">
    <div className="story-progress" aria-hidden="true"><span style={{ width: `${active / scenes.length * 100}%` }} /></div>
    <div className="story-counter" aria-live="polite"><span>{String(active).padStart(2, "0")}</span><i />{String(scenes.length).padStart(2, "0")}</div>
    <section id="story-hero" data-story-scene className="landing-scene landing-hero-scene"><div className="landing-hero-grid" data-scene-content>
      <div className="landing-hero-copy"><h1>قرارك الأكاديمي…<br /><em>بوضوح.</em></h1><div className="landing-actions"><Link href={href} className="button-primary story-cta">{cta}<span aria-hidden="true">←</span></Link><a href="#journey-path" className="story-scroll-cue">اكتشف المسار <span aria-hidden="true">↓</span></a></div></div>
      <div className="landing-hero-art" aria-label="مرشدي، دليلك الأكاديمي"><AstrolabeMark className="story-astrolabe astrolabe-mark" /><div className="story-embers" aria-hidden="true"><i /><i /><i /><i /></div><Image src="/brand/morshidi-guide-cutout.png" alt="" fill priority sizes="(max-width: 768px) 80vw, 540px" className="story-guide" /><span className="story-gate-line" aria-hidden="true" /></div>
    </div></section>
    <section id="journey-path" data-story-scene className="landing-scene landing-path-scene"><div className="story-scene-inner path-stage" data-path-stage data-scene-content><span className="story-kicker">المسار</span><h2>كل خطوة تقرّبك.</h2><div className="journey-map"><svg className="journey-road" viewBox="0 0 1000 260" preserveAspectRatio="none" aria-hidden="true"><path className="journey-road-line" pathLength="1" d="M980 62 C810 220 710 26 520 132 S240 232 24 84" /></svg><div className="journey-stops"><PathNode code="سجّل" state="complete" label="سجّل" /><PathNode code="افهم" state="complete" label="افهم خطتك" /><PathNode code="خطّط" state="current" label="خطّط فصلك" /><PathNode code="تخرّج" state="locked" label="تخرّج" /></div></div><div className="story-side-note"><span className="story-needle" aria-hidden="true" /> من خطتك إلى التخرّج</div></div></section>
    <section id="story-gate" data-story-scene className="landing-scene landing-gate-scene"><div className="story-scene-inner" data-scene-content><div className="story-section-heading"><span className="story-kicker">الأهلية</span><h2>المتطلب يفتح الباب.</h2></div><div className="gate-demo engraved-card"><div className="track-choices" role="group" aria-label="اختر التخصص">{tracks.map((item, index) => <button key={item.name} type="button" aria-pressed={track === index} onClick={() => setTrack(index)}>{item.name}</button>)}</div><div className="gate-courses"><article className="gate-course is-done"><span className="gate-state"><i />منجزة</span><h3>{demo.done}</h3><code dir="ltr">CS-101</code><b dir="ltr">A</b></article><span className="gate-link" aria-hidden="true" /><article className="gate-course is-open"><span className="gate-state"><i />مؤهلة</span><h3>{demo.next}</h3><code dir="ltr">{demo.code}</code><b>3 س</b></article><span className="gate-link is-dim" aria-hidden="true" /><article className="gate-course is-locked"><span className="gate-state"><i />مقيّدة</span><h3>{demo.locked}</h3><code dir="ltr">CS-401</code><b>{demo.reason}</b></article></div></div></div></section>
    <section id="story-dial" data-story-scene className="landing-scene landing-dial-scene"><div className="story-dial-layout" data-scene-content><div className="story-dial-copy"><span className="story-kicker">البوصلة</span><h2>مسارك،<br /><em>على مقياس واضح.</em></h2></div><AstrolabeDial value={12} max={100} label="من الخطة" size={268} /><div className="story-mini-stats"><div><strong>72</strong><span>منجزة</span></div><div><strong>60</strong><span>متبقية</span></div><div><strong>8</strong><span>فصول</span></div></div></div></section>
    <section id="story-board" data-story-scene className="landing-scene landing-board-scene"><div className="story-scene-inner" data-scene-content><div className="story-section-heading"><span className="story-kicker">الفصل</span><h2>ثلاثة إيقاعات، طريق واحد.</h2></div><div className="semester-deck"><article className="semester-card"><span className="semester-mark">١</span><small>أخف</small><strong>12 <i>ساعة</i></strong><span>عبء متوازن</span><div className="semester-ticks"><i /><i /><i /><i /></div></article><article className="semester-card is-featured"><span className="semester-mark">٢</span><small>متوازن</small><strong>15 <i>ساعة</i></strong><span>خطوة ثابتة</span><div className="semester-ticks"><i /><i /><i /><i /><i /></div></article><article className="semester-card"><span className="semester-mark">٣</span><small>مكثّف</small><strong>18 <i>ساعة</i></strong><span>تقدّم أسرع</span><div className="semester-ticks"><i /><i /><i /><i /><i /><i /></div></article></div><span className="story-sample-note">أمثلة توضيحية — خطتك تعتمد على سجلك</span></div></section>
    <section id="story-timeline" data-story-scene className="landing-scene landing-timeline-scene"><div className="story-scene-inner" data-scene-content><span className="story-kicker">الرحلة</span><h2>محطة بعد محطة.</h2><div className="timeline-map" aria-label="مسار دراسي توضيحي من ثمانية فصول"><svg viewBox="0 0 1000 160" preserveAspectRatio="none" aria-hidden="true"><path className="timeline-road" pathLength="1" d="M970 82 C810 16 700 142 555 82 S260 20 30 82" /></svg>{Array.from({ length: 8 }, (_, index) => <div key={index} className={`timeline-station ${index < 2 ? "is-lit" : ""}`}><span>{String(index + 1).padStart(2, "0")}</span><i /></div>)}<div className="timeline-finish" aria-hidden="true"><span>م</span></div></div><span className="story-sample-note">مسار تقريبي — المواد حسب المتطلبات</span></div></section>
    <section id="story-trust" data-story-scene className="landing-scene landing-trust-scene"><div className="story-trust-pattern" aria-hidden="true" /><div className="story-trust-copy" data-scene-content><span className="story-kicker">مرشدي</span><h2>كل قرار مبني<br />على قواعد جامعتك.</h2></div></section>
    <section id="story-start" data-story-scene className="landing-scene landing-final-scene"><div className="landing-final-content" data-scene-content><AstrolabeMark className="final-astrolabe" /><span className="story-kicker">الخطوة الأولى</span><h2>ابدأ رحلتك.</h2><Link href={href} className="button-primary story-cta">{cta}<span aria-hidden="true">←</span></Link></div></section>
  </div>;
}
