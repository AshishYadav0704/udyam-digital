import clsx from "clsx";
import { Check, ChevronRight, Circle, CircleDot, FastForward, Headset, PackageSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { OtpLogin } from "../components/OtpLogin";
import { Shell } from "../components/Shell";
import { Button, Card, EmptyState, Money, Notice, Pill, SkeletonCard } from "../components/ui";
import { api, ApiError, fmtDate } from "../lib/api";
import { useJourney } from "../lib/store";
import type { OrderView } from "../lib/types";
import { PaymentChoice } from "./Checkout";

function LoginGate({ children }: { children: React.ReactNode }) {
  const { j, t } = useJourney();
  if (j.customerToken) return <>{children}</>;
  return (
    <Card>
      <p className="mb-3 font-semibold">{t("track.login")}</p>
      <OtpLogin />
    </Card>
  );
}

function useOrderView(id: string | undefined) {
  const { j, t, logoutCustomer } = useJourney();
  const [o, setO] = useState<OrderView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    if (!id || !j.customerToken) return;
    setErr(null);
    api<OrderView>(`/api/orders/${id}?lang=${j.lang}`, { token: j.customerToken })
      .then(setO)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) logoutCustomer();
        setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : e.message);
      });
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [id, j.customerToken, j.lang]);
  return { o, setO, err, reload: load };
}

// ------------------------------------------------------------------ confirmation (screen 12)
export function ConfirmationPage() {
  const { id } = useParams();
  const { j, t } = useJourney();
  const nav = useNavigate();
  const { o, err } = useOrderView(id);
  return (
    <Shell step="track">
      <LoginGate>
        {err && <Notice tone="error">{err}</Notice>}
        {!o && !err && <SkeletonCard lines={4} label={t("common.loading")} />}
        {o && (
          <div className="space-y-4">
            <div className="flex animate-rise items-center gap-3">
              <span className="grid size-12 shrink-0 place-items-center rounded-full bg-leaf text-white">
                <Check className="size-7" aria-hidden />
              </span>
              <h1 className="text-[26px] font-bold">{t("confirm.title")}</h1>
            </div>
            <Card>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
                <dt className="text-muted">{t("confirm.order_no")}</dt>
                <dd className="num font-bold">{o.order_no}</dd>
                <dt className="text-muted">{t("quote.monthly_total")}</dt>
                <dd>
                  <Money value={o.quote.monthly_total} className="font-semibold" />
                </dd>
                <dt className="text-muted">{t("quote.contract")}</dt>
                <dd>{o.quote.contract_months} {j.lang === "hi" ? "महीने" : "months"}</dd>
                <dt className="text-muted">{t("confirm.kyc_status")}</dt>
                <dd>{o.kyc ? <Pill tone={o.kyc.status === "verified" ? "good" : o.kyc.status === "action_required" ? "warn" : "neutral"}>{t(`decision_label.${o.kyc.status}`)}</Pill> : "-"}</dd>
                <dt className="text-muted">{t("track.activation")}</dt>
                <dd>{fmtDate(o.tracker.expected_activation, j.lang)}</dd>
              </dl>
            </Card>
            <section>
              <h2 className="mb-2 text-[18px] font-bold">{t("confirm.next")}</h2>
              <ol className="space-y-2">
                {["confirm.n1", "confirm.n2", ...(o.quote.lines.some((l) => l.product_id === "P07" || l.product_id === "P08") ? ["confirm.n3"] : [])].map((k, i) => (
                  <li key={k} className="flex gap-3">
                    <span className="num grid size-7 shrink-0 place-items-center rounded-full bg-brand-soft text-[14px] font-bold text-brand-ink">{i + 1}</span>
                    <span className="pt-0.5">{t(k)}</span>
                  </li>
                ))}
              </ol>
            </section>
            <Button block size="lg" onClick={() => nav(`/orders/${o.order_id}`)}>
              {t("confirm.track")}
            </Button>
          </div>
        )}
      </LoginGate>
    </Shell>
  );
}

