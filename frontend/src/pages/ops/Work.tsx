import clsx from "clsx";
import { ClipboardCheck, Eye, FastForward, Phone, ScrollText, Truck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Button, Card, EmptyState, Money, Notice, OptionRow, Pill, Select, SkeletonCard, SourceBadge, Textarea } from "../../components/ui";
import { api, fetchImage } from "../../lib/api";
import { useJourney } from "../../lib/store";
import type { KycCase, KycDoc } from "../../lib/types";
import { OpsShell, Td, TableWrap, Th } from "./OpsShell";

const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "-");
const waiting = (iso: string | null | undefined) => {
  if (!iso) return "-";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return mins < 60 ? `${mins} min` : mins < 48 * 60 ? `${Math.round(mins / 60)} h` : `${Math.round(mins / 1440)} days`;
};

function useStaffGet<T>(path: string, deps: unknown[] = []) {
  const { j, logoutStaff } = useJourney();
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const reload = () => {
    setErr(null);
    api<T>(path, { token: j.staffToken })
      .then(setData)
      .catch((e) => {
        if (e.status === 401) logoutStaff();
        setErr(e.message);
      });
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(reload, [path, j.staffToken, ...deps]);
  return { data, err, reload, setData };
}

// ------------------------------------------------------------------ KYC queue
export function OpsKycQueue() {
  const { data, err } = useStaffGet<{ cases: { case_id: string; status: string; business: string; gstin: string | null; udyam: string | null; findings: string[]; updated_at: string | null }[] }>("/api/backoffice/kyc-queue");
  return (
    <OpsShell title="KYC queue">
      <p className="mb-3 max-w-3xl text-[15px] text-ink-3">Cases the automated checks could not clear, oldest first. Identifiers are masked; opening a document is recorded in the audit log.</p>
      {err && <Notice tone="error">{err}</Notice>}
      {!data && !err && <SkeletonCard lines={4} label="Loading" />}
      {data && data.cases.length === 0 && (
        <EmptyState title="Nothing waiting for a reviewer" icon={<ClipboardCheck className="size-5" aria-hidden />}>
          Cases appear here when a document needs a person: a mismatch, an unreadable read or a registry problem.
        </EmptyState>
      )}
      {data && data.cases.length > 0 && (
        <>
        <div className="mb-2 flex flex-wrap gap-2 text-[14px]">
          <Pill tone="warn">{data.cases.filter((c) => c.status === "manual_review").length} for a reviewer</Pill>
          <Pill>{data.cases.filter((c) => c.status === "action_required").length} waiting on the customer</Pill>
        </div>
        <TableWrap>
          <table className="w-full">
            <thead>
              <tr>
                <Th>Business</Th>
                <Th>Status</Th>
                <Th>Flags</Th>
                <Th>Waiting</Th>
              </tr>
            </thead>
            <tbody>
              {data.cases.map((c) => (
                <tr key={c.case_id} className="hover:bg-mist">
                  <Td>
                    <Link to={`/ops/kyc/${c.case_id}`} className="inline-flex min-h-10 items-center font-semibold text-brand-ink underline-offset-4 hover:underline">
                      {c.business}
                    </Link>
                    <span className="num block text-[13px] text-muted">{[c.gstin, c.udyam].filter(Boolean).join(", ")}</span>
                  </Td>
                  <Td>
                    <Pill tone={c.status === "manual_review" ? "warn" : "neutral"}>{c.status === "manual_review" ? "for a reviewer" : "waiting on customer"}</Pill>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {c.findings.map((f, i) => (
                        <Pill key={f + i}>{f.replace(/_/g, " ").toLowerCase()}</Pill>
                      ))}
                    </div>
                  </Td>
                  <Td className="whitespace-nowrap">
                    {waiting(c.updated_at)}
                    <span className="block text-[13px] text-muted">{when(c.updated_at)}</span>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
        </>
      )}
    </OpsShell>
  );
}

function StaffDoc({ caseId, doc }: { caseId: string; doc: KycDoc }) {
  const { j } = useJourney();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const show = async () => {
    setBusy(true);
    try {
      setUrl(await fetchImage(`/api/kyc/cases/${caseId}/documents/${doc.id}/image`, j.staffToken!));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-bold">{doc.label}</h3>
        {!url && (
          <Button size="sm" variant="secondary" onClick={show} loading={busy} className="shrink-0 whitespace-nowrap">
            <Eye className="size-4" aria-hidden /> Open document
          </Button>
        )}
      </div>
      <p className="text-[14px] text-muted">
        Detected {doc.doc_type.replace(/_/g, " ")}, blur {doc.quality.blur_score.toFixed(0)}
        {doc.quality.is_blurry ? " (blurred)" : ""}, {doc.quality.width}x{doc.quality.height}
        {Math.abs(doc.deskewed_by) >= 0.5 ? `, deskewed ${doc.deskewed_by.toFixed(1)}°` : ""}
      </p>
      {busy && !url && <span className="mt-2 block h-48 w-full animate-pulse rounded-md bg-mist" aria-hidden />}
      {url && <img src={url} alt={doc.label} className="mt-2 w-full rounded-md border border-line" />}
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[14px]">
        {Object.entries(doc.fields)
          .filter(([, f]) => f.value)
          .map(([k, f]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k.replace(/_/g, " ")}</dt>
              <dd className="num min-w-0 break-words">
                {f.value}{" "}
                {f.confidence < 0.8 ? (
                  <Pill tone="warn" className="text-[13px]">{Math.round(f.confidence * 100)}%, check</Pill>
                ) : (
                  <span className="text-[13px] text-muted">{Math.round(f.confidence * 100)}%{f.validated ? ", valid" : ""}</span>
                )}
              </dd>
            </div>
          ))}
      </dl>
    </Card>
  );
}

export function OpsKycCase() {
  const { id } = useParams();
  const { j } = useJourney();
  const { data, err, setData } = useStaffGet<KycCase>(`/api/backoffice/kyc/${id}`);
  const [decision, setDecision] = useState<"approve" | "reject" | "request_resubmission" | null>(null);   // no default: a person chooses
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!decision) {
      setMsg({ tone: "error", text: "Choose a decision first." });
      return;
    }
    if (note.trim().length < 3) {
      setMsg({ tone: "error", text: "Add a short note explaining the decision (it is shown in the audit trail)." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<{ status: string }>(`/api/backoffice/kyc/${id}/decision`, { token: j.staffToken, body: { decision, note: note.trim() } });
      setData((d) => (d ? { ...d, status: r.status, reviewer_note: note.trim() } : d));
      setMsg({ tone: "success", text: `Recorded: ${r.status.replace(/_/g, " ")}` });
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <OpsShell title="KYC case" actions={<Link to="/ops/kyc" className="inline-flex min-h-10 items-center text-[15px] font-semibold text-brand-ink underline-offset-4 hover:underline">Back to queue</Link>}>
      {err && <Notice tone="error">{err}</Notice>}
      {!data && !err && <SkeletonCard lines={6} label="Loading" />}
      {data && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="min-w-0 space-y-4">
            <Card>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-[20px] font-bold">{data.declaration?.business_name}</h2>
                <Pill tone={data.status === "verified" ? "good" : data.status === "rejected" ? "bad" : "warn"}>{data.status.replace(/_/g, " ")}</Pill>
              </div>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[15px]">
                <dt className="text-muted">Signatory</dt>
                <dd>{data.declaration?.signatory_name}</dd>
                <dt className="text-muted">GSTIN</dt>
                <dd className="num">{data.declaration?.gstin || "-"}</dd>
                <dt className="text-muted">Udyam</dt>
                <dd className="num">{data.declaration?.udyam_number || "-"}</dd>
                <dt className="text-muted">City</dt>
                <dd>{[data.declaration?.city, data.declaration?.state].filter(Boolean).join(", ") || "-"}</dd>
              </dl>
            </Card>
            <Card>
              <h3 className="mb-2 font-bold">Findings</h3>
              <ul className="space-y-2">
                {data.findings.map((f, i) => (
                  <li key={f.code + i} className="flex items-start justify-between gap-3 border-b border-line pb-2 last:border-0 last:pb-0">
                    <div>
                      <p className="num text-[13px] font-semibold text-muted">{f.code}</p>
                      <p className="text-[15px]">{f.text}</p>
                      {f.resolution && <p className="text-[14px] text-muted">{f.resolution}</p>}
                    </div>
                    <Pill tone={f.severity === "block" ? "bad" : f.severity === "info" ? "good" : "warn"}>{f.severity}</Pill>
                  </li>
                ))}
              </ul>
            </Card>
            {(data.registry?.gstin || data.registry?.udyam) && (
              <Card>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-bold">Registry check</h3>
                  <SourceBadge kind="synthetic">Mock registry, synthetic data - not a government API</SourceBadge>
                </div>
                <div className="mt-2 grid gap-3 md:grid-cols-2">
                  {(["gstin", "udyam"] as const)
                    .filter((k) => data.registry?.[k])
                    .map((k) => (
                      <dl key={k} className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-lg bg-mist p-3 text-[14px]">
                        <dt className="col-span-2 font-semibold">{k === "gstin" ? "GST registry" : "Udyam registry"}</dt>
                        {Object.entries(data.registry[k] as Record<string, string>)
                          .filter(([f]) => f !== "source")
                          .map(([f, v]) => (
                            <div key={f} className="contents">
                              <dt className="text-muted">{f.replace(/_/g, " ")}</dt>
                              <dd className="min-w-0 break-words">{String(v)}</dd>
                            </div>
                          ))}
                      </dl>
                    ))}
                </div>
              </Card>
            )}
            <div className="grid gap-4 2xl:grid-cols-2">
              {data.documents.map((d) => (
                <StaffDoc key={d.id} caseId={data.id} doc={d} />
              ))}
            </div>
          </div>
          <form onSubmit={submit} className="h-fit space-y-3 rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)] xl:sticky xl:top-5">
            <h3 className="font-bold">Decision</h3>
            <fieldset className="space-y-2">
              <legend className="sr-only">Decision</legend>
              {(
                [
                  ["approve", "Approve - details verified"],
                  ["request_resubmission", "Ask the customer to resubmit"],
                  ["reject", "Reject application"],
                ] as const
              ).map(([v, label]) => (
                <OptionRow key={v} name="decision" checked={decision === v} onChange={() => setDecision(v)}>
                  {label}
                </OptionRow>
              ))}
            </fieldset>
            <label htmlFor="note" className="block font-semibold">Note for the audit trail</label>
            <Textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
            {data.reviewer_note && <p className="text-[14px] text-muted">Last note: {data.reviewer_note}</p>}
            {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
            <Button type="submit" block loading={busy}>Record decision</Button>
            <p className="text-[13px] text-muted">The model and OCR never approve or reject on their own; a reviewer records every manual decision.</p>
          </form>
        </div>
      )}
    </OpsShell>
  );
}

// ------------------------------------------------------------------ orders
type StaffOrder = { order_id: string; order_no: string; status: string; payment_status: string | null; monthly: number; business: string | null; city: string | null; route: string | null; stuck: boolean; last_update: string; partner_code: string | null };

export function OpsOrders() {
  const { j } = useJourney();
  const [stuck, setStuck] = useState(false);
  const { data, err, reload } = useStaffGet<{ orders: StaffOrder[] }>(`/api/backoffice/orders?stuck=${stuck}`, [stuck]);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const canAdvance = j.staff?.role === "sales" || j.staff?.role === "admin";
  const advance = async (id: string) => {
    setBusy(id);
    setMsg(null);
    try {
      await api(`/api/orders/${id}/advance`, { token: j.staffToken, method: "POST" });
      reload();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <OpsShell
      title="Orders"
      actions={
        <label className="flex min-h-10 cursor-pointer items-center gap-2 text-[15px]">
          <input type="checkbox" checked={stuck} onChange={(e) => setStuck(e.target.checked)} className="size-5 accent-[var(--color-brand)]" /> Only stuck over 48 h
        </label>
      }
    >
      {msg && <Notice tone="warn" className="mb-3">{msg}</Notice>}
      {err && <Notice tone="error">{err}</Notice>}
      {!data && !err && <SkeletonCard lines={4} label="Loading" />}
      {data && data.orders.length === 0 && (
        <EmptyState title={stuck ? "Nothing is stuck" : "No orders yet"} icon={<Truck className="size-5" aria-hidden />}>
          {stuck ? "Every open order has moved in the last 48 hours." : "Orders placed in the customer journey appear here."}
        </EmptyState>
      )}
      {data && data.orders.length > 0 && canAdvance && (
        <p className="mb-2 text-[14px] text-muted">"Simulate next milestone" stands in for the installation team's system, which this prototype does not connect to.</p>
      )}
      {data && data.orders.length > 0 && (
        <TableWrap>
          <table className="w-full">
            <thead>
              <tr>
                <Th>Order</Th>
                <Th>Business</Th>
                <Th>Status</Th>
                <Th className="text-right">Monthly</Th>
                <Th>Route</Th>
                <Th>Last update</Th>
                {canAdvance && <Th />}
              </tr>
            </thead>
            <tbody>
              {data.orders.map((o) => (
                <tr key={o.order_id} className={clsx(o.stuck && "bg-amber-soft/60")}>
                  <Td className="num font-semibold">{o.order_no}</Td>
                  <Td>
                    {o.business || "-"}
                    <span className="block text-[13px] text-muted">{o.city}{o.partner_code ? `, ${o.partner_code}` : ""}</span>
                  </Td>
                  <Td>
                    {o.status.replace(/_/g, " ")}
                    {o.payment_status === "failed" && <span className="block"><Pill tone="bad">payment failed</Pill></span>}
                    {o.stuck && <span className="block"><Pill tone="warn">stuck</Pill></span>}
                  </Td>
                  <Td className="text-right"><Money value={o.monthly} paise={false} /></Td>
                  <Td>{o.route?.replace(/_/g, " ") || "-"}</Td>
                  <Td className="whitespace-nowrap">{when(o.last_update)}</Td>
                  {canAdvance && (
                    <Td>
                      {o.status !== "active" && (
                        <Button size="sm" variant="quiet" onClick={() => advance(o.order_id)} loading={busy === o.order_id}>
                          <FastForward className="size-4" aria-hidden /> Simulate next milestone
                        </Button>
                      )}
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </OpsShell>
  );
}

// ------------------------------------------------------------------ partners
export function OpsPartners() {
  const { data, err } = useStaffGet<{ partners: { code: string; name: string; city: string; leads: Record<string, number>; lead_total: number; orders: number; mrr: number }[] }>("/api/backoffice/partners");
  return (
    <OpsShell title="Partners">
      <p className="mb-3 max-w-3xl text-[15px] text-ink-3">Partners see only leads and orders attributed to them (QR code or referral link). Win-back leads from cities not yet open online are routed here.</p>
      {err && <Notice tone="error">{err}</Notice>}
      {!data && !err && <SkeletonCard lines={4} label="Loading" />}
      {data && data.partners.length === 0 && <EmptyState title="No partners visible to you" />}
      {data && data.partners.length > 0 && (
        <TableWrap>
          <table className="w-full">
            <thead>
              <tr>
                <Th>Partner</Th>
                <Th>City</Th>
                <Th className="text-right">Leads</Th>
                <Th>By band</Th>
                <Th className="text-right">Orders</Th>
                <Th className="text-right">Monthly value</Th>
              </tr>
            </thead>
            <tbody>
              {data.partners.map((p) => (
                <tr key={p.code}>
                  <Td>
                    <span className="font-semibold">{p.name}</span>
                    <span className="num block text-[13px] text-muted">{p.code}</span>
                  </Td>
                  <Td>{p.city}</Td>
                  <Td className="num text-right">{p.lead_total}</Td>
                  <Td className="text-[14px]">{Object.entries(p.leads).map(([b, n]) => `${n} ${b}`).join(", ") || "-"}</Td>
                  <Td className="num text-right">{p.orders}</Td>
                  <Td className="text-right"><Money value={p.mrr} paise={false} /></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </OpsShell>
  );
}

// ------------------------------------------------------------------ call-backs (escalations)
type Esc = { id: string; reason: string; status: string; language: string; preferred_time: string | null; note: string | null; order_no: string | null; business: string | null; city: string | null; contact: string | null; assigned_to: string | null; created_at: string };

export function OpsCallbacks() {
  const { j } = useJourney();
  const { data, err, setData } = useStaffGet<{ escalations: Esc[] }>("/api/backoffice/escalations");
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const reveal = async (id: string) => {
    setBusy(id);
    setMsg(null);
    try {
      const r = await api<{ mobile: string }>(`/api/backoffice/escalations/${id}/reveal`, { token: j.staffToken, method: "POST" });
      setRevealed((m) => ({ ...m, [id]: r.mobile }));
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const update = async (id: string, status: string) => {
    try {
      const r = await api<{ id: string; status: string; assigned_to: string | null }>(`/api/backoffice/escalations/${id}`, { token: j.staffToken, body: { status, assigned_to: j.staff?.name } });
      setData((d) => (d ? { escalations: d.escalations.map((e) => (e.id === id ? { ...e, ...r } : e)) } : d));
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  return (
    <OpsShell title="Call-backs">
      <p className="mb-3 max-w-3xl text-[15px] text-ink-3">People who asked for a human. Numbers stay masked until you choose to call; each reveal is written to the audit log.</p>
      {msg && <Notice tone="warn" className="mb-3">{msg}</Notice>}
      {err && <Notice tone="error">{err}</Notice>}
      {!data && !err && <SkeletonCard lines={4} label="Loading" />}
      {data && data.escalations.length === 0 && (
        <EmptyState title="No call-back requests" icon={<Phone className="size-5" aria-hidden />}>
          Requests from the "Talk to a person" buttons in the customer journey appear here.
        </EmptyState>
      )}
      {data && data.escalations.length > 0 && (
        <TableWrap>
          <table className="w-full">
            <thead>
              <tr>
                <Th>Requested</Th>
                <Th>Customer</Th>
                <Th>Reason</Th>
                <Th>Call</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {data.escalations.map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap">
                    {when(e.created_at)}
                    <span className="block text-[13px] text-muted">{e.language === "hi" ? "Hindi" : "English"}{e.preferred_time ? `, ${e.preferred_time}` : ""}</span>
                  </Td>
                  <Td>
                    {e.business || "-"}
                    <span className="block text-[13px] text-muted">{[e.city, e.order_no].filter(Boolean).join(", ")}</span>
                  </Td>
                  <Td>
                    {e.reason.replace(/_/g, " ")}
                    {e.note && <span className="block max-w-xs text-[13px] text-muted">{e.note}</span>}
                  </Td>
                  <Td>
                    {revealed[e.id] ? (
                      <a href={`tel:${revealed[e.id]}`} className="num inline-flex min-h-10 items-center gap-1 font-semibold text-brand-ink underline"><Phone className="size-4" aria-hidden />{revealed[e.id]}</a>
                    ) : e.contact ? (
                      <Button size="sm" variant="secondary" onClick={() => reveal(e.id)} loading={busy === e.id}>
                        <span className="num">{e.contact}</span> Show
                      </Button>
                    ) : (
                      <span className="text-[14px] text-muted">No number given</span>
                    )}
                  </Td>
                  <Td>
                    <Select aria-label="Status" value={e.status} onChange={(ev) => update(e.id, ev.target.value)} className="min-h-10 min-w-36 text-[15px]">
                      <option value="open">open</option>
                      <option value="in_progress">in progress</option>
                      <option value="resolved">resolved</option>
                    </Select>
                    {e.assigned_to && <span className="block text-[13px] text-muted">{e.assigned_to}</span>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </OpsShell>
  );
}

// ------------------------------------------------------------------ audit
export function OpsAudit() {
  const { data, err } = useStaffGet<{ events: { at: string; actor_type: string; action: string; entity: string; details: Record<string, any> }[] }>("/api/backoffice/audit?limit=200");
  return (
    <OpsShell title="Audit log">
      <p className="mb-3 max-w-3xl text-[15px] text-ink-3">Who did what, newest first. Identifiers are never written here in full.</p>
      {err && <Notice tone="error">{err}</Notice>}
      {!data && !err && <SkeletonCard lines={6} label="Loading" />}
      {data && data.events.length === 0 && <EmptyState title="No events yet" icon={<ScrollText className="size-5" aria-hidden />} />}
      {data && data.events.length > 0 && (
        <TableWrap>
          <table className="w-full">
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Entity</Th>
                <Th>Details</Th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((a, i) => (
                <tr key={i}>
                  <Td className="whitespace-nowrap">{when(a.at)}</Td>
                  <Td>{a.actor_type}</Td>
                  <Td className="num">{a.action}</Td>
                  <Td>{a.entity}</Td>
                  <Td className="num max-w-md text-[13px] break-words text-muted">{JSON.stringify(a.details)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </OpsShell>
  );
}
