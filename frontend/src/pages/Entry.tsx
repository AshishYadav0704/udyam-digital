import { FileText, Headset, IdCard, MessagesSquare, ReceiptText, ShieldCheck, SquarePen, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button, Money, Skeleton, Stamp } from "../components/ui";
import { api } from "../lib/api";
import { useJourney } from "../lib/store";
import type { Lang } from "../i18n/strings";

type Product = { product_id: string; name: string; unit: string; list_price: number; setup_fee: number; description: string };

const EXAMPLE_IDS = ["P01", "P07", "P19"];

function CatalogueExample() {
  const { j, t } = useJourney();
  const [rows, setRows] = useState<Product[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setFailed(false);
    api<{ products: Product[] }>(`/api/catalogue/products?lang=${j.lang}`)
      .then((d) => live && setRows(d.products.filter((p) => EXAMPLE_IDS.includes(p.product_id))))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [j.lang, attempt]);
  if (failed)
    return (
      <div className="rounded-xl border border-dashed border-line-strong bg-white p-5 text-[15px] text-muted" role="status">
        {t("landing.prices_unavailable")}{" "}
        <button type="button" onClick={() => setAttempt((n) => n + 1)} className="inline-flex min-h-10 items-center font-semibold text-brand-ink underline-offset-4 hover:underline">
          {t("common.retry")}
        </button>
      </div>
    );
  if (!rows)
    return (
      <div className="space-y-4 rounded-xl border border-line bg-white p-5 shadow-[var(--shadow-card)]" role="status" aria-label={t("common.loading")}>
        <Skeleton className="h-4 w-1/2" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex justify-between gap-6">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-5 w-16" />
          </div>
        ))}
      </div>
    );
  if (rows.length === 0) return null;
  return (
    <figure className="bill relative rounded-t-xl border border-b-0 border-line bg-white px-5 pt-5 shadow-[var(--shadow-raised)]" aria-label={t("landing.example")}>
      <Stamp className="absolute top-4 right-4">{t("landing.stamp")}</Stamp>
      <figcaption className="mb-3 pr-28 text-[14px] text-muted">{t("landing.example")}</figcaption>
      <ul className="divide-y divide-dashed divide-line">
        {rows.map((p) => (
          <li key={p.product_id} className="flex items-baseline justify-between gap-4 py-2.5">
            <span className="min-w-0">
              <span className="block font-semibold">{p.name}</span>
              <span className="block text-[14px] text-muted">{p.unit}</span>
            </span>
            <Money value={p.list_price} className="font-semibold" />
          </li>
        ))}
      </ul>
    </figure>
  );
}