// ------------------------------------------------------------------ tracker (screen 13)
export function TrackerPage() {
  const { id } = useParams();
  const { j, set, t } = useJourney();
  const nav = useNavigate();
  const { o, setO, err, reload } = useOrderView(id);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "warn" | "error"; text: string } | null>(null);
  const [method, setMethod] = useState<"upi_autopay" | "card" | "netbanking" | "pay_on_install">("upi_autopay");

  const advance = async () => {
    setBusy("advance");
    setMsg(null);
    try {
      setO(await api<OrderView>(`/api/orders/${id}/advance?lang=${j.lang}`, { token: j.customerToken, method: "POST" }));
    } catch (e) {
      setMsg({ tone: "warn", text: `${t("track.cannot_advance")}: ${(e as Error).message}` });
    } finally {
      setBusy(null);
    }
  };
  const help = async () => {
    setBusy("help");
    setMsg(null);
    try {
      await api(`/api/orders/${id}/help`, { token: j.customerToken, body: { reason: "order_help" } });
      setMsg({ tone: "success", text: t("track.help_sent") });
      reload();
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };
  const pay = async () => {
    setBusy("pay");
    setMsg(null);
    try {
      setO(await api<OrderView>(`/api/orders/${id}/payment`, { token: j.customerToken, body: { method } }));
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const tr = o?.tracker;
  const needsKyc = o && (!o.kyc || ["collecting", "action_required"].includes(o.kyc.status));
  return (
    <Shell step="track" wide>
      <LoginGate>
        {err && <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={reload}>{t("common.retry")}</Button>}>{err}</Notice>}
        {!o && !err && <SkeletonCard lines={6} label={t("common.loading")} className="max-w-2xl" />}
        {o && tr && (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start lg:gap-8">
          <div className="space-y-4">
            <div>
              <h1 className="text-[26px] font-bold">{t("track.title")}</h1>
              <p className="text-muted">
                <span className="num font-semibold text-ink">{o.order_no}</span>
                {tr.expected_activation && (
                  <>
                    {", "}
                    {t("track.activation")}: <b className="text-ink">{fmtDate(tr.expected_activation, j.lang)}</b>
                  </>
                )}
              </p>
            </div>

            {tr.blockers.length > 0 && (
              <Card className="border-amber/50 bg-amber-soft/40">
                <h2 className="mb-2 font-bold">{t("track.blockers")}</h2>
                <ul className="space-y-1.5 text-[15px]">
                  {tr.blockers.slice(-3).map((b, i) => (
                    <li key={i}>
                      <b>{b.label}</b>
                      {b.note && <span className="text-ink-3"> - {b.note}</span>}
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex flex-wrap gap-2">
                  {o.payment_status === "failed" && (
                    <div className="w-full space-y-2">
                      <PaymentChoice value={method} onChange={setMethod} />
                      <Button onClick={pay} loading={busy === "pay"}>{t("track.retry_payment")}</Button>
                    </div>
                  )}
                  {needsKyc && o.payment_status !== "failed" && (
                    <Button variant="secondary" onClick={() => { set({ orderId: o.order_id, caseId: o.kyc?.case_id || null }); nav(o.kyc ? "/kyc/upload" : "/kyc/consent"); }}>
                      {t("track.continue_kyc")}
                    </Button>
                  )}
                </div>
              </Card>
            )}
            {!tr.blockers.length && needsKyc && o.payment_status !== "failed" && (
              <Notice tone="warn" action={<Button size="sm" onClick={() => { set({ orderId: o.order_id, caseId: o.kyc?.case_id || null }); nav(o.kyc ? "/kyc/upload" : "/kyc/consent"); }}>{t("track.continue_kyc")}</Button>}>
                {t("consent.order_banner", { no: o.order_no })}
              </Notice>
            )}

            <Card>
              <ol className="relative">
                {tr.steps.map((s, i) => {
                  const last = i === tr.steps.length - 1;
                  return (
                    <li key={s.stage} className="relative flex gap-3 pb-4 last:pb-0">
                      {!last && <span className={clsx("absolute top-7 left-[13px] h-[calc(100%-1.5rem)] w-0.5", s.status === "done" ? "bg-brand" : "bg-line-strong")} aria-hidden />}
                      <span className={clsx("relative z-[1] grid size-7 shrink-0 place-items-center rounded-full", s.status === "done" && "bg-brand text-white", s.status === "current" && "border-2 border-brand bg-white text-brand-ink ring-4 ring-brand-soft", s.status === "upcoming" && "border-2 border-line-strong bg-white text-muted")}>
                        {s.status === "done" ? <Check className="size-4" aria-hidden /> : s.status === "current" ? <CircleDot className="size-4" aria-hidden /> : <Circle className="size-3" aria-hidden />}
                      </span>
                      <div className="min-w-0 pt-0.5">
                        <p className={clsx("font-semibold", s.status === "upcoming" && "text-ink-3", s.status === "current" && "text-brand-ink")}>
                          {s.label}
                          {s.status === "current" && <span className="sr-only"> ({t("track.now")})</span>}
                        </p>
                        <p className="text-[14px] text-muted">
                          {s.at ? `${t("track.done")} ${fmtDate(s.at, j.lang)}` : s.expected ? `${t("track.expected")} ${fmtDate(s.expected, j.lang)}` : ""}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </Card>
          </div>

          <div className="space-y-4">
            <Card>
              <h2 className="mb-2 font-bold">{t("track.installs")}</h2>
              <ul className="divide-y divide-dashed divide-line text-[15px]">
                {tr.installations.map((x) => (
                  <li key={x.product_id} className="flex justify-between gap-3 py-2">
                    <span>
                      {x.qty} × {x.name}
                    </span>
                    <span className="shrink-0 text-muted">{fmtDate(x.expected, j.lang)}</span>
                  </li>
                ))}
              </ul>
            </Card>

            {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
              <Button variant="secondary" onClick={help} loading={busy === "help"}>
                <Headset className="size-4" aria-hidden /> {t("track.help_btn")}
              </Button>
              {o.status !== "active" && (
                <Button variant="quiet" onClick={advance} loading={busy === "advance"}>
                  <FastForward className="size-4" aria-hidden /> {t("track.simulate")}
                </Button>
              )}
            </div>
          </div>
          </div>
        )}
      </LoginGate>
    </Shell>
  );
}

export function OrdersPage() {
  const { j, t } = useJourney();
  const nav = useNavigate();
  const [orders, setOrders] = useState<OrderView[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!j.customerToken) return;
    api<{ orders: OrderView[] }>(`/api/orders?lang=${j.lang}`, { token: j.customerToken })
      .then((r) => setOrders(r.orders))
      .catch((e) => setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j.customerToken, j.lang]);
  return (
    <Shell step="track">
      <h1 className="mb-4 text-[26px] font-bold">{t("track.find")}</h1>
      <LoginGate>
        {err && <Notice tone="error">{err}</Notice>}
        {!orders && !err && <SkeletonCard lines={3} label={t("common.loading")} />}
        {orders && orders.length === 0 && <EmptyState icon={<PackageSearch className="size-5" aria-hidden />} title={t("track.none")} action={<Button onClick={() => nav("/start")}>{t("plan.start_advisor")}</Button>}>{t("track.none_sub")}</EmptyState>}
        {orders && orders.length > 0 && (
          <ul className="space-y-2">
            {orders.map((o) => {
              const current = o.tracker.steps.find((s) => s.status === "current");
              return (
                <li key={o.order_id}>
                  <Link to={`/orders/${o.order_id}`} className="group block rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)] transition-colors hover:border-brand/50">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="num font-bold">{o.order_no}</span>
                      <span className="flex items-center gap-1">
                        <Money value={o.quote.monthly_subtotal} className="text-[15px] text-ink-3" />
                        <ChevronRight className="size-4 text-muted group-hover:text-brand-ink" aria-hidden />
                      </span>
                    </div>
                    <p className="mt-0.5 text-[15px] text-muted">{o.quote.lines.map((l) => l.name).join(", ")}</p>
                    <p className="mt-1.5 text-[15px]">
                      <Pill tone={current ? "brand" : "good"}>{current ? current.label : t("track.done")}</Pill>
                      {o.tracker.expected_activation && <span className="text-muted">, {fmtDate(o.tracker.expected_activation, j.lang)}</span>}
                    </p>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </LoginGate>
    </Shell>
  );
}
