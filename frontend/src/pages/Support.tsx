import clsx from "clsx";
import { CheckCircle2, ChevronDown, Headset, LogOut, PackageSearch } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { OtpLogin } from "../components/OtpLogin";
import { Shell } from "../components/Shell";
import { Button, Card, Field, Input, Notice, OptionRow, Pill, SkeletonCard, Textarea } from "../components/ui";
import { api, ApiError, fmtDate } from "../lib/api";
import { createSession } from "../lib/session";
import { useJourney } from "../lib/store";
import type { ConsentNotice } from "../lib/types";

// ------------------------------------------------------------------ support (screen 14)
export function HelpPage() {
  const { t } = useJourney();
  const [open, setOpen] = useState<number | null>(0);
  const faqs = [1, 2, 3];
  return (
    <Shell>
      <h1 className="mb-4 text-[26px] font-bold">{t("help.title")}</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        <Link to="/help/callback" className="flex min-h-20 items-center gap-3 rounded-xl border border-brand bg-brand p-4 text-white shadow-[var(--shadow-card)] transition-colors hover:bg-brand-2">
          <Headset className="size-7 shrink-0" aria-hidden />
          <span>
            <span className="block text-[18px] font-bold">{t("help.callback")}</span>
            <span className="text-white">{t("start.person_sub")}</span>
          </span>
        </Link>
        <Link to="/orders" className="flex min-h-20 items-center gap-3 rounded-xl border border-control bg-white p-4 shadow-[var(--shadow-card)] transition-colors hover:border-brand hover:bg-brand-soft/40">
          <PackageSearch className="size-7 shrink-0" aria-hidden />
          <span>
            <span className="block text-[18px] font-bold">{t("nav.track")}</span>
            <span className="text-muted">{t("help.orders")}</span>
          </span>
        </Link>
      </div>
      <section className="mt-6">
        <h2 className="mb-2 text-[18px] font-bold">{t("help.faq_title")}</h2>
        <ul className="divide-y divide-line rounded-xl border border-line bg-white shadow-[var(--shadow-card)]">
          {faqs.map((n, i) => (
            <li key={n}>
              <button onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i} className="flex min-h-14 w-full items-center justify-between gap-3 px-4 text-left font-semibold">
                {t(`help.faq${n}q`)}
                <ChevronDown className={clsx("size-5 shrink-0 transition-transform", open === i && "rotate-180")} aria-hidden />
              </button>
              {open === i && <p className="px-4 pb-4 text-ink-3">{t(`help.faq${n}a`)}</p>}
            </li>
          ))}
        </ul>
      </section>
    </Shell>
  );
}

