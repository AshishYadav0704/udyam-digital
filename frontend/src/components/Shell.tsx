import clsx from "clsx";
import { Check, Headset, PackageSearch, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useJourney } from "../lib/store";

export function BrandMark({ className }: { className?: string }) {
  // A ledger page with a binding strip: the "bahi-khata" every small business already keeps. Our own mark for the
  // case's fictional operator; it is not, and does not imitate, any real operator's logo.
  return (
    <svg viewBox="0 0 32 32" className={clsx("size-8 shrink-0", className)} aria-hidden>
      <rect x="2" y="2" width="28" height="28" rx="7" fill="#d81921" />
      <rect x="2" y="2" width="7" height="28" rx="3.5" fill="#8f0e14" />
      <path d="M13 11h12M13 16h12M13 21h8" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

const STEPS = ["advisor", "plan", "checkout", "kyc", "track"] as const;
export type StepKey = (typeof STEPS)[number];

export function StepRail({ step }: { step: StepKey }) {
  const { t } = useJourney();
  const idx = STEPS.indexOf(step);
  return (
    <nav aria-label="Progress" className="no-print mb-6">
      <ol className="flex items-start">
        {STEPS.map((s, i) => {
          const done = i < idx;
          const current = i === idx;
          return (
            <li key={s} className="relative flex min-w-0 flex-1 flex-col items-center gap-1.5" aria-current={current ? "step" : undefined}>
              {i > 0 && (
                <span aria-hidden className={clsx("absolute top-[13px] right-1/2 h-0.5 w-full -translate-x-[14px]", i <= idx ? "bg-brand" : "bg-line-strong")} style={{ width: "calc(100% - 28px)" }} />
              )}
              <span
                className={clsx(
                  "relative z-[1] grid size-7 place-items-center rounded-full text-[13px] font-bold transition-colors",
                  done && "bg-brand text-white",
                  current && "border-2 border-brand bg-white text-brand-ink ring-4 ring-brand-soft",
                  !done && !current && "border-2 border-line-strong bg-white text-muted",
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : i + 1}
                <span className="sr-only">{done ? " (done)" : current ? " (current)" : ""}</span>
              </span>
              <span className={clsx("w-full truncate text-center text-[13px]", current ? "font-semibold text-ink" : "text-muted")}>{t(`steps.${s}`)}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function LangToggle() {
  const { j, set, t } = useJourney();
  return (
    <button
      type="button"
      onClick={() => set({ lang: j.lang === "hi" ? "en" : "hi" })}
      className="min-h-10 rounded-lg border border-control bg-white px-3 text-[15px] font-semibold text-ink transition-colors hover:border-ink-3 hover:bg-mist"
      aria-label={j.lang === "hi" ? "Switch to English" : "हिंदी में बदलें"}
    >
      {t("lang.switch")}
    </button>
  );
}

/**
 * Customer page frame. `aside` (desktop only, from 1024 px) holds a sticky summary next to the content; on phones the
 * page shows its own compact version (e.g. the price bar), so nothing important lives only in the aside.
 */
export function Shell({ children, step, wide, aside }: { children: ReactNode; step?: StepKey; wide?: boolean; aside?: ReactNode }) {
  const { t, j } = useJourney();
  const { pathname } = useLocation();
  const width = wide || aside ? "max-w-5xl" : "max-w-2xl";
  const navCls = ({ isActive }: { isActive: boolean }) =>
    clsx("flex min-h-10 min-w-10 items-center justify-center gap-1.5 rounded-lg px-2.5 text-[15px] font-medium transition-colors", isActive ? "bg-brand-soft text-brand-ink" : "text-ink-3 hover:bg-mist hover:text-ink");
  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2">
        {t("common.skip")}
      </a>
      <header className="no-print sticky top-0 z-20 border-b border-line bg-white/95 backdrop-blur">
        <div className={clsx("mx-auto flex items-center gap-1.5 px-4 py-2", width)}>
          <Link to="/" className="mr-auto flex min-h-10 items-center gap-2 font-bold text-ink" aria-label={t("brand")}>
            <BrandMark />
            <span className="hidden text-[18px] sm:inline">{t("brand")}</span>
          </Link>
          <NavLink to="/orders" className={navCls} aria-label={t("nav.track")}>
            <PackageSearch className="size-4" aria-hidden />
            <span className="hidden min-[440px]:inline">{t("nav.track")}</span>
          </NavLink>
          <NavLink to="/help" className={navCls} aria-label={t("nav.help")}>
            <Headset className="size-4" aria-hidden />
            <span className="hidden min-[440px]:inline">{t("nav.help")}</span>
          </NavLink>
          {j.customerToken && (
            <NavLink to="/privacy" className={navCls} aria-label={t("nav.privacy")}>
              <ShieldCheck className="size-4" aria-hidden />
              <span className="hidden md:inline">{t("nav.privacy")}</span>
            </NavLink>
          )}
          <LangToggle />
        </div>
      </header>
      <main id="main" className={clsx("mx-auto w-full flex-1 px-4 pt-5 pb-16", width)}>
        {step && <StepRail step={step} />}
        <div key={pathname} className="animate-page-in">
          {aside ? (
            <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start lg:gap-8">
              <div className="min-w-0">{children}</div>
              <aside className="no-print hidden lg:sticky lg:top-20 lg:block">{aside}</aside>
            </div>
          ) : (
            children
          )}
        </div>
      </main>
      <footer className="no-print border-t border-line bg-white">
        <div className={clsx("mx-auto flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-[14px] text-muted", width)}>
          <span className="py-1.5">{t("landing.demo")}</span>
          <Link to="/ops" className="inline-flex min-h-10 items-center underline underline-offset-2 hover:text-ink">
            {t("nav.ops")}
          </Link>
        </div>
      </footer>
    </div>
  );
}
