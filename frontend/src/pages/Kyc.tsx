import clsx from "clsx";
import { AlertTriangle, Camera, CheckCircle2, ChevronDown, Clock3, Eye, EyeOff, FileCheck2, RefreshCw, ShieldAlert, Wand2 } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { OtpLogin } from "../components/OtpLogin";
import { Shell } from "../components/Shell";
import { Button, Card, Checkbox, EmptyState, Field, Input, Notice, Pill, Select, SkeletonCard, Toggle } from "../components/ui";
import { api, ApiError, fetchImage, fmtDate } from "../lib/api";
import { useJourney } from "../lib/store";
import type { ConsentNotice, KycCase, KycDoc, KycFinding, OrderView } from "../lib/types";

function useOrder() {
  const { j, set } = useJourney();
  const [order, setOrder] = useState<OrderView | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  useEffect(() => {
    if (!j.orderId || !j.customerToken) return;
    api<OrderView>(`/api/orders/${j.orderId}?lang=${j.lang}`, { token: j.customerToken })
      .then((o) => {
        setOrder(o);
        if (o.kyc?.case_id && !j.caseId) set({ caseId: o.kyc.case_id });
      })
      .catch((e) => setErr(e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j.orderId, j.customerToken, j.lang]);
  return { order, err };
}

function NeedOrder() {
  const { j, t } = useJourney();
  const nav = useNavigate();
  return (
    <Shell step="kyc">
      {!j.customerToken ? (
        <Card>
          <p className="mb-3 font-semibold">{t("common.login_needed")}</p>
          <OtpLogin />
        </Card>
      ) : (
        <EmptyState title={t("kyc.no_order")} action={<Button onClick={() => nav("/orders")}>{t("track.find")}</Button>} />
      )}
    </Shell>
  );
}

// ------------------------------------------------------------------ consent (screen 9)
export function ConsentPage() {
  const { j, t } = useJourney();
  const nav = useNavigate();
  const { order } = useOrder();
  const [notice, setNotice] = useState<ConsentNotice | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [choices, setChoices] = useState<Record<string, boolean>>({ kyc_verification: false, partner_assist: false, marketing: false });
  const [open, setOpen] = useState<string | null>("kyc_verification");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    setLoadErr(null);
    api<ConsentNotice>(`/api/consent/notice?lang=${j.lang}`)
      .then(setNotice)
      .catch(() => setLoadErr(t("common.network")));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [j.lang]);

  if (!j.customerToken || !j.orderId) return <NeedOrder />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!choices.kyc_verification) {
      setErr(t("consent.need_required"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api("/api/consent", { token: j.customerToken, body: { purposes: choices, notice_version: notice!.version, language: j.lang } });
      nav("/kyc/upload");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) load();
      setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell step="kyc">
      {order && (
        <Notice tone="success" className="mb-4">
          {t("consent.order_banner", { no: order.order_no })}
        </Notice>
      )}
      {loadErr && <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>{t("common.retry")}</Button>}>{loadErr}</Notice>}
      {!notice && !loadErr && <SkeletonCard lines={5} label={t("common.loading")} />}
      {notice && (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div>
            <h1 className="text-[26px] leading-tight font-bold">{notice.title}</h1>
            <p className="mt-1 text-ink-3">{notice.intro}</p>
          </div>
          {notice.purposes.map((p) => {
            const isOpen = open === p.id;
            return (
              <Card key={p.id} className={clsx(p.required && "border-brand/40")}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <Pill tone={p.required ? "brand" : "neutral"}>{p.required ? t("consent.required") : t("consent.optional")}</Pill>
                    <h2 className="mt-1.5 text-[18px] font-bold">{p.title}</h2>
                  </div>
                  {!p.required && <Toggle checked={!!choices[p.id]} onChange={(v) => setChoices({ ...choices, [p.id]: v })} label={p.title} />}
                </div>
                <button type="button" onClick={() => setOpen(isOpen ? null : p.id)} aria-expanded={isOpen} className="mt-2 inline-flex min-h-10 items-center gap-1 text-left text-[15px] font-semibold text-brand-ink underline-offset-4 hover:underline">
                  {t("consent.data")}, {t("consent.why").toLowerCase()}, {t("consent.retention").toLowerCase()}
                  <ChevronDown className={clsx("size-4 transition-transform", isOpen && "rotate-180")} aria-hidden />
                </button>
                {isOpen && (
                  <dl className="mt-2 space-y-2.5 text-[15px]">
                    <div>
                      <dt className="font-semibold">{t("consent.data")}</dt>
                      <dd>
                        <ul className="list-disc pl-5">
                          {p.data.map((d) => (
                            <li key={d}>{d}</li>
                          ))}
                        </ul>
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold">{t("consent.why")}</dt>
                      <dd>{p.why}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold">{t("consent.who")}</dt>
                      <dd>{p.who}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold">{t("consent.retention")}</dt>
                      <dd>{p.retention}</dd>
                    </div>
                  </dl>
                )}
                {p.required && (
                  <div className="mt-3 border-t border-line pt-3">
                    <Checkbox checked={choices.kyc_verification} onChange={(v) => setChoices({ ...choices, kyc_verification: v })}>
                      <span className="font-semibold">{t("consent.agree")}</span>
                    </Checkbox>
                  </div>
                )}
              </Card>
            );
          })}
          <p className="text-[15px] text-ink-3">{notice.always}</p>
          <details className="rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)]">
            <summary className="flex min-h-10 cursor-pointer items-center font-bold">{t("consent.rights")}</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-[15px]">
              {notice.rights.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <p className="mt-3 text-[15px] text-muted">{notice.contact}</p>
          </details>
          <p className="text-[14px] text-muted">
            {notice.language_note} v{notice.version}
          </p>
          {err && <Notice tone="error">{err}</Notice>}
          <Button type="submit" block size="lg" loading={busy}>
            {busy ? t("consent.saving") : t("consent.continue")}
          </Button>
        </form>
      )}
    </Shell>
  );
}

// ------------------------------------------------------------------ upload (screen 10)
const SLOTS = ["gst_certificate", "udyam_certificate", "address_proof", "signatory_id"] as const;
const SPECIMENS = Array.from({ length: 12 }, (_, i) => `K${String(i + 1).padStart(2, "0")}`);

function DocThumb({ caseId, doc }: { caseId: string; doc: KycDoc }) {
  const { j } = useJourney();
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let made: string | null = null;
    fetchImage(`/api/kyc/cases/${caseId}/documents/${doc.id}/image`, j.customerToken!)
      .then((u) => {
        made = u;
        if (alive) setUrl(u);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [caseId, doc.id, j.customerToken]);
  return url ? <img src={url} alt={doc.label} className="h-20 w-16 shrink-0 rounded-md border border-line bg-mist object-cover object-top" /> : <span className="h-20 w-16 shrink-0 animate-pulse rounded-md border border-line bg-mist" aria-hidden />;
}

function Slot({ slot, doc, caseId, onUploaded, optional }: { slot: string; doc?: KycDoc; caseId: string; onUploaded: (c: KycCase) => void; optional?: boolean }) {
  const { j, t } = useJourney();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pick = async (f: File | undefined) => {
    if (!f) return;
    if (!/^image\/(png|jpeg)$/.test(f.type)) {
      setErr(j.lang === "hi" ? "सिर्फ़ PNG या JPEG फ़ोटो/स्कैन" : "Only PNG or JPEG photos or scans");
      return;
    }
    if (f.size > 5 * 1024 * 1024) {
      setErr(j.lang === "hi" ? "फ़ाइल 5 MB से बड़ी है" : "File is larger than 5 MB");
      return;
    }
    setBusy(true);
    setErr(null);
    const fd = new FormData();
    fd.append("slot", slot);
    fd.append("file", f);
    try {
      const r = await api<{ case: KycCase }>(`/api/kyc/cases/${caseId}/documents?lang=${j.lang}`, { form: fd, token: j.customerToken });
      onUploaded(r.case);
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : (e as Error).message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const read = doc ? Object.values(doc.fields).filter((f) => f.value).length : 0;
  return (
    <li className={clsx("rounded-xl border bg-white p-3.5 shadow-[var(--shadow-card)]", doc ? "border-line" : "border-dashed border-line-strong")}>
      <div className="flex items-start gap-3">
        {doc ? <DocThumb caseId={caseId} doc={doc} /> : <span className="grid h-20 w-16 shrink-0 place-items-center rounded-md border border-dashed border-control text-muted"><Camera className="size-6" aria-hidden /></span>}
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            {t(`documents.${slot}`)} {optional && <span className="text-[14px] font-normal text-muted">({t("kyc.optional_slot")})</span>}
          </p>
          <p className="text-[14px] text-muted">{t(`kyc.slot_hint.${slot}`)}</p>
          {doc && (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {doc.quality.is_blurry ? <Pill tone="warn">{t("kyc.blurry")}</Pill> : <Pill tone="good"><CheckCircle2 className="size-3.5" aria-hidden />{t("kyc.read_ok", { n: read })}</Pill>}
              {doc.quality.is_low_resolution && <Pill tone="warn">{t("kyc.low_res")}</Pill>}
              {Math.abs(doc.deskewed_by) >= 0.5 && <Pill>{t("kyc.deskewed", { deg: Math.abs(doc.deskewed_by).toFixed(1) })}</Pill>}
            </div>
          )}
          <input ref={inputRef} type="file" accept="image/png,image/jpeg" capture="environment" className="sr-only" id={`file-${slot}`} onChange={(e) => pick(e.target.files?.[0])} />
          <label htmlFor={`file-${slot}`} className={clsx("mt-2 inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-3.5 text-[15px] font-semibold transition-colors", doc ? "border border-control bg-white text-ink hover:border-ink-3 hover:bg-mist" : "bg-brand text-white hover:bg-brand-2", busy && "pointer-events-none opacity-60")}>
            {busy ? <RefreshCw className="size-4 animate-spin" aria-hidden /> : <Camera className="size-4" aria-hidden />}
            {busy ? t("kyc.uploading") : doc ? t("kyc.replace") : t("kyc.choose")}
          </label>
          {err && <p className="mt-1.5 text-[15px] font-medium text-rust" role="alert">{err}</p>}
        </div>
      </div>
    </li>
  );
}

export function UploadPage() {
  const { j, set, t, logoutCustomer } = useJourney();
  const nav = useNavigate();
  const { order } = useOrder();
  const [kcase, setCase] = useState<KycCase | null>(null);
  const [decl, setDecl] = useState({ business_name: "", signatory_name: "", gstin: "", udyam_number: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [specimen, setSpecimen] = useState("K02");
  const [specBusy, setSpecBusy] = useState(false);
  const [verifying, setVerifying] = useState(false);

  // prefill the declaration from the advisor profile and login
  useEffect(() => {
    const p = j.recommendation?.profile;
    setDecl((d) => ({
      business_name: d.business_name || p?.business_name || "",
      signatory_name: d.signatory_name || j.customer?.name || "",
      gstin: d.gstin || p?.gstin || "",
      udyam_number: d.udyam_number,
    }));
  }, [j.recommendation, j.customer]);

  useEffect(() => {
    if (!j.caseId || !j.customerToken) return;
    api<KycCase>(`/api/kyc/cases/${j.caseId}?lang=${j.lang}`, { token: j.customerToken })
      .then(setCase)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) set({ caseId: null });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j.caseId, j.lang]);

  if (!j.customerToken || !j.orderId) return <NeedOrder />;

  const createCase = async (e: FormEvent) => {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (decl.business_name.trim().length < 2) er.business_name = t("common.required");
    if (decl.signatory_name.trim().length < 2) er.signatory_name = t("common.required");
    if (decl.gstin && decl.gstin.replace(/\s/g, "").length !== 15) er.gstin = j.lang === "hi" ? "GSTIN में 15 अक्षर होते हैं" : "A GSTIN has 15 characters";
    setErrs(er);
    if (Object.keys(er).length) return;
    setBusy(true);
    setErr(null);
    try {
      const p = j.recommendation?.profile;
      const r = await api<{ case_id: string }>("/api/kyc/cases", {
        token: j.customerToken,
        body: {
          order_id: j.orderId,
          declaration: {
            business_name: decl.business_name.trim(),
            signatory_name: decl.signatory_name.trim(),
            gstin: decl.gstin.replace(/\s/g, "").toUpperCase() || null,
            udyam_number: decl.udyam_number.trim().toUpperCase() || null,
            city: p?.city || null,
            state: p?.state || null,
          },
        },
      });
      set({ caseId: r.case_id });
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) nav("/kyc/consent");
      else if (e instanceof ApiError && e.status === 401) logoutCustomer();
      setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const loadSpecimen = async () => {
    if (!j.caseId) return;
    setSpecBusy(true);
    setErr(null);
    try {
      setCase(await api<KycCase>(`/api/kyc/cases/${j.caseId}/specimen?lang=${j.lang}`, { token: j.customerToken, body: { applicant: specimen } }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSpecBusy(false);
    }
  };

  const verify = async () => {
    setVerifying(true);
    setErr(null);
    try {
      await api<KycCase>(`/api/kyc/cases/${j.caseId}/evaluate?lang=${j.lang}`, { token: j.customerToken, method: "POST" });
      nav("/kyc/result");
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : (e as Error).message);
    } finally {
      setVerifying(false);
    }
  };

  const docs = Object.fromEntries((kcase?.documents || []).map((d) => [d.slot, d]));
  const declared = kcase?.declaration;
  const hasRequired = !!docs.address_proof && !!docs.signatory_id;

  return (
    <Shell step="kyc">
      <h1 className="mb-1 text-[26px] font-bold">{t("kyc.title")}</h1>
      {order && <p className="mb-4 text-muted">{t("confirm.order_no")}: <span className="num font-semibold text-ink">{order.order_no}</span></p>}

      {!j.caseId ? (
        <form onSubmit={createCase} className="space-y-3" noValidate>
          <Card>
            <h2 className="mb-3 text-[18px] font-bold">{t("kyc.declaration")}</h2>
            <div className="space-y-3">
              <Field label={t("kyc.business_name")} htmlFor="bn" error={errs.business_name}>
                <Input id="bn" value={decl.business_name} onChange={(e) => setDecl({ ...decl, business_name: e.target.value })} maxLength={120} aria-invalid={!!errs.business_name} autoComplete="organization" />
              </Field>
              <Field label={t("kyc.signatory")} htmlFor="sg" error={errs.signatory_name}>
                <Input id="sg" value={decl.signatory_name} onChange={(e) => setDecl({ ...decl, signatory_name: e.target.value })} maxLength={120} aria-invalid={!!errs.signatory_name} autoComplete="name" />
              </Field>
              <Field label={t("kyc.gstin")} htmlFor="gs" error={errs.gstin} optional={t("common.optional")}>
                <Input id="gs" value={decl.gstin} onChange={(e) => setDecl({ ...decl, gstin: e.target.value.toUpperCase() })} maxLength={17} spellCheck={false} autoCapitalize="characters" aria-invalid={!!errs.gstin} />
              </Field>
              <Field label={t("kyc.udyam")} htmlFor="ud">
                <Input id="ud" value={decl.udyam_number} onChange={(e) => setDecl({ ...decl, udyam_number: e.target.value.toUpperCase() })} maxLength={25} spellCheck={false} placeholder="UDYAM-XX-00-0000000" />
              </Field>
            </div>
          </Card>
          {err && <Notice tone="error">{err}</Notice>}
          <Button type="submit" block size="lg" loading={busy}>
            {t("kyc.save_details")}
          </Button>
        </form>
      ) : (
        <div className="space-y-4">
          {declared && (
            <Card className="text-[15px]">
              <div className="flex flex-wrap gap-x-6 gap-y-1">
                <span><span className="text-muted">{t("kyc.business_name")}: </span><b>{declared.business_name}</b></span>
                <span><span className="text-muted">{t("kyc.signatory")}: </span><b>{declared.signatory_name}</b></span>
                {declared.gstin && <span className="num"><span className="text-muted">GSTIN: </span>{declared.gstin}</span>}
                {declared.udyam_number && <span className="num"><span className="text-muted">Udyam: </span>{declared.udyam_number}</span>}
              </div>
            </Card>
          )}
          <ul className="space-y-2.5">
            {SLOTS.filter((s) => s !== "gst_certificate" || declared?.gstin || docs.gst_certificate).map((s) => (
              <Slot key={s} slot={s} doc={docs[s]} caseId={j.caseId!} onUploaded={setCase} optional={s === "udyam_certificate" || (s === "gst_certificate" && !declared?.gstin)} />
            ))}
          </ul>
          <p className="flex items-start gap-2 text-[14px] text-muted">
            <FileCheck2 className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("kyc.digilocker")}
          </p>

          <div className="rounded-xl border border-dashed border-amber/60 bg-amber-soft/60 p-3.5">
            <p className="flex items-center gap-2 font-semibold">
              <Wand2 className="size-4" aria-hidden /> {t("kyc.sample")}
            </p>
            <p className="mb-2 text-[14px] text-ink-3">{t("kyc.sample_hint")}</p>
            <div className="flex gap-2">
              <label htmlFor="spec" className="sr-only">{t("kyc.choose_applicant")}</label>
              <Select id="spec" value={specimen} onChange={(e) => setSpecimen(e.target.value)} className="max-w-32">
                {SPECIMENS.map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </Select>
              <Button variant="secondary" onClick={loadSpecimen} loading={specBusy}>{t("kyc.load")}</Button>
            </div>
          </div>

          {err && <Notice tone="error">{err}</Notice>}
          {!hasRequired && <p className="text-[15px] text-muted">{t("kyc.missing_required")}</p>}
          <Button block size="lg" onClick={verify} loading={verifying} disabled={!hasRequired}>
            {verifying ? t("kyc.checking") : t("kyc.verify")}
          </Button>
        </div>
      )}
    </Shell>
  );
}

// ------------------------------------------------------------------ verification result (screen 11)
const SEV_ORDER: KycFinding["severity"][] = ["block", "resubmit", "review", "info"];
const LOW_CONFIDENCE = 0.8;    // same threshold the server uses (OCR_MIN_FIELD_CONFIDENCE)
const SEV_ICON = { block: ShieldAlert, resubmit: AlertTriangle, review: Clock3, info: CheckCircle2 } as const;
const SEV_TONE = { block: "bad", resubmit: "warn", review: "neutral", info: "good" } as const;

function DocDetail({ caseId, doc, token }: { caseId: string; doc: KycDoc; token: string }) {
  const { t } = useJourney();
  const [show, setShow] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!show || url) return;
    fetchImage(`/api/kyc/cases/${caseId}/documents/${doc.id}/image`, token).then(setUrl).catch(() => undefined);
  }, [show, url, caseId, doc.id, token]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const fields = Object.entries(doc.fields).filter(([, f]) => f.value);
  return (
    <li className="rounded-xl border border-line bg-white p-3.5 shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold">{doc.label}</p>
        <button onClick={() => setShow(!show)} className="inline-flex min-h-10 items-center gap-1 text-[15px] font-semibold text-brand-ink underline-offset-4 hover:underline" aria-expanded={show}>
          {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />} {show ? t("kyc.hide") : t("kyc.view")}
        </button>
      </div>
      {show && !url && <span className="mt-2 block h-40 w-full animate-pulse rounded-md bg-mist" aria-hidden />}
      {show && url && <img src={url} alt={doc.label} className="mt-2 w-full rounded-md border border-line" />}
      {fields.length > 0 && (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[14px]">
          {fields.map(([k, f]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{t(`field.${k}`) === `field.${k}` ? k.replace(/_/g, " ") : t(`field.${k}`)}</dt>
              <dd className="num min-w-0 break-words">
                {f.value} {f.validated && <CheckCircle2 className="inline size-3.5 text-leaf" aria-label="validated" />}
                {f.confidence < LOW_CONFIDENCE ? (
                  <Pill tone="warn" className="ml-1.5 align-middle text-[13px]">{t("kyc.low_confidence", { pct: Math.round(f.confidence * 100) })}</Pill>
                ) : (
                  <span className="ml-1 text-[13px] text-muted">{t("kyc.confidence", { pct: Math.round(f.confidence * 100) })}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  );
}

export function ResultPage() {
  const { j, t } = useJourney();
  const nav = useNavigate();
  const [kcase, setCase] = useState<KycCase | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    if (!j.caseId || !j.customerToken) return;
    setErr(null);
    api<KycCase>(`/api/kyc/cases/${j.caseId}?lang=${j.lang}`, { token: j.customerToken })
      .then(setCase)
      .catch((e) => setErr(e instanceof ApiError && e.status === 0 ? t("common.network") : e.message));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [j.caseId, j.lang]);
  if (!j.customerToken || !j.caseId) return <NeedOrder />;
  if (err) return <Shell step="kyc"><Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>{t("common.retry")}</Button>}>{err}</Notice></Shell>;
  if (!kcase) return <Shell step="kyc"><SkeletonCard lines={4} label={t("kyc.checking")} /></Shell>;

  const decision = kcase.decision;
  const tone = decision === "verified" ? "success" : decision === "action_required" ? "warn" : "info";
  const groups = SEV_ORDER.map((s) => [s, kcase.findings.filter((f) => f.severity === s)] as const).filter(([, fs]) => fs.length);
  const reg = kcase.registry || {};

  return (
    <Shell step="kyc">
      <h1 className="mb-3 text-[26px] font-bold">{t("kyc.result")}</h1>
      {decision ? (
        <Notice tone={tone} title={kcase.decision_label || decision}>
          {t(`kyc.decision.${decision}`)}
        </Notice>
      ) : (
        <Notice tone="info">{t("kyc.missing_required")}</Notice>
      )}

      {groups.map(([sev, fs]) => {
        const Icon = SEV_ICON[sev];
        return (
          <section key={sev} className="mt-4">
            <h2 className="mb-2 flex items-center gap-2 text-[17px] font-bold">
              <Icon className="size-5" aria-hidden /> {t(`kyc.sev.${sev}`)}
            </h2>
            <ul className="space-y-2">
              {fs.map((f, i) => (
                <li key={f.code + i} className="rounded-xl border border-line bg-white px-3.5 py-3 shadow-[var(--shadow-card)]">
                  <div className="flex items-start justify-between gap-2">
                    <p>{f.text}</p>
                    <Pill tone={SEV_TONE[sev]}>{f.code.replace(/_/g, " ").toLowerCase()}</Pill>
                  </div>
                  {f.resolution && <p className="mt-1 text-[14px] text-muted">{f.resolution}</p>}
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {(reg.gstin || reg.udyam) && (
        <section className="mt-5">
          <h2 className="mb-1 text-[17px] font-bold">{t("kyc.registry")}</h2>
          <p className="mb-2 text-[14px] text-muted">{t("kyc.registry_note")}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {reg.gstin && (
              <Card className="text-[15px]">
                <p className="font-semibold">GSTIN</p>
                <p>{reg.gstin.legal_name}</p>
                <p className="text-muted">{reg.gstin.trade_name}, {reg.gstin.state}</p>
                <Pill tone={reg.gstin.status === "Active" ? "good" : "bad"}>{reg.gstin.status}</Pill>
              </Card>
            )}
            {reg.udyam && (
              <Card className="text-[15px]">
                <p className="font-semibold">Udyam</p>
                <p>{reg.udyam.enterprise_name}</p>
                <p className="text-muted">{reg.udyam.enterprise_type}, {reg.udyam.city}</p>
              </Card>
            )}
          </div>
        </section>
      )}

      <section className="mt-5">
        <h2 className="mb-2 text-[17px] font-bold">{t("kyc.fields")}</h2>
        <ul className="space-y-2">
          {kcase.documents.map((d) => (
            <DocDetail key={d.id} caseId={kcase.id} doc={d} token={j.customerToken!} />
          ))}
        </ul>
        {kcase.reference_date && <p className="mt-2 text-[14px] text-muted">{t("kyc.reference", { date: fmtDate(kcase.reference_date, j.lang) })}</p>}
      </section>

      <div className="mt-6 grid gap-2 sm:grid-cols-2">
        {decision === "action_required" ? (
          <>
            <Button onClick={() => nav("/kyc/upload")}>{t("kyc.reupload")}</Button>
            <Button variant="secondary" onClick={() => nav(`/orders/${j.orderId}`)}>{t("kyc.continue")}</Button>
          </>
        ) : (
          <>
            <Button onClick={() => nav(`/orders/${j.orderId}/confirmed`)}>{t("common.continue")}</Button>
            <Link to="/kyc/upload" className="inline-flex min-h-12 items-center justify-center font-semibold text-brand-ink underline-offset-4 hover:underline">{t("kyc.reupload")}</Link>
          </>
        )}
      </div>
    </Shell>
  );
}
