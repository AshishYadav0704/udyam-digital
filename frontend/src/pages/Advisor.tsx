import clsx from "clsx";
import { Check, Cpu, Headset, RotateCcw, SendHorizontal, SquarePen } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Shell } from "../components/Shell";
import { Button, Checkbox, Field, Input, Money, Notice, OptionRow, Select, Skeleton } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { applyTurn, createSession } from "../lib/session";
import { selectionFromRecommendation, useJourney } from "../lib/store";
import type { AdvisorTurn, Profile, Recommendation } from "../lib/types";

function useErrorText() {
  const { t } = useJourney();
  return (e: unknown) => {
    if (e instanceof ApiError) {
      if (e.status === 0) return t("common.network");
      if (e.status === 404) return t("common.session_lost");
      return e.message;
    }
    return t("common.network");
  };
}

function ProfileSummary({ p }: { p: Profile }) {
  const { t, j } = useJourney();
  const bits: string[] = [];
  if (p.business_type) bits.push(p.business_type);
  if (p.city) bits.push(p.city);
  if (p.employees) bits.push(`${p.employees} ${j.lang === "hi" ? "लोग" : p.employees === 1 ? "person" : "people"}`);
  if (p.sites) bits.push(`${p.sites} ${j.lang === "hi" ? "साइट" : p.sites === 1 ? "site" : "sites"}`);
  if (p.has_gstin === true) bits.push(p.gstin_status && p.gstin_status !== "Active" ? `GSTIN ${p.gstin_status}` : "GSTIN ✓");
  if (p.has_gstin === false) bits.push(j.lang === "hi" ? "GSTIN नहीं" : "No GSTIN");
  for (const n of p.needs || []) bits.push(t(`need.${n}`));
  if (!bits.length) return null;
  return (
    <div className="rounded-xl border border-line bg-white px-3.5 py-2.5 shadow-[var(--shadow-card)]">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[14px] font-semibold text-ink-3">{t("advisor.known")}</span>
        <Link to="/advisor/form" className="inline-flex min-h-9 items-center gap-1 text-[14px] font-semibold text-brand-ink underline-offset-4 hover:underline">
          <SquarePen className="size-3.5" aria-hidden /> {t("advisor.edit_form")}
        </Link>
      </div>
      <ul className="flex flex-wrap gap-1.5">
        {bits.map((b) => (
          <li key={b} className="rounded-md bg-mist px-2 py-0.5 text-[14px] ring-1 ring-line ring-inset">
            {b}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PlanReady({ rec }: { rec: Recommendation }) {
  const { t } = useJourney();
  const nav = useNavigate();
  const q = rec.quote!;
  return (
    <div className="animate-rise rounded-xl border border-brand/40 bg-white p-4 shadow-[var(--shadow-raised)]">
      <p className="text-[15px] font-semibold text-brand-ink">{t("plan.your_plan")}</p>
      <p className="mt-0.5 text-[15px]">{(rec.items || []).map((i) => i.name).join(", ")}</p>
      <p className="mt-3">
        <Money value={q.monthly_subtotal} className="text-[28px] font-extrabold" />
        <span className="whitespace-nowrap text-muted"> {t("plan.permonth")}</span>
      </p>
      <Button block className="mt-3" onClick={() => nav("/plan")}>
        {t("advisor.see_plan")}
      </Button>
    </div>
  );
}

export function AdvisorChat() {
  const { j, set, t, resetAdvisor } = useJourney();
  const nav = useNavigate();
  const errText = useErrorText();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [profile, setProfile] = useState<Profile>({});
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const started = useRef(false);

  // start (or resume) the conversation
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!j.sessionId) {
      setBusy(true);
      createSession(j, set)
        .catch((e) => setError(errText(e)))
        .finally(() => setBusy(false));
    } else {
      api<{ profile: Profile }>(`/api/advisor/sessions/${j.sessionId}`, { sessionToken: j.sessionToken })
        .then((r) => setProfile(r.profile || {}))
        .catch((e) => {
          if (e instanceof ApiError && e.status === 404) resetAdvisor();
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [j.chat.length, busy]);

  useEffect(() => {
    setPicked([]);
  }, [j.expecting]);

  const send = async (payload: { text?: string; needs?: string[]; action?: "show_plan" | "skip" | "human" }) => {
    if (!j.sessionId || busy) return;
    setError(null);
    setBusy(true);
    const shown = payload.text || (payload.needs?.length ? payload.needs.map((n) => j.chips.find((c) => c.value === n)?.label || n).join(", ") : null);
    if (shown) set((prev) => ({ chat: [...prev.chat, { role: "user", text: shown }] }));
    try {
      const r = await api<AdvisorTurn>(`/api/advisor/sessions/${j.sessionId}/messages`, {
        body: { ...payload, language: j.lang },
        sessionToken: j.sessionToken,
      });
      applyTurn(r, set);
      setProfile(r.profile || {});
      setText("");
    } catch (e) {
      if (shown) set((prev) => ({ chat: prev.chat.slice(0, -1) }));
      if (payload.text) setText(payload.text);
      if (e instanceof ApiError && e.status === 404) {
        resetAdvisor();
        started.current = false;
      }
      setError(errText(e));
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const v = text.trim();
    if (v) send({ text: v });
  };

  const optionalSlot = j.expecting === "needs" || j.expecting === "spend";
  const rec = j.advisorState === "recommended" ? j.recommendation : null;
  const providerLabel = j.llmProvider === "offline" ? t("advisor.mode_offline") : `${t("advisor.mode_ai")} (${j.llmProvider})`;

  return (
    <Shell step="advisor">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h1 className="text-[22px] font-bold">{t("steps.advisor")}</h1>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-[13px] text-ink-3 ring-1 ring-line" title={t("plan.template_note")}>
          <Cpu className="size-3.5" aria-hidden /> {providerLabel}
        </span>
      </div>

      <div ref={logRef} role="log" aria-live="polite" aria-label={t("steps.advisor")} className="mb-3 max-h-[52dvh] min-h-60 space-y-2.5 overflow-y-auto rounded-xl bg-white/60 p-1 sm:max-h-[56dvh]">
        {j.chat.map((m, i) => (
          <div key={i} className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <p
              className={clsx(
                "max-w-[85%] animate-rise rounded-2xl px-3.5 py-2.5 leading-snug whitespace-pre-line",
                m.role === "user" ? "rounded-br-md bg-ink text-white" : "rounded-bl-md border border-line bg-white",
                m.kind === "note" && "border-amber/40 bg-amber-soft",
                m.kind === "recommendation" && "border-brand/30",
              )}
            >
              {m.text}
            </p>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start" aria-label={t("common.loading")}>
            <p className="typing rounded-2xl rounded-bl-md border border-line bg-white px-4 py-3">
              <span /> <span /> <span />
            </p>
          </div>
        )}
      </div>

      {error && (
        <Notice tone="error" className="mb-3" action={!j.sessionId ? <Button size="sm" variant="secondary" onClick={() => { started.current = false; setError(null); setBusy(true); createSession(j, set).catch((e) => setError(errText(e))).finally(() => setBusy(false)); }}>{t("common.retry")}</Button> : undefined}>
          {error}
        </Notice>
      )}

      {rec && rec.quote ? (
        <div className="space-y-3">
          <PlanReady rec={rec} />
        </div>
      ) : j.advisorState === "escalated" || j.advisorState === "not_serviceable" ? (
        <Notice
          tone="info"
          title={j.advisorState === "escalated" ? t("advisor.escalated") : t("advisor.not_serviceable")}
          action={
            <Button size="sm" onClick={() => nav("/help/callback")}>
              <Headset className="size-4" aria-hidden /> {t("advisor.add_number")}
            </Button>
          }
        />
      ) : (
        <>
          {j.chips.length > 0 && (
            <div className="mb-3">
              {j.multiSelect ? (
                <fieldset>
                  <legend className="sr-only">{t("form.needs")}</legend>
                  <div className="flex flex-wrap gap-2">
                    {j.chips.map((c) => {
                      const on = picked.includes(c.value);
                      return (
                        <button
                          key={c.value}
                          type="button"
                          aria-pressed={on}
                          onClick={() => setPicked((p) => (on ? p.filter((x) => x !== c.value) : [...p, c.value]))}
                          className={clsx(
                            "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-4 text-[15px] font-medium transition-colors",
                            on ? "border-brand bg-brand-soft text-brand-ink" : "border-control bg-white text-ink hover:border-ink-3",
                          )}
                        >
                          {on && <Check className="size-4" aria-hidden />}
                          {c.label}
                        </button>
                      );
                    })}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Button onClick={() => send({ needs: picked, action: "show_plan" })} disabled={busy}>
                      {t("advisor.show_plan")}
                    </Button>
                    <Button variant="quiet" onClick={() => send({ action: "skip", text: undefined })} disabled={busy}>
                      {t("advisor.skip")}
                    </Button>
                  </div>
                </fieldset>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {j.chips.map((c) => (
                    <button
                      key={c.value}
                      type="button"
                      onClick={() => send({ text: c.label })}
                      disabled={busy}
                      className="min-h-11 rounded-full border border-control bg-white px-4 text-[15px] font-medium text-ink transition-colors hover:border-brand hover:bg-brand-soft/40 disabled:opacity-50"
                    >
                      {c.label}
                    </button>
                  ))}
                  {optionalSlot && (
                    <button type="button" onClick={() => send({ action: "skip" })} disabled={busy} className="min-h-11 rounded-full px-3 text-[15px] text-muted underline-offset-4 hover:underline">
                      {t("advisor.skip")}
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
          <form onSubmit={onSubmit} className="flex gap-2">
            <label htmlFor="advisor-input" className="sr-only">
              {t("advisor.placeholder")}
            </label>
            <Input
              id="advisor-input"
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t("advisor.placeholder")}
              maxLength={600}
              autoComplete="off"
              enterKeyHint="send"
              disabled={!j.sessionId}
            />
            <Button type="submit" aria-label={t("advisor.send")} disabled={busy || !text.trim()} className="shrink-0 px-4">
              <SendHorizontal className="size-5" aria-hidden />
            </Button>
          </form>
        </>
      )}

      <div className="mt-4 space-y-3">
        <ProfileSummary p={profile} />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <button onClick={() => nav("/help/callback")} className="inline-flex min-h-11 items-center gap-1.5 font-semibold text-brand-ink underline-offset-4 hover:underline">
            <Headset className="size-4" aria-hidden /> {t("advisor.human")}
          </button>
          <button
            onClick={() => {
              resetAdvisor();
              started.current = false;
              setProfile({});
              setBusy(true);
              createSession({ ...j, sessionId: null }, set)
                .catch((e) => setError(errText(e)))
                .finally(() => setBusy(false));
            }}
            className="inline-flex min-h-11 items-center gap-1.5 text-ink-3 underline-offset-4 hover:underline"
          >
            <RotateCcw className="size-4" aria-hidden /> {t("advisor.restart")}
          </button>
        </div>
      </div>
    </Shell>
  );
}

// ------------------------------------------------------------------ form alternative
const NEED_OPTIONS = ["internet", "mobile_lines", "billing_pos", "cctv", "wifi_guest", "cloud_email", "backup_storage", "backup_internet", "website", "whatsapp", "sms", "endpoint_security", "cloud_telephony", "toll_free", "fleet", "machine_iot", "multi_site_mgmt", "high_speed"];

export function AdvisorForm() {
  const { j, set, t } = useJourney();
  const nav = useNavigate();
  const errText = useErrorText();
  const [types, setTypes] = useState<{ name: string; segment: string }[] | null>(null);
  const [typesErr, setTypesErr] = useState(false);
  const [cities, setCities] = useState<string[]>([]);
  const [f, setF] = useState({ business_type: "", city: "", employees: "", sites: "1", has_gstin: "", gstin: "", needs: [] as string[] });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notServiceable, setNotServiceable] = useState<string | null>(null);

  const loadTypes = () => {
    setTypesErr(false);
    api<{ business_types: { name: string; segment: string }[] }>("/api/catalogue/business-types")
      .then((d) => setTypes(d.business_types))
      .catch(() => setTypesErr(true));
  };
  useEffect(() => {
    loadTypes();
    api<{ cities: any[] }>("/api/catalogue/cities")
      .then((d) => setCities(d.cities.map((c: any) => (typeof c === "string" ? c : c.name)).filter(Boolean)))
      .catch(() => setCities([]));
  }, []);

  // prefill from what the chat already learned
  useEffect(() => {
    if (!j.sessionId) return;
    api<{ profile: Profile }>(`/api/advisor/sessions/${j.sessionId}`, { sessionToken: j.sessionToken })
      .then(({ profile: p }) =>
        setF((cur) => ({
          business_type: p.business_type || cur.business_type,
          city: p.city || cur.city,
          employees: p.employees ? String(p.employees) : cur.employees,
          sites: p.sites ? String(p.sites) : cur.sites,
          has_gstin: p.has_gstin === true ? "yes" : p.has_gstin === false ? "no" : cur.has_gstin,
          gstin: cur.gstin,
          needs: p.needs?.length ? p.needs : cur.needs,
        })),
      )
      .catch(() => undefined);
  }, [j.sessionId, j.sessionToken]);

  const byGroup = useMemo(() => {
    const g: Record<string, string[]> = {};
    for (const b of types || []) (g[b.segment] ||= []).push(b.name);
    return g;
  }, [types]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const req = t("common.required");
    if (!f.business_type) errs.business_type = req;
    if (!f.city.trim()) errs.city = req;
    const emp = Number(f.employees);
    if (!f.employees || !Number.isInteger(emp) || emp < 1 || emp > 5000) errs.employees = j.lang === "hi" ? "1 से 5000 के बीच संख्या लिखें" : "Enter a number from 1 to 5000";
    const sites = Number(f.sites);
    if (!Number.isInteger(sites) || sites < 1 || sites > 200) errs.sites = j.lang === "hi" ? "1 से 200 के बीच संख्या लिखें" : "Enter a number from 1 to 200";
    if (!f.has_gstin) errs.has_gstin = req;
    if (f.has_gstin === "yes" && f.gstin && f.gstin.replace(/\s/g, "").length !== 15) errs.gstin = j.lang === "hi" ? "GSTIN में 15 अक्षर होते हैं" : "A GSTIN has 15 characters";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError(null);
    setNotServiceable(null);
    try {
      let sid = j.sessionId,
        tok = j.sessionToken;
      if (!sid) {
        const r = await createSession(j, set);
        sid = r.session_id;
        tok = (r as any).session_token;
      }
      const body: Record<string, any> = {
        business_type: f.business_type,
        city: f.city.trim(),
        employees: emp,
        sites,
        has_gstin: f.has_gstin === "yes",
        needs: f.needs,
        language: j.lang,
      };
      if (f.has_gstin === "yes" && f.gstin.trim()) body.gstin = f.gstin.replace(/\s/g, "").toUpperCase();
      const r = await api<{ profile: Profile; missing: string[]; recommendation: Recommendation | null; state: string }>(`/api/advisor/sessions/${sid}/profile`, {
        method: "PATCH",
        body,
        sessionToken: tok,
      });
      if (r.recommendation?.status === "ok") {
        set({ recommendation: r.recommendation, selection: selectionFromRecommendation(r.recommendation), advisorState: "recommended" });
        nav("/plan");
      } else if (r.recommendation?.status === "not_serviceable") {
        set({ advisorState: "not_serviceable" });
        setNotServiceable(r.profile.city || f.city);
      } else {
        setError(t("form.missing", { fields: r.missing.join(", ") }));
      }
    } catch (e) {
      if (e instanceof ApiError && (e.detail as any)?.field === "gstin") setErrors({ gstin: e.message });
      else setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const segName: Record<string, string> = j.lang === "hi" ? { micro: "छोटी दुकान / सेवा", prof: "पेशेवर सेवाएँ", multi: "कई ब्रांच", mfg: "निर्माण" } : { micro: "Shops and services", prof: "Professional practices", multi: "Multi-branch", mfg: "Manufacturing" };

  return (
    <Shell step="advisor">
      <h1 className="mb-1 text-[26px] leading-tight font-bold">{t("form.title")}</h1>
      <p className="mb-5 text-muted">{t("form.sub")}</p>
      <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)] sm:p-5" noValidate>
        {typesErr && (
          <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={loadTypes}>{t("common.retry")}</Button>}>
            {t("form.types_error")}
          </Notice>
        )}
        <Field label={t("form.type")} htmlFor="bt" error={errors.business_type}>
          {types === null && !typesErr ? (
            <Skeleton className="h-12 w-full rounded-lg" />
          ) : (
          <Select id="bt" value={f.business_type} onChange={(e) => setF({ ...f, business_type: e.target.value })} aria-invalid={!!errors.business_type} disabled={!types?.length}>
            <option value="">{t("form.choose")}</option>
            {Object.entries(byGroup).map(([seg, names]) => (
              <optgroup key={seg} label={segName[seg] || seg}>
                {names.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
          )}
        </Field>
        <Field label={t("form.city")} htmlFor="city" error={errors.city}>
          <Input id="city" list="city-list" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} aria-invalid={!!errors.city} autoComplete="address-level2" />
          <datalist id="city-list">
            {cities.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("form.employees")} htmlFor="emp" error={errors.employees}>
            <Input id="emp" inputMode="numeric" value={f.employees} onChange={(e) => setF({ ...f, employees: e.target.value.replace(/\D/g, "") })} aria-invalid={!!errors.employees} />
          </Field>
          <Field label={t("form.sites")} htmlFor="sites" error={errors.sites}>
            <Input id="sites" inputMode="numeric" value={f.sites} onChange={(e) => setF({ ...f, sites: e.target.value.replace(/\D/g, "") })} aria-invalid={!!errors.sites} />
          </Field>
        </div>
        <fieldset className="space-y-2">
          <legend className="font-semibold">{t("form.gst")}</legend>
          <div className="grid grid-cols-2 gap-2">
            {(["yes", "no"] as const).map((v) => (
              <OptionRow key={v} name="gst" checked={f.has_gstin === v} onChange={() => setF({ ...f, has_gstin: v })}>
                {v === "yes" ? t("form.gst_yes") : t("form.gst_no")}
              </OptionRow>
            ))}
          </div>
          {errors.has_gstin && <p className="text-[15px] font-medium text-rust" role="alert">{errors.has_gstin}</p>}
        </fieldset>
        {f.has_gstin === "yes" && (
          <Field label={t("form.gstin")} htmlFor="gstin" error={errors.gstin}>
            <Input id="gstin" value={f.gstin} onChange={(e) => setF({ ...f, gstin: e.target.value.toUpperCase() })} maxLength={17} autoCapitalize="characters" spellCheck={false} aria-invalid={!!errors.gstin} />
          </Field>
        )}
        <fieldset>
          <legend className="mb-2 font-semibold">{t("form.needs")}</legend>
          <div className="grid grid-cols-1 gap-x-4 min-[420px]:grid-cols-2">
            {NEED_OPTIONS.map((n) => (
              <Checkbox key={n} checked={f.needs.includes(n)} onChange={(on) => setF({ ...f, needs: on ? [...f.needs, n] : f.needs.filter((x) => x !== n) })}>
                {t(`need.${n}`)}
              </Checkbox>
            ))}
          </div>
        </fieldset>
        {error && <Notice tone="error">{error}</Notice>}
        {notServiceable && (
          <Notice tone="info" title={t("form.not_serviceable", { city: notServiceable })} action={<Button size="sm" onClick={() => nav("/help/callback")}>{t("advisor.add_number")}</Button>} />
        )}
        <Button type="submit" block size="lg" loading={busy}>
          {t("form.submit")}
        </Button>
        <p className="text-center">
          <Link to="/advisor" className="inline-flex min-h-10 items-center font-semibold text-brand-ink underline-offset-4 hover:underline">
            {t("start.chat")}
          </Link>
        </p>
      </form>
    </Shell>
  );
}