export function Landing() {
  const { j, set, t } = useJourney();
  const nav = useNavigate();
  const start = (lang: Lang) => {
    set({ lang });
    nav("/start");
  };
  const steps = ["landing.step1", "landing.step2", "landing.step3", "landing.step4"];
  return (
    <Shell wide>
      <div className="grid gap-8 md:grid-cols-[1.15fr_1fr] md:items-center md:gap-12 md:py-6">
        <div className="space-y-5">
          <h1 className="text-[32px] leading-[1.15] font-extrabold text-ink sm:text-[42px]">{t("landing.title")}</h1>
          <p className="max-w-[56ch] text-[18px] text-ink-3">{t("landing.sub")}</p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button size="lg" onClick={() => start("en")} lang="en" variant={j.lang === "en" ? "primary" : "secondary"}>
              {t("landing.start_en")}
            </Button>
            <Button size="lg" onClick={() => start("hi")} lang="hi" variant={j.lang === "hi" ? "primary" : "secondary"}>
              {t("landing.start_hi")}
            </Button>
          </div>
          <Link to="/help/callback" className="inline-flex min-h-11 items-center gap-2 font-semibold text-brand-ink underline-offset-4 hover:underline">
            <Headset className="size-5" aria-hidden /> {t("landing.human")}
          </Link>
        </div>
        <CatalogueExample />
      </div>

      <section className="mt-10 grid gap-8 md:grid-cols-2">
        <div>
          <h2 className="mb-3 text-[20px] font-bold">{t("landing.how")}</h2>
          <ol className="space-y-3">
            {steps.map((k, i) => (
              <li key={k} className="flex items-start gap-3">
                <span className="num grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft font-bold text-brand-ink">{i + 1}</span>
                <span className="pt-1">{t(k)}</span>
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h2 className="mb-3 text-[20px] font-bold">{t("landing.need")}</h2>
          <NeedList />
        </div>
      </section>

      <section className="mt-10 grid gap-4 border-t border-line pt-6 sm:grid-cols-3">
        {[
          { Icon: ReceiptText, k: "landing.trust1" },
          { Icon: ShieldCheck, k: "landing.trust2" },
          { Icon: Headset, k: "landing.trust3" },
        ].map(({ Icon, k }) => (
          <p key={k} className="flex items-start gap-3 text-[15px] text-ink-3">
            <Icon className="mt-0.5 size-5 shrink-0 text-brand-ink" aria-hidden /> {t(k)}
          </p>
        ))}
      </section>
    </Shell>
  );
}

function NeedList() {
  const { t } = useJourney();
  const items = [
    { Icon: FileText, k: "start.need_gst" },
    { Icon: FileText, k: "start.need_udyam" },
    { Icon: IdCard, k: "start.need_id" },
    { Icon: ReceiptText, k: "start.need_bill" },
  ];
  return (
    <ul className="space-y-2.5">
      {items.map(({ Icon, k }) => (
        <li key={k} className="flex items-start gap-3">
          <Icon className="mt-0.5 size-5 shrink-0 text-ink-3" aria-hidden />
          <span>{t(k)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Deep-link entry for WhatsApp / partner QR codes: /language?src=WhatsApp&partner=PTN-LKO-01 */
export function LanguageSelect() {
  const { set, t } = useJourney();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const choose = (lang: Lang) => {
    const src = params.get("src");
    const partner = params.get("partner");
    set({ lang, ...(src || partner ? { attribution: { source: src || "Website", partner_code: partner } } : {}) });
    nav("/start");
  };
  return (
    <Shell>
      <h1 className="mb-1 text-[26px] font-bold">
        {t("lang.title")} <span lang="hi">/ अपनी भाषा चुनें</span>
      </h1>
      <p className="mb-5 text-muted">{t("lang.sub")}</p>
      <div className="grid gap-3">
        <button onClick={() => choose("hi")} lang="hi" className="flex min-h-20 items-center justify-between rounded-xl border border-control bg-white px-5 text-left shadow-[var(--shadow-card)] transition-colors hover:border-brand hover:bg-brand-soft/40">
          <span>
            <span className="block text-[24px] font-bold">हिंदी</span>
            <span className="text-muted">हिंदी में जारी रखें</span>
          </span>
          <span className="grid size-12 place-items-center rounded-full bg-brand-soft text-[26px] font-bold text-brand-ink" aria-hidden>
            अ
          </span>
        </button>
        <button onClick={() => choose("en")} lang="en" className="flex min-h-20 items-center justify-between rounded-xl border border-control bg-white px-5 text-left shadow-[var(--shadow-card)] transition-colors hover:border-brand hover:bg-brand-soft/40">
          <span>
            <span className="block text-[24px] font-bold">English</span>
            <span className="text-muted">Continue in English</span>
          </span>
          <span className="grid size-12 place-items-center rounded-full bg-brand-soft text-[26px] font-bold text-brand-ink" aria-hidden>
            A
          </span>
        </button>
      </div>
      <p className="mt-5 text-[15px] text-muted">{t("lang.more")}</p>
    </Shell>
  );
}

export function Onboarding() {
  const { j, t, resetAdvisor } = useJourney();
  const nav = useNavigate();
  const options = [
    { Icon: MessagesSquare, title: "start.chat", sub: "start.chat_sub", to: "/advisor", primary: true },
    { Icon: SquarePen, title: "start.form", sub: "start.form_sub", to: "/advisor/form" },
    { Icon: Headset, title: "start.person", sub: "start.person_sub", to: "/help/callback" },
  ];
  return (
    <Shell step="advisor">
      <h1 className="mb-1 text-[26px] font-bold">{t("start.title")}</h1>
      <p className="mb-4 text-muted">{t("start.sub")}</p>
      <div className="mb-6 rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)]">
        <NeedList />
      </div>
      <h2 className="mb-3 text-[20px] font-bold">{t("start.how")}</h2>
      <div className="grid gap-3">
        {options.map(({ Icon, title, sub, to, primary }) => (
          <button
            key={to}
            onClick={() => nav(to)}
            className={
              "flex min-h-18 items-center gap-4 rounded-xl border px-4 py-3 text-left shadow-[var(--shadow-card)] transition-colors " +
              (primary ? "border-brand bg-brand text-white hover:bg-brand-2" : "border-control bg-white hover:border-brand hover:bg-brand-soft/40")
            }
          >
            <Icon className="size-7 shrink-0" aria-hidden />
            <span>
              <span className="block text-[18px] font-bold">{t(title)}</span>
              <span className={primary ? "text-white" : "text-muted"}>{t(sub)}</span>
            </span>
          </button>
        ))}
      </div>
      {j.sessionId && (
        <button onClick={() => { resetAdvisor(); nav("/advisor"); }} className="mt-5 inline-flex min-h-11 items-center gap-2 text-ink-3 underline-offset-4 hover:underline">
          <Undo2 className="size-4" aria-hidden /> {t("advisor.restart")}
        </button>
      )}
    </Shell>
  );
}
