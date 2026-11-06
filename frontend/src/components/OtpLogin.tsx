import { useState, type FormEvent } from "react";
import { api, ApiError } from "../lib/api";
import { useJourney } from "../lib/store";
import { Button, Field, Input, Notice } from "./ui";

/** Mobile + OTP login. In the prototype the OTP is shown on screen (no SMS gateway); production sends it by SMS only. */
export function OtpLogin({ askName, onDone }: { askName?: boolean; onDone?: () => void }) {
  const { j, set, t } = useJourney();
  const [mobile, setMobile] = useState("");
  const [otp, setOtp] = useState("");
  const [name, setName] = useState("");
  const [sent, setSent] = useState<{ masked: string; demo_otp?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const msg = (e: unknown) => (e instanceof ApiError ? (e.status === 0 ? t("common.network") : e.message) : t("common.network"));

  const request = async (e: FormEvent) => {
    e.preventDefault();
    const digits = mobile.replace(/\D/g, "").replace(/^91(?=\d{10}$)/, "");
    if (!/^[6-9]\d{9}$/.test(digits)) {
      setErr(j.lang === "hi" ? "10 अंकों का सही मोबाइल नंबर लिखें" : "Enter a valid 10-digit mobile number");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await api<{ masked: string; demo_otp?: string }>("/api/auth/otp/request", { body: { mobile: digits } });
      setSent(r);
      setMobile(digits);
    } catch (e) {
      setErr(msg(e));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (e: FormEvent) => {
    e.preventDefault();
    if (!/^\d{4,8}$/.test(otp)) {
      setErr(j.lang === "hi" ? "OTP लिखें" : "Enter the OTP");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await api<{ token: string; customer: { id: string; name: string | null; mobile: string } }>("/api/auth/otp/verify", {
        body: { mobile, otp, name: name.trim() || null, language: j.lang, partner_code: j.attribution?.partner_code || null },
      });
      set({ customerToken: r.token, customer: r.customer });
      onDone?.();
    } catch (e) {
      setErr(msg(e));
    } finally {
      setBusy(false);
    }
  };

  if (!sent)
    return (
      <form onSubmit={request} className="space-y-3" noValidate>
        <Field label={t("checkout.mobile")} htmlFor="mobile" error={err}>
          <Input id="mobile" type="tel" inputMode="numeric" autoComplete="tel-national" value={mobile} onChange={(e) => setMobile(e.target.value)} maxLength={14} aria-invalid={!!err} />
        </Field>
        <Button type="submit" loading={busy} block>
          {t("checkout.send_otp")}
        </Button>
      </form>
    );

  return (
    <form onSubmit={verify} className="space-y-3" noValidate>
      <p className="text-[15px]">
        {t("checkout.otp_sent", { masked: sent.masked })}{" "}
        <button type="button" className="inline-flex min-h-10 items-center font-semibold text-brand-ink underline underline-offset-4" onClick={() => { setSent(null); setOtp(""); setErr(null); }}>
          {t("checkout.change_number")}
        </button>
      </p>
      {sent.demo_otp && <Notice tone="warn">{t("checkout.demo_otp", { otp: sent.demo_otp })}</Notice>}
      <Field label={t("checkout.otp")} htmlFor="otp" error={err}>
        <Input id="otp" inputMode="numeric" autoComplete="one-time-code" value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))} maxLength={8} aria-invalid={!!err} />
      </Field>
      {askName && (
        <Field label={t("checkout.name")} htmlFor="cname" hint={t("checkout.name_hint")} optional={t("common.optional")}>
          <Input id="cname" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoComplete="name" />
        </Field>
      )}
      <Button type="submit" loading={busy} block>
        {t("checkout.verify")}
      </Button>
    </form>
  );
}
