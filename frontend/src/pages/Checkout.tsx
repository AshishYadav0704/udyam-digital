import clsx from "clsx";
import { CheckCircle2, FlaskConical, LockKeyhole, LogOut } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { OtpLogin } from "../components/OtpLogin";
import { Shell } from "../components/Shell";
import { Button, Card, Checkbox, EmptyState, Field, Input, Money, Notice, OptionRow, SkeletonCard, Textarea } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { selectedLines, useJourney } from "../lib/store";
import type { OrderView, Quote } from "../lib/types";

const METHODS = ["upi_autopay", "card", "netbanking", "pay_on_install"] as const;
type Method = (typeof METHODS)[number];

export function PaymentChoice({ value, onChange }: { value: Method; onChange: (m: Method) => void }) {
  const { t } = useJourney();
  return (
    <fieldset className="space-y-2">
      <legend className="sr-only">{t("checkout.payment")}</legend>
      {METHODS.map((m) => (
        <OptionRow key={m} name="pay" checked={value === m} onChange={() => onChange(m)}>
          {t(`checkout.pay.${m}`)}
        </OptionRow>
      ))}
      <p className="flex items-start gap-2 pt-1 text-[14px] text-muted">
        <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("checkout.simulated")}
      </p>
    </fieldset>
  );
}

