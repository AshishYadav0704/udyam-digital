import clsx from "clsx";
import { ChevronDown, Loader2, Printer, Save, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button, Card, EmptyState, Money, Notice, Pill, QtyStepper, Skeleton, Stamp, Toggle } from "../components/ui";
import { api, ApiError, fmtDate } from "../lib/api";
import { selectedLines, selectionFromRecommendation, useJourney, type Selection } from "../lib/store";
import type { PlanItem, Profile, Quote, Recommendation } from "../lib/types";
import { unitText } from "../lib/units";

export function profileLine(p: Profile | undefined, lang: string) {
  if (!p) return "";
  const hi = lang === "hi";
  return [
    p.business_type,
    p.city,
    p.employees ? `${p.employees} ${hi ? "लोग" : p.employees === 1 ? "person" : "people"}` : null,
    p.sites ? `${p.sites} ${hi ? "साइट" : p.sites === 1 ? "site" : "sites"}` : null,
    p.has_gstin ? (p.gstin_status && p.gstin_status !== "Active" ? `GSTIN ${p.gstin_status}` : "GSTIN ✓") : hi ? "GSTIN नहीं" : "No GSTIN",
  ]
    .filter(Boolean)
    .join(", ");
}

function NoPlan() {
  const { t } = useJourney();
  const nav = useNavigate();
  return (
    <Shell step="plan">
      <EmptyState title={t("plan.no_plan")} action={<Button onClick={() => nav("/start")}>{t("plan.start_advisor")}</Button>}>{t("plan.no_plan_sub")}</EmptyState>
    </Shell>
  );
}

/** Live server-side pricing of the current selection (debounced). The client never computes prices. */
export function useLivePreview(sel: Selection | null) {
  const { j } = useJourney();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [netError, setNetError] = useState<string | null>(null);
  const key = JSON.stringify(selectedLines(sel));
  const seq = useRef(0);
  useEffect(() => {
    if (!j.sessionId) return;
    const lines = selectedLines(sel);
    if (!lines.length) {
      setQuote(null);
      setProblems([]);
      return;
    }
    const my = ++seq.current;
    setLoading(true);
    const h = setTimeout(() => {
      api<Quote>("/api/quotes/preview", { body: { session_id: j.sessionId, items: lines }, sessionToken: j.sessionToken })
        .then((q) => {
          if (my !== seq.current) return;
          setQuote(q);
          setProblems([]);
          setNetError(null);
        })
        .catch((e) => {
          if (my !== seq.current) return;
          if (e instanceof ApiError && e.status === 422 && e.detail?.messages) {
            setProblems(e.detail.messages);
            setQuote(null);
          } else setNetError(e instanceof ApiError && e.status === 0 ? "network" : e.message);
        })
        .finally(() => my === seq.current && setLoading(false));
    }, 300);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, j.sessionId]);
  return { quote, problems, loading, netError };
}