// ------------------------------------------------------------------ human escalation (screen 15)
export function CallbackPage() {
  const { j, set, t } = useJourney();
  const [mobile, setMobile] = useState("");
  const [when, setWhen] = useState<"morning" | "afternoon" | "evening">("morning");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [mobileErr, setMobileErr] = useState<string | null>(null);
  const [done, setDone] = useState<{ id: string; contact: string | null } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const digits = mobile.replace(/\D/g, "").replace(/^91(?=\d{10}$)/, "");
    if (!/^[6-9]\d{9}$/.test(digits)) {
      setMobileErr(j.lang === "hi" ? "10 अंकों का सही मोबाइल नंबर लिखें" : "Enter a valid 10-digit mobile number");
      return;
    }
    setMobileErr(null);
    setBusy(true);
    setErr(null);
    try {
      let sid = j.sessionId,
        tok = j.sessionToken;
      if (!sid) {
        const r = await createSession(j, set);
        sid = r.session_id;
        tok = r.session_token;
      }
      const r = await api<{ escalation_id: string; contact: string | null }>(`/api/advisor/sessions/${sid}/escalate`, {
        sessionToken: tok,
        body: { reason: j.advisorState === "not_serviceable" ? "partner_serviceability" : "advisor_help", preferred_time: when, note: note.trim() || null, mobile: digits },
      });
      setDone({ id: r.escalation_id, contact: r.contact });
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <h1 className="mb-1 text-[26px] font-bold">{t("help.callback_title")}</h1>
      <p className="mb-4 text-muted">{t("start.person_sub")}</p>
      {done ? (
        <Card className="animate-rise border-leaf/40">
          <p className="flex items-center gap-2 text-[18px] font-bold text-leaf">
            <CheckCircle2 className="size-6" aria-hidden /> {t("help.done")}
          </p>
          <p className="mt-2 text-ink-3">
            {t("help.ref", { id: done.id.slice(0, 8).toUpperCase() })}
            {done.contact && `, ${done.contact}`}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {j.recommendation && (
              <Link to="/plan" className="inline-flex min-h-12 items-center rounded-lg bg-brand px-5 font-semibold text-white hover:bg-brand-2">
                {t("advisor.see_plan")}
              </Link>
            )}
            <Link to="/" className="inline-flex min-h-12 items-center rounded-lg border border-control bg-white px-5 font-semibold hover:border-ink-3 hover:bg-mist">
              {t("common.back")}
            </Link>
          </div>
        </Card>
      ) : (
        <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)] sm:p-5" noValidate>
          <Field label={t("help.mobile")} htmlFor="cb-mobile" error={mobileErr} hint={t("help.mobile_hint")}>
            <Input id="cb-mobile" type="tel" inputMode="numeric" autoComplete="tel-national" value={mobile} onChange={(e) => setMobile(e.target.value)} maxLength={14} aria-invalid={!!mobileErr} />
          </Field>
          <fieldset>
            <legend className="mb-2 font-semibold">{t("help.time")}</legend>
            <div className="grid grid-cols-3 gap-2">
              {(["morning", "afternoon", "evening"] as const).map((w) => (
                <OptionRow key={w} name="when" checked={when === w} onChange={() => setWhen(w)} center className="px-2">
                  {t(`help.${w}`)}
                </OptionRow>
              ))}
            </div>
          </fieldset>
          <Field label={t("help.note")} htmlFor="cb-note">
            <Textarea id="cb-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
          </Field>
          {err && <Notice tone="error">{err}</Notice>}
          <Button type="submit" block size="lg" loading={busy}>
            {t("help.submit")}
          </Button>
        </form>
      )}
    </Shell>
  );
}

// ------------------------------------------------------------------ my privacy
type Summary = {
  customer: { name: string | null; mobile: string; language: string };
  consents: string[];
  orders: { order_no: string; status: string }[];
  kyc_cases: { id: string; status: string; gstin: string | null; udyam: string | null; documents: { slot: string; uploaded_at: string; delete_after: string | null }[] }[];
};