export function CheckoutPage() {
  const { j, set, t, logoutCustomer } = useJourney();
  const nav = useNavigate();
  const lines = useMemo(() => selectedLines(j.selection), [j.selection]);
  const [q, setQ] = useState<Quote | null>(null);
  const [qErr, setQErr] = useState<string | null>(null);
  const [form, setForm] = useState({ name: j.customer?.name || "", address: "", pincode: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [method, setMethod] = useState<Method>("upi_autopay");
  const [terms, setTerms] = useState(false);
  const [simulateFail, setSimulateFail] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [order, setOrder] = useState<OrderView | null>(null);

  useEffect(() => {
    if (!j.sessionId || !lines.length) return;
    api<Quote>("/api/quotes/preview", { body: { session_id: j.sessionId, items: lines }, sessionToken: j.sessionToken })
      .then(setQ)
      .catch((e) => setQErr(e instanceof ApiError && e.status === 0 ? t("common.network") : e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j.sessionId, JSON.stringify(lines)]);

  useEffect(() => {
    if (j.customer?.name && !form.name) setForm((f) => ({ ...f, name: j.customer!.name || "" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j.customer]);

  if (!j.sessionId || !lines.length)
    return (
      <Shell step="checkout">
        <EmptyState title={t("plan.no_plan")} action={<Button onClick={() => nav("/start")}>{t("plan.start_advisor")}</Button>} />
      </Shell>
    );

  const paymentFailed = order && order.payment_status === "failed";
  const dueNow = q ? (method === "pay_on_install" ? 0 : q.setup_total) : null;

  const place = async (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (form.name.trim().length < 2) errs.name = t("common.required");
    if (form.address.trim().length < 8) errs.address = j.lang === "hi" ? "पूरा पता लिखें (कम से कम 8 अक्षर)" : "Enter the full address (at least 8 characters)";
    if (!/^[1-9]\d{5}$/.test(form.pincode)) errs.pincode = j.lang === "hi" ? "6 अंकों का पिन कोड" : "6-digit PIN code";
    if (!terms) errs.terms = t("common.required");
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setErr(null);
    try {
      const o = await api<OrderView>("/api/checkout", {
        token: j.customerToken,
        sessionToken: j.sessionToken,
        body: {
          session_id: j.sessionId,
          items: lines,
          package: j.selection?.pkg || "recommended",
          contact_name: form.name.trim(),
          install_address: form.address.trim(),
          pincode: form.pincode,
          accept_terms: terms,
          payment_method: method,
          simulate_payment_failure: simulateFail,
        },
      });
      setOrder(o);
      set({ orderId: o.order_id, caseId: null });
      if (o.payment_status !== "failed") nav("/kyc/consent");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        logoutCustomer();
        setErr(t("common.login_needed"));
      } else setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    if (!order) return;
    setBusy(true);
    setErr(null);
    try {
      const o = await api<OrderView>(`/api/orders/${order.order_id}/payment`, { token: j.customerToken, body: { method, simulate_failure: false } });
      setOrder(o);
      if (o.payment_status !== "failed") nav("/kyc/consent");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const summary = q ? (
    <Card>
      <p className="font-semibold text-ink-3">{t("checkout.summary")}</p>
      <div className="mt-1 flex items-baseline justify-between gap-3">
        <span>{t("quote.monthly_total")}</span>
        <Money value={q.monthly_total} className="text-[22px] font-extrabold" />
      </div>
      <ul className="mt-2 space-y-0.5 text-[15px] text-muted">
        {q.lines.map((l) => (
          <li key={l.product_id}>
            {l.qty} × {l.name}
          </li>
        ))}
      </ul>
      <dl className="mt-3 space-y-1 border-t border-line pt-3 text-[15px]">
        <div className="flex justify-between gap-3">
          <dt>{t("checkout.due_now")}</dt>
          <dd>
            <Money value={dueNow} className="font-bold" />
          </dd>
        </div>
        <div className="flex justify-between gap-3 text-muted">
          <dt>{t("quote.contract")}</dt>
          <dd>
            {q.contract_months} {j.lang === "hi" ? "महीने" : "months"}
          </dd>
        </div>
      </dl>
    </Card>
  ) : qErr ? (
    <Notice tone="error">{qErr}</Notice>
  ) : (
    <SkeletonCard lines={3} label={t("common.loading")} />
  );

  return (
    <Shell step="checkout" aside={summary}>
      <h1 className="mb-4 text-[26px] leading-tight font-bold">{t("checkout.title")}</h1>
      <div className="mb-4 lg:hidden">{summary}</div>

      <Card className="mb-4">
        <h2 className="mb-3 text-[18px] font-bold">{t("checkout.login")}</h2>
        {j.customerToken ? (
          <div className="flex items-center justify-between gap-2">
            <p className="flex items-center gap-2 text-leaf">
              <CheckCircle2 className="size-5" aria-hidden /> {t("checkout.logged_in_as", { mobile: j.customer?.mobile || "" })}
            </p>
            {!order && (
              <button onClick={logoutCustomer} className="inline-flex min-h-10 items-center gap-1 text-[15px] font-semibold text-brand-ink underline-offset-4 hover:underline">
                <LogOut className="size-4" aria-hidden /> {t("checkout.change_number")}
              </button>
            )}
          </div>
        ) : (
          <OtpLogin askName />
        )}
      </Card>
      {!j.customerToken && (
        <p className="mb-3 flex items-center gap-2 text-[15px] text-muted">
          <LockKeyhole className="size-4 shrink-0" aria-hidden /> {t("checkout.verify_first")}
        </p>
      )}

      {paymentFailed ? (
        <Card>
          <Notice tone="error" title={t("checkout.order_saved", { no: order!.order_no })} className="mb-4">
            {t("checkout.failed")}
          </Notice>
          <PaymentChoice value={method} onChange={setMethod} />
          {err && (
            <Notice tone="error" className="mt-3">
              {err}
            </Notice>
          )}
          <Button className="mt-4" block size="lg" onClick={retry} loading={busy}>
            {t("checkout.retry")}
          </Button>
        </Card>
      ) : (
        <form onSubmit={place} noValidate className={clsx("space-y-4", !j.customerToken && "pointer-events-none opacity-50")} aria-disabled={!j.customerToken}>
          <Card>
            <h2 className="mb-3 text-[18px] font-bold">{t("checkout.details")}</h2>
            <div className="space-y-3">
              <Field label={t("checkout.name")} htmlFor="n" error={errors.name}>
                <Input id="n" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" maxLength={120} aria-invalid={!!errors.name} />
              </Field>
              <Field label={t("checkout.address")} htmlFor="a" error={errors.address}>
                <Textarea id="a" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} autoComplete="street-address" maxLength={300} aria-invalid={!!errors.address} />
              </Field>
              <Field label={t("checkout.pincode")} htmlFor="pin" error={errors.pincode}>
                <Input id="pin" inputMode="numeric" value={form.pincode} onChange={(e) => setForm({ ...form, pincode: e.target.value.replace(/\D/g, "").slice(0, 6) })} autoComplete="postal-code" aria-invalid={!!errors.pincode} className="max-w-40" />
              </Field>
            </div>
          </Card>
          <Card>
            <h2 className="mb-3 text-[18px] font-bold">{t("checkout.payment")}</h2>
            <PaymentChoice value={method} onChange={setMethod} />
            {q && (
              <dl className="mt-4 space-y-1 text-[15px]">
                <div className="flex justify-between">
                  <dt>{t("checkout.due_now")}</dt>
                  <dd>
                    <Money value={dueNow} className="font-bold" />
                  </dd>
                </div>
                <div className="flex justify-between text-muted">
                  <dt>{t("checkout.monthly_autopay")}</dt>
                  <dd>
                    <Money value={q.monthly_total} />
                  </dd>
                </div>
              </dl>
            )}
          </Card>
          <div className="space-y-3">
            <Checkbox checked={terms} onChange={setTerms}>
              {t("checkout.terms")}
              {q && <span className="text-muted"> ({q.contract_months} {j.lang === "hi" ? "महीने" : "months"})</span>}
            </Checkbox>
            {errors.terms && <p className="text-[15px] font-medium text-rust" role="alert">{errors.terms}</p>}
            <div className="rounded-lg border border-dashed border-amber/60 bg-amber-soft/60 px-3 py-1">
              <Checkbox checked={simulateFail} onChange={setSimulateFail}>
                <span className="text-[15px]">{t("checkout.simulate")}</span>
              </Checkbox>
            </div>
          </div>
          {err && <Notice tone="error">{err}</Notice>}
          <Button type="submit" block size="lg" loading={busy} disabled={!j.customerToken || !q}>
            {busy ? t("checkout.placing") : t("checkout.place")}
          </Button>
        </form>
      )}
    </Shell>
  );
}