function ItemRow({ it, dimmed }: { it: PlanItem; dimmed?: boolean }) {
  const { t } = useJourney();
  const [open, setOpen] = useState(false);
  const pct = it.share_of_similar ? Math.round(it.share_of_similar * 100) : 0;
  return (
    <li className={clsx("py-3", dimmed && "opacity-55")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{it.name}</p>
          <p className="text-[15px] text-muted">
            {it.qty} {it.unit_label}
            {dimmed && <span className="ml-2 font-semibold text-amber">{t("plan.dropped")}</span>}
          </p>
        </div>
        <Money value={it.monthly} className="shrink-0 font-semibold" />
      </div>
      <p className="mt-1 text-[15px] text-ink-3">{it.reason_text}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        {pct > 0 && !it.reason_text.includes("%") && <Pill>{t("plan.share_similar", { pct })}</Pill>}
        <button onClick={() => setOpen(!open)} aria-expanded={open} className="inline-flex min-h-9 items-center gap-1 text-[14px] font-semibold text-brand-ink underline-offset-4 hover:underline">
          {t("plan.why")} <ChevronDown className={clsx("size-4 transition-transform", open && "rotate-180")} aria-hidden />
        </button>
      </div>
      {open && <p className="mt-2 rounded-lg bg-mist px-3 py-2 text-[15px]">{it.description}</p>}
    </li>
  );
}

function PriceFigures({ monthly, setup, loading, big, testId }: { monthly: number | null | undefined; setup?: number | null; loading?: boolean; big?: boolean; testId?: string }) {
  const { t } = useJourney();
  return (
    <div aria-live="polite" aria-busy={loading || undefined}>
      <p className="leading-tight">
        <Money value={monthly} testId={testId} className={clsx(big ? "text-[30px]" : "text-[24px]", "font-extrabold transition-opacity", loading && "opacity-40")} />
        <span className="text-[15px] text-muted"> {t("plan.permonth")}</span>
      </p>
      {setup !== undefined && (
        <p className="text-[14px] text-muted">
          {t("plan.setup")}: <Money value={setup} paise={false} />
        </p>
      )}
      {loading && (
        <p className="mt-0.5 flex items-center gap-1.5 text-[13px] text-muted">
          <Loader2 className="size-3.5 animate-spin" aria-hidden /> {t("plan.updating")}
        </p>
      )}
    </div>
  );
}

/** Phones: a price bar pinned to the bottom of the screen. From 1024 px the same figures sit in the side summary. */
function PriceBar({ monthly, setup, loading, children }: { monthly: number | null | undefined; setup?: number | null; loading?: boolean; children: React.ReactNode }) {
  return (
    <div className="no-print sticky bottom-0 z-10 -mx-4 mt-6 border-t border-line bg-white/95 px-4 py-3 shadow-[0_-6px_16px_-12px_rgb(16_24_40/0.25)] backdrop-blur lg:hidden">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PriceFigures monthly={monthly} setup={setup} loading={loading} testId="price-monthly" />
        <div className="flex gap-2">{children}</div>
      </div>
    </div>
  );
}

function SideSummary({ title, monthly, setup, loading, note, children }: { title: string; monthly: number | null | undefined; setup?: number | null; loading?: boolean; note?: string; children: React.ReactNode }) {
  return (
    <Card className="space-y-4">
      <p className="font-semibold text-ink-3">{title}</p>
      <PriceFigures monthly={monthly} setup={setup} loading={loading} big testId="price-monthly-side" />
      {note && <p className="text-[14px] text-muted">{note}</p>}
      <div className="grid gap-2">{children}</div>
    </Card>
  );
}

export function PlanPage() {
  const { j, set, t } = useJourney();
  const nav = useNavigate();
  const rec = j.recommendation;
  if (!rec || rec.status !== "ok" || !rec.quote) return <NoPlan />;
  const pkg = j.selection?.pkg || "recommended";
  const starterIds = rec.starter_ids || [];
  const starterDiffers = starterIds.length > 0 && starterIds.length < (rec.items || []).length;
  const choose = (p: Selection["pkg"]) => set({ selection: selectionFromRecommendation(rec, p) });
  const monthly = pkg === "starter" ? rec.starter_quote?.monthly_subtotal : pkg === "recommended" ? rec.quote.monthly_subtotal : null;
  const setup = pkg === "starter" ? rec.starter_quote?.setup_subtotal : pkg === "recommended" ? rec.quote.setup_subtotal : undefined;
  const notes = (rec.notes || []).filter((n) => !n.code.startsWith("INTERNAL"));

  const actions = (
    <>
      <Button onClick={() => nav("/quote")}>{t("plan.review")}</Button>
      <Button variant="secondary" onClick={() => nav("/plan/add-ons")}>
        {t("plan.choose_addons")}
      </Button>
    </>
  );
  return (
    <Shell step="plan" aside={<SideSummary title={t("plan.your_plan")} monthly={monthly ?? undefined} setup={setup} note={t("plan.gst_note")}>{actions}</SideSummary>}>
      <h1 className="text-[26px] leading-tight font-bold">{t("plan.title")}</h1>
      <p className="mt-1 text-muted">
        {t("plan.for")}: {profileLine(rec.profile, j.lang)}{" "}
        <Link to="/advisor/form" className="inline-flex min-h-9 items-center font-semibold text-brand-ink underline-offset-4 hover:underline">
          {t("common.edit")}
        </Link>
      </p>

      {rec.explanation && (
        <div className="mt-4 rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)]">
          <p className="leading-relaxed">{rec.explanation}</p>
          <p className="mt-2 flex items-center gap-1.5 text-[14px] text-muted">
            {rec.explanation_source === "llm" && <Sparkles className="size-3.5" aria-hidden />}
            {rec.explanation_source === "llm" ? t("plan.ai_note") : t("plan.template_note")}
          </p>
        </div>
      )}

      {starterDiffers && (
        <div className="mt-4 grid grid-cols-2 gap-2" role="radiogroup" aria-label={t("plan.your_plan")}>
          {(
            [
              ["recommended", t("plan.option_rec"), rec.quote.monthly_subtotal],
              ["starter", t("plan.option_starter"), rec.starter_quote?.monthly_subtotal],
            ] as const
          ).map(([k, label, price]) => (
            <button
              key={k}
              role="radio"
              aria-checked={pkg === k}
              onClick={() => choose(k)}
              className={clsx("rounded-xl border bg-white px-3.5 py-3 text-left transition-colors", pkg === k ? "border-brand bg-brand-soft/50 ring-1 ring-brand" : "border-control hover:border-ink-3")}
            >
              <span className={clsx("block text-[15px] font-semibold", pkg === k ? "text-brand-ink" : "text-ink-3")}>{label}</span>
              <Money value={price} className="text-[22px] font-extrabold" />
              <span className="text-[14px] text-muted"> {t("plan.permonth")}</span>
            </button>
          ))}
        </div>
      )}

      <Card className="mt-4">
        <ul className="divide-y divide-dashed divide-line">
          {(rec.items || []).map((it) => (
            <ItemRow key={it.product_id} it={it} dimmed={pkg === "starter" && !starterIds.includes(it.product_id)} />
          ))}
        </ul>
        {pkg === "custom" && <p className="mt-2 text-[15px] text-muted">{t("quote.edit")}</p>}
      </Card>

      {notes.length > 0 && (
        <section className="mt-5">
          <h2 className="mb-2 text-[18px] font-bold">{t("plan.notes")}</h2>
          <ul className="space-y-2">
            {notes.map((n) => (
              <li key={n.code}>
                <Notice tone={n.code === "GST_BLOCKED" || n.code === "BUDGET_OVER" ? "warn" : "info"}>{n.text}</Notice>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(rec.excluded || []).length > 0 && (
        <section className="mt-5">
          <h2 className="mb-2 text-[18px] font-bold">{t("plan.excluded")}</h2>
          <ul className="space-y-1.5 text-[15px]">
            {rec.excluded!.slice(0, 6).map((e) => (
              <li key={e.product_id} className="rounded-lg border border-line bg-white px-3.5 py-2.5">
                <span className="font-semibold">{e.name}</span>
                <span className="text-ink-3"> - {e.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <PriceBar monthly={monthly ?? undefined} setup={setup}>
        <Button variant="secondary" onClick={() => nav("/plan/add-ons")}>
          {t("plan.choose_addons")}
        </Button>
        <Button onClick={() => nav("/quote")}>{t("plan.review")}</Button>
      </PriceBar>
    </Shell>
  );
}

export function AddOnsPage() {
  const { j, set, t } = useJourney();
  const nav = useNavigate();
  const rec = j.recommendation;
  const sel = j.selection;
  const { quote, problems, loading, netError } = useLivePreview(sel);
  if (!rec || rec.status !== "ok" || !sel) return <NoPlan />;

  const setQty = (pid: string, qty: number) => set({ selection: { pkg: "custom", items: { ...sel.items, [pid]: qty } } });
  const row = (it: PlanItem, isAddon: boolean) => {
    const qty = sel.items[it.product_id] ?? 0;
    const on = qty > 0;
    return (
      <li key={it.product_id} className="py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-semibold">{it.name}</p>
            <p className="text-[15px] text-muted">
              <Money value={it.unit_price} /> {unitText(it.unit, j.lang)}
              {it.setup > 0 && (
                <span className="block">
                  {t("plan.setup")} <Money value={it.setup / Math.max(1, it.qty)} paise={false} /> {unitText(it.unit, j.lang)}
                </span>
              )}
            </p>
          </div>
          <Toggle checked={on} onChange={(v) => setQty(it.product_id, v ? Math.max(1, it.qty) : 0)} label={it.name} />
        </div>
        <p className="mt-1 text-[15px] text-ink-3">{isAddon ? it.reason_text : it.description}</p>
        {on && (
          <div className="mt-2 flex items-center gap-3">
            <span className="text-[15px] text-muted">{t("plan.qty")}</span>
            <QtyStepper value={qty} min={1} max={it.unit.includes("site") ? Math.max(1, rec.profile.sites || 1) : 200} onChange={(v) => setQty(it.product_id, v)} label={`${t("plan.qty")} ${it.name}`} />
          </div>
        )}
      </li>
    );
  };
  const allLines = selectedLines(sel);
  const canReview = !!quote && problems.length === 0 && !loading;
  const sideMonthly = quote?.monthly_subtotal ?? (allLines.length ? undefined : 0);
  return (
    <Shell
      step="plan"
      aside={
        <SideSummary title={t("plan.your_plan")} monthly={sideMonthly} setup={quote?.setup_subtotal} loading={loading} note={t("plan.server_priced")}>
          <Button onClick={() => nav("/quote")} disabled={!canReview}>
            {t("plan.review")}
          </Button>
          <Button variant="secondary" onClick={() => nav("/plan")}>
            {t("common.back")}
          </Button>
        </SideSummary>
      }
    >
      <h1 className="text-[26px] leading-tight font-bold">{t("plan.addons")}</h1>
      <p className="mt-1 mb-4 text-muted">{profileLine(rec.profile, j.lang)}</p>
      <Card>
        <h2 className="mb-1 font-bold">{t("plan.your_plan")}</h2>
        <ul className="divide-y divide-dashed divide-line">{(rec.items || []).map((it) => row(it, false))}</ul>
      </Card>
      {(rec.add_ons || []).length > 0 && (
        <Card className="mt-4">
          <h2 className="mb-1 font-bold">{t("plan.addons")}</h2>
          <ul className="divide-y divide-dashed divide-line">{rec.add_ons!.map((it) => row(it, true))}</ul>
        </Card>
      )}
      {problems.length > 0 && (
        <Notice tone="warn" title={t("plan.invalid")} className="mt-4">
          <ul className="list-disc pl-5">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Notice>
      )}
      {netError && (
        <Notice tone="error" className="mt-4">
          {netError === "network" ? t("common.network") : netError}
        </Notice>
      )}
      {allLines.length === 0 && (
        <Notice tone="warn" className="mt-4">
          {t("plan.empty_selection")}
        </Notice>
      )}
      <PriceBar monthly={sideMonthly} setup={quote?.setup_subtotal} loading={loading}>
        <Button variant="quiet" onClick={() => nav("/plan")}>
          {t("common.back")}
        </Button>
        <Button onClick={() => nav("/quote")} disabled={!canReview}>
          {t("plan.review")}
        </Button>
      </PriceBar>
    </Shell>
  );
}

// ------------------------------------------------------------------ the bill
export function Bill({ q, title, stampDate }: { q: Quote; title: string; stampDate?: string }) {
  const { t, j } = useJourney();
  const maxDay = Math.max(1, ...q.lines.map((l) => l.install_done_day));
  const driver = q.lines.find((l) => l.product_id === q.contract_driver)?.name || q.contract_driver;
  return (
    <article className="bill relative rounded-t-xl border border-b-0 border-line bg-white px-4 pt-5 shadow-[var(--shadow-raised)] sm:px-6" aria-label={t("quote.title")}>
      <Stamp className="absolute top-4 right-3 sm:right-5">
        <span className="block text-[11px] font-semibold">{t("quote.valid")}</span>
        <span className="num block text-[15px] font-extrabold">{fmtDate(stampDate || q.valid_until, j.lang)}</span>
      </Stamp>
      <header className="pr-28">
        <p className="flex items-center gap-2 text-[15px] font-semibold text-ink-3">{t("brand")}</p>
        <h2 className="mt-0.5 text-[20px] leading-tight font-bold">{title}</h2>
      </header>
      <div className="rule-dashed my-4" />
      <table className="w-full text-left">
        <caption className="sr-only">{t("quote.title")}</caption>
        <thead>
          <tr className="text-[14px] text-muted">
            <th scope="col" className="pb-1 font-medium">
              {t("quote.item")}
            </th>
            <th scope="col" className="pb-1 text-right font-medium">
              {t("quote.amount")}
            </th>
          </tr>
        </thead>
        <tbody>
          {q.lines.map((l) => (
            <tr key={l.product_id} className="align-top">
              <td className="py-1.5 pr-3">
                <span className="block font-semibold">{l.name}</span>
                <span className="num block text-[14px] text-muted">
                  {t("quote.per_unit", { qty: l.qty, price: "₹" + new Intl.NumberFormat("en-IN").format(l.unit_price) })} {unitText(l.unit, j.lang)}
                </span>
              </td>
              <td className="py-1.5 text-right">
                <Money value={l.monthly} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="rule-dashed my-3" />
      <dl className="space-y-1">
        <div className="flex justify-between">
          <dt>{t("quote.monthly_sub")}</dt>
          <dd>
            <Money value={q.monthly_subtotal} />
          </dd>
        </div>
        <div className="flex justify-between text-ink-3">
          <dt>{t("quote.gst")}</dt>
          <dd>
            <Money value={q.monthly_gst} />
          </dd>
        </div>
        <div className="flex items-baseline justify-between border-t-2 border-ink pt-2">
          <dt className="font-bold">{t("quote.monthly_total")}</dt>
          <dd>
            <Money value={q.monthly_total} className="text-[26px] font-extrabold" />
          </dd>
        </div>
      </dl>
      <div className="rule-dashed my-3" />
      <dl className="space-y-2 text-[15px]">
        <div className="flex justify-between gap-3">
          <dt>{t("quote.setup")}</dt>
          <dd className="text-right">
            {q.setup_subtotal > 0 ? (
              <>
                <Money value={q.setup_subtotal} paise={false} /> <span className="text-muted">(+<Money value={q.setup_gst} />)</span>
              </>
            ) : (
              t("quote.no_setup")
            )}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>{t("quote.contract")}</dt>
          <dd className="max-w-[65%] text-right">{t("quote.contract_note", { months: q.contract_months, product: driver })}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>{t("quote.total_contract", { months: q.contract_months })}</dt>
          <dd>
            <Money value={q.total_contract_value} />
          </dd>
        </div>
      </dl>
      <div className="rule-dashed my-3" />
      <section aria-label={t("quote.install")}>
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h3 className="font-bold">{t("quote.install")}</h3>
          <span className="text-[14px] text-muted">{t("quote.ready", { days: q.expected_activation_days })}</span>
        </div>
        <ul className="space-y-1.5">
          {q.lines.map((l) => (
            <li key={l.product_id} className="grid grid-cols-[minmax(0,8.5rem)_1fr_auto] items-center gap-2 text-[14px]">
              <span className="truncate">{l.name}</span>
              <span className="relative h-4 rounded bg-mist" aria-hidden>
                <span
                  className="absolute inset-y-0 rounded bg-ink-3/80"
                  style={{ left: `${(l.install_start_day / maxDay) * 100}%`, width: `${Math.max(4, ((l.install_done_day - l.install_start_day) / maxDay) * 100)}%` }}
                />
              </span>
              <span className="num text-[13px] text-muted">{t("quote.day", { from: l.install_start_day, to: l.install_done_day })}</span>
            </li>
          ))}
        </ul>
      </section>
      <p className="mt-4 pb-2 text-[14px] text-muted">
        {t("quote.price_note")} {t("quote.policy")}
      </p>
    </article>
  );
}

export function QuotePage() {
  const { j, set, t } = useJourney();
  const nav = useNavigate();
  const rec = j.recommendation as Recommendation | null;
  const sel = j.selection;
  const lines = useMemo(() => selectedLines(sel), [sel]);
  const [q, setQ] = useState<Quote | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  const load = () => {
    if (!j.sessionId || !lines.length) return;
    setErr(null);
    api<Quote>("/api/quotes/preview", { body: { session_id: j.sessionId, items: lines }, sessionToken: j.sessionToken })
      .then(setQ)
      .catch((e) => setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : e.message));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [j.sessionId, JSON.stringify(lines)]);

  if (!rec || !sel || !lines.length) return <NoPlan />;

  const save = async () => {
    setSaving(true);
    try {
      const r = await api<{ quote_id: string; valid_until: string }>("/api/quotes", { body: { session_id: j.sessionId, items: lines }, sessionToken: j.sessionToken });
      set({ savedQuoteId: r.quote_id });
      setSaved(r.valid_until);
    } catch (e: any) {
      setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Shell step="plan">
      <div className="no-print mb-3 flex items-center justify-between">
        <h1 className="text-[26px] font-bold">{t("quote.title")}</h1>
        <Link to="/plan/add-ons" className="inline-flex min-h-10 items-center font-semibold text-brand-ink underline-offset-4 hover:underline">
          {t("quote.edit")}
        </Link>
      </div>
      {err && (
        <Notice tone="error" className="mb-3" action={<Button size="sm" variant="secondary" onClick={load}>{t("common.retry")}</Button>}>
          {err}
        </Notice>
      )}
      {!q && !err && (
        <div className="space-y-4 rounded-xl border border-line bg-white p-5" role="status" aria-label={t("quote.pricing")}>
          <Skeleton className="h-6 w-1/2" />
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex justify-between gap-6">
              <Skeleton className="h-4 w-3/5" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
          <Skeleton className="h-8 w-full" />
        </div>
      )}
      {q && <Bill q={q} title={`${rec.profile.business_type || ""}${rec.profile.city ? ", " + rec.profile.city : ""}`} />}
      {saved && (
        <Notice tone="success" className="mt-4">
          {t("quote.saved", { date: fmtDate(saved, j.lang) })}
        </Notice>
      )}
      {q && (
        <div className="no-print mt-5 grid gap-2 sm:grid-cols-[1fr_1fr_1.4fr]">
          <Button variant="secondary" onClick={save} loading={saving} disabled={!!saved}>
            <Save className="size-4" aria-hidden /> {t("quote.save")}
          </Button>
          <Button variant="secondary" onClick={() => window.print()}>
            <Printer className="size-4" aria-hidden /> {t("quote.print")}
          </Button>
          <Button onClick={() => nav("/checkout")}>{t("quote.checkout")}</Button>
        </div>
      )}
    </Shell>
  );
}