export function PrivacyPage() {
  const { j, t, logoutCustomer } = useJourney();
  const [s, setS] = useState<Summary | null>(null);
  const [consents, setConsents] = useState<Record<string, boolean> | null>(null);
  const [notice, setNotice] = useState<ConsentNotice | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  const load = () => {
    if (!j.customerToken) return;
    setLoadErr(null);
    const fail = (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) logoutCustomer();
      else setLoadErr(e instanceof ApiError && e.status !== 0 ? e.message : t("common.network"));
    };
    api<Summary>("/api/privacy/summary", { token: j.customerToken }).then(setS).catch(fail);
    api<{ purposes: Record<string, boolean> }>("/api/consent", { token: j.customerToken }).then((r) => setConsents(r.purposes)).catch(fail);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [j.customerToken]);
  useEffect(() => {
    api<ConsentNotice>(`/api/consent/notice?lang=${j.lang}`).then(setNotice).catch(() => undefined);
  }, [j.lang]);

  const withdraw = async (purpose: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<{ effect: string }>("/api/consent/withdraw", { token: j.customerToken, body: { purpose } });
      setMsg({ tone: "success", text: `${t(`purpose.${purpose}`)}: ${t("privacy.withdrawn")}. ${r.effect}` });
      setConfirm(null);
      load();
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const give = async (purpose: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await api("/api/consent", { token: j.customerToken, body: { purposes: { [purpose]: true }, notice_version: notice?.version, language: j.lang } });
      load();
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <div className="mb-4 flex items-center justify-between gap-2">
        <h1 className="text-[26px] font-bold">{t("privacy.title")}</h1>
        {j.customerToken && (
          <button onClick={logoutCustomer} className="inline-flex min-h-10 items-center gap-1.5 font-semibold text-brand-ink underline-offset-4 hover:underline">
            <LogOut className="size-4" aria-hidden /> {t("common.logout")}
          </button>
        )}
      </div>
      {!j.customerToken ? (
        <Card>
          <p className="mb-3 font-semibold">{t("common.login_needed")}</p>
          <OtpLogin />
        </Card>
      ) : loadErr ? (
        <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>{t("common.retry")}</Button>}>
          {loadErr}
        </Notice>
      ) : !s || !consents ? (
        <SkeletonCard lines={4} label={t("common.loading")} />
      ) : (
        <div className="space-y-4">
          {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
          <Card>
            <h2 className="mb-2 text-[18px] font-bold">{t("privacy.consents")}</h2>
            <ul className="divide-y divide-line">
              {Object.entries(consents).map(([p, on]) => (
                <li key={p} className="py-3">
                  <div className="flex items-center justify-between gap-3">
                    <span>
                      <span className="font-semibold">{t(`purpose.${p}`)}</span>{" "}
                      <Pill tone={on ? "good" : "neutral"}>{on ? t("privacy.given") : t("privacy.withdrawn")}</Pill>
                    </span>
                    {on ? (
                      <Button size="sm" variant="danger" onClick={() => setConfirm(p)} disabled={busy}>
                        {t("privacy.withdraw")}
                      </Button>
                    ) : (
                      <Button size="sm" variant="secondary" onClick={() => give(p)} disabled={busy}>
                        {t("privacy.give")}
                      </Button>
                    )}
                  </div>
                  {confirm === p && (
                    <div className="mt-2 rounded-lg border border-rust/30 bg-rust-soft p-3" role="alertdialog" aria-label={t("privacy.withdraw_confirm", { purpose: t(`purpose.${p}`) })}>
                      <p className="font-semibold">{t("privacy.withdraw_confirm", { purpose: t(`purpose.${p}`) })}</p>
                      {p === "kyc_verification" && <p className="mt-1 text-[15px]">{t("privacy.kyc_warning")}</p>}
                      <div className="mt-2 flex gap-2">
                        <Button size="sm" variant="danger" onClick={() => withdraw(p)} loading={busy}>
                          {t("privacy.withdraw")}
                        </Button>
                        <Button size="sm" variant="quiet" onClick={() => setConfirm(null)}>
                          {t("common.close")}
                        </Button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>
          <Card>
            <h2 className="mb-2 text-[18px] font-bold">{t("privacy.data")}</h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[15px]">
              <dt className="text-muted">{t("checkout.name")}</dt>
              <dd>{s.customer.name || "-"}</dd>
              <dt className="text-muted">{t("checkout.mobile")}</dt>
              <dd className="num">{s.customer.mobile}</dd>
              <dt className="text-muted">{t("privacy.orders")}</dt>
              <dd>{s.orders.length ? s.orders.map((o) => `${o.order_no} (${o.status.replace(/_/g, " ")})`).join(", ") : "-"}</dd>
            </dl>
            {s.kyc_cases.map((k) => (
              <div key={k.id} className="mt-3 rounded-lg bg-mist p-3 text-[15px]">
                <p className="font-semibold">
                  KYC: {k.status.replace(/_/g, " ")} {k.gstin && <span className="num font-normal">GSTIN {k.gstin}</span>} {k.udyam && <span className="num font-normal">Udyam {k.udyam}</span>}
                </p>
                <p className="mt-1 font-semibold">{t("privacy.documents")}</p>
                {k.documents.length ? (
                  <ul className="list-disc pl-5">
                    {k.documents.map((d) => (
                      <li key={d.slot}>
                        {t(`documents.${d.slot}`)}, {fmtDate(d.uploaded_at, j.lang)}
                        {d.delete_after && <span className="text-muted"> ({t("privacy.delete_after", { date: fmtDate(d.delete_after, j.lang) })})</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-muted">{t("privacy.empty")}</p>
                )}
              </div>
            ))}
          </Card>
          {notice && (
            <Card>
              <h2 className="mb-2 text-[18px] font-bold">{t("consent.rights")}</h2>
              <ul className="list-disc space-y-1 pl-5 text-[15px]">
                {notice.rights.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <p className="mt-3 text-[15px] text-muted">{notice.contact}</p>
            </Card>
          )}
        </div>
      )}
    </Shell>
  );
}
