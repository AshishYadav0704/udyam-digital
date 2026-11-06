import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button, EmptyState, Input, Money, Notice, Pill, Select, SkeletonCard, SourceBadge, Textarea } from "../../components/ui";
import { api } from "../../lib/api";
import { useJourney } from "../../lib/store";
import { OpsShell, Td, TableWrap, Th } from "./OpsShell";

type Activity = { at: string; by: string; status: string | null; assigned_to: string | null; note: string | null };
type Lead = {
  id: string;
  ref: string;
  origin: string;
  source: string;
  segment: string;
  business_type: string | null;
  business_name: string | null;
  city: string | null;
  city_tier: number | null;
  has_gstin: boolean | null;
  stage: string | null;
  drop_reason: string | null;
  propensity: number | null;
  band: string | null;
  route: string | null;
  route_label: string | null;
  reasons: string[];
  sla_hours: number | null;
  drivers: { factor: string; effect: "raises" | "lowers"; weight: number }[];
  status: string;
  assigned_to: string | null;
  partner_code: string | null;
  monthly_value: number | null;
  created_at: string | null;
  features?: Record<string, any>;
  activity?: Activity[];
};

const SEG: Record<string, string> = { micro: "Micro", prof: "Professional", multi: "Multi-site", mfg: "Manufacturing" };
const BAND_TONE: Record<string, "good" | "warn" | "neutral"> = { priority: "good", watch: "warn", standard: "neutral" };
const ROUTES = ["self_serve", "assisted", "partner", "sales", "kyc_review"];
const ROUTE: Record<string, string> = { self_serve: "Self-serve", assisted: "Assisted digital", partner: "Channel partner", sales: "Field / KAM sales", kyc_review: "KYC reviewer" };
const STATUSES = ["open", "contacted", "nurture", "won", "lost"];
const STATUS_TONE: Record<string, "neutral" | "good" | "warn" | "bad" | "brand"> = { open: "neutral", contacted: "brand", nurture: "warn", won: "good", lost: "bad" };
const when = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function LeadPanel({ id, onClose, onSaved }: { id: string; onClose: () => void; onSaved: (l: Lead) => void }) {
  const { j } = useJourney();
  const [l, setL] = useState<Lead | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [status, setStatus] = useState("open");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const load = () => {
    setL(null);
    setLoadErr(null);
    api<Lead>(`/api/backoffice/leads/${id}`, { token: j.staffToken })
      .then((r) => {
        setL(r);
        setStatus(r.status);
      })
      .catch((e) => setLoadErr((e as Error).message || "Could not load this lead."));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [id, j.staffToken]);
  useEffect(() => {
    // focus moves into the panel once when it opens; Escape closes it
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCloseRef.current();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const save = async (assignMe: boolean) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<Lead>(`/api/backoffice/leads/${id}/assign`, {
        token: j.staffToken,
        body: { status, ...(assignMe ? { assigned_to: j.staff?.name } : {}), ...(note.trim() ? { note: note.trim() } : {}) },
      });
      setL({ ...l!, ...r });
      onSaved(r);
      setNote("");
      setMsg({ tone: "success", text: "Follow-up saved." });
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="fixed inset-0 z-20 bg-ink/30" onClick={onClose} aria-hidden />
      <aside className="fixed inset-y-0 right-0 z-30 w-full max-w-md animate-page-in overflow-y-auto border-l border-line bg-white p-5 shadow-[var(--shadow-raised)]" aria-label="Lead detail" role="dialog" aria-modal="true">
        <button ref={closeRef} onClick={onClose} className="absolute top-3 right-3 grid size-10 place-items-center rounded-lg hover:bg-mist" aria-label="Close">
          <X className="size-5" />
        </button>
        {loadErr ? (
          <Notice tone="error" className="mt-10" action={<Button size="sm" variant="secondary" onClick={load}>Retry</Button>}>
            {loadErr}
          </Notice>
        ) : !l ? (
          <SkeletonCard lines={6} label="Loading lead" className="mt-10" />
        ) : (
          <div className="space-y-4">
            <div className="pr-10">
              <p className="num text-[14px] text-muted">{l.ref}</p>
              <h2 className="text-[20px] leading-tight font-bold">{l.business_name || l.business_type || "Lead"}</h2>
              <p className="text-ink-3">{[l.business_type, l.city, SEG[l.segment]].filter(Boolean).join(", ")}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {l.propensity !== null && <Pill tone={BAND_TONE[l.band || "standard"]}>{(l.propensity * 100).toFixed(1)}% likely, {l.band}</Pill>}
              {l.monthly_value ? <Pill>Plan <Money value={l.monthly_value} paise={false} />/mo</Pill> : null}
              {l.origin === "digital" ? <SourceBadge kind="live">Digital journey (live)</SourceBadge> : <SourceBadge kind="synthetic">Historic win-back (synthetic)</SourceBadge>}
            </div>
            <section className="rounded-xl border border-brand/30 bg-brand-soft/50 p-3.5">
              <h3 className="font-bold text-brand-ink">Recommended next step: {l.route_label}</h3>
              {l.sla_hours && <p className="text-[14px] text-ink-3">Respond within {l.sla_hours} h</p>}
              <ul className="mt-1 list-disc pl-5 text-[15px]">
                {l.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </section>
            {l.drivers.length > 0 && (
              <section>
                <h3 className="font-bold">What moves the score</h3>
                <p className="mb-1 text-[14px] text-muted">Logistic-regression contributions for this lead (standardised feature x coefficient). The score orders the queue; it never changes price or eligibility.</p>
                <ul className="space-y-1 text-[15px]">
                  {l.drivers.map((d) => (
                    <li key={d.factor} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5">
                        {d.effect === "raises" ? <ArrowUpRight className="size-4 text-leaf" aria-label="raises" /> : <ArrowDownRight className="size-4 text-rust" aria-label="lowers" />}
                        {d.factor}
                      </span>
                      <span className="num text-muted">
                        {d.weight > 0 ? "+" : ""}
                        {d.weight.toFixed(2)}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {l.drop_reason && (
              <p className="rounded-lg bg-mist px-3 py-2 text-[15px]">
                Previously lost: <b>{l.drop_reason}</b> at {l.stage}
              </p>
            )}
            <section className="space-y-2.5 border-t border-line pt-3">
              <h3 className="font-bold">Log a follow-up</h3>
              <p className="text-[14px] text-muted">Assigned to: {l.assigned_to || "nobody yet"}</p>
              <label htmlFor="lead-status" className="block font-semibold">Outcome</label>
              <Select id="lead-status" value={status} onChange={(e) => setStatus(e.target.value)}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
              <label htmlFor="lead-note" className="block font-semibold">
                Note <span className="font-normal text-muted">(optional, kept in the audit trail)</span>
              </label>
              <Textarea id="lead-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} placeholder="e.g. Called; owner wants the quote on WhatsApp" />
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => save(true)} loading={busy}>
                  Assign to me and save
                </Button>
                <Button size="sm" variant="secondary" onClick={() => save(false)} disabled={busy}>
                  Save
                </Button>
              </div>
              {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
            </section>
            <section>
              <h3 className="mb-1 font-bold">History</h3>
              {l.activity && l.activity.length ? (
                <ol className="space-y-2 text-[15px]">
                  {l.activity.map((a, i) => (
                    <li key={i} className="rounded-lg border border-line px-3 py-2">
                      <p className="text-[14px] text-muted">
                        {when(a.at)}, {a.by}
                      </p>
                      <p>
                        {a.status && <Pill tone={STATUS_TONE[a.status] || "neutral"}>{a.status}</Pill>} {a.assigned_to && <span className="text-ink-3">assigned to {a.assigned_to}</span>}
                      </p>
                      {a.note && <p className="mt-0.5">{a.note}</p>}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-[15px] text-muted">No follow-ups yet.</p>
              )}
            </section>
          </div>
        )}
      </aside>
    </>
  );
}

const EMPTY_FILTERS = { origin: "", band: "", route: "", segment: "", status: "" };

export function OpsLeads() {
  const { j } = useJourney();
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [data, setData] = useState<{ total: number; leads: Lead[]; bands: Record<string, number>; routes: Record<string, number> } | null>(null);
  const [page, setPage] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const PAGE = 25;
  useEffect(() => {
    const h = setTimeout(() => {
      setPage(0);
      setQuery(search.trim());
    }, 300);
    return () => clearTimeout(h);
  }, [search]);
  useEffect(() => {
    const q = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
    Object.entries(filters).forEach(([k, v]) => v && q.set(k, v));
    if (query) q.set("q", query);
    setData(null);
    setErr(null);
    api(`/api/backoffice/leads?${q}`, { token: j.staffToken })
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [filters, query, page, j.staffToken]);
  const setF = (k: string, v: string) => {
    setPage(0);
    setFilters({ ...filters, [k]: v });
  };
  const anyFilter = !!query || Object.values(filters).some(Boolean);
  return (
    <OpsShell title="Leads">
      <p className="mb-3 max-w-3xl text-[15px] text-ink-3">
        Sorted by conversion propensity. Digital leads come from the advisor (live); win-back leads are June leads from the synthetic case data, lost for a reason the digital journey removes. Scores rank who to call first; they never change price or eligibility.
      </p>
      <div className="mb-3 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-end">
        <div className="relative col-span-2 sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input aria-label="Search leads" placeholder="Search reference, business or city" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
        <div className="sm:w-44">
          <Select aria-label="Origin" value={filters.origin} onChange={(e) => setF("origin", e.target.value)}>
            <option value="">All origins</option>
            <option value="digital">Digital journey</option>
            <option value="historic_winback">Historic win-back</option>
          </Select>
        </div>
        <div className="sm:w-40">
          <Select aria-label="Band" value={filters.band} onChange={(e) => setF("band", e.target.value)}>
            <option value="">All bands</option>
            <option value="priority">Priority</option>
            <option value="watch">Watch</option>
            <option value="standard">Standard</option>
          </Select>
        </div>
        <div className="sm:w-48">
          <Select aria-label="Route" value={filters.route} onChange={(e) => setF("route", e.target.value)}>
            <option value="">All routes</option>
            {ROUTES.map((r) => (
              <option key={r} value={r}>
                {ROUTE[r]}
              </option>
            ))}
          </Select>
        </div>
        <div className="sm:w-44">
          <Select aria-label="Segment" value={filters.segment} onChange={(e) => setF("segment", e.target.value)}>
            <option value="">All segments</option>
            {Object.entries(SEG).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </div>
        <div className="sm:w-40">
          <Select aria-label="Status" value={filters.status} onChange={(e) => setF("status", e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        {anyFilter && (
          <Button
            size="sm"
            variant="ghost"
            className="min-h-12"
            onClick={() => {
              setFilters(EMPTY_FILTERS);
              setSearch("");
              setQuery("");
              setPage(0);
            }}
          >
            Clear filters
          </Button>
        )}
      </div>
      {err && <Notice tone="error">{err}</Notice>}
      {!data && !err && <SkeletonCard lines={8} label="Loading leads" />}
      {data && (
        <>
          <p className="mb-2 text-[14px] text-muted" aria-live="polite">
            {data.total.toLocaleString("en-IN")} leads.{" "}
            {Object.entries(data.bands)
              .filter(([k]) => k !== "null")
              .map(([k, v]) => `${v} ${k}`)
              .join(", ")}
          </p>
          {data.leads.length === 0 ? (
            <EmptyState title="No leads match these filters" icon={<Search className="size-5" aria-hidden />}>
              Try a different search or clear the filters.
            </EmptyState>
          ) : (
            <TableWrap>
              <table className="w-full">
                <thead>
                  <tr>
                    <Th>Lead</Th>
                    <Th>Business</Th>
                    <Th>Segment</Th>
                    <Th className="text-right">Propensity</Th>
                    <Th>Next step</Th>
                    <Th>Status</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.leads.map((l) => (
                    <tr key={l.id} className={clsx("cursor-pointer transition-colors hover:bg-mist", open === l.id && "bg-brand-soft/60")} onClick={() => setOpen(l.id)}>
                      <Td>
                        <button
                          className="num -mx-1 inline-flex min-h-10 items-center rounded px-1 text-left font-semibold text-brand-ink underline-offset-4 hover:underline"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpen(l.id);
                          }}
                        >
                          {l.ref}
                        </button>
                        <span className="block text-[13px] text-muted">{l.origin === "digital" ? "Digital (live)" : "Win-back (synthetic)"}</span>
                      </Td>
                      <Td>
                        {l.business_type || "-"}
                        <span className="block text-[13px] text-muted">
                          {l.city}
                          {l.has_gstin ? ", GSTIN" : ""}
                        </span>
                      </Td>
                      <Td>{SEG[l.segment] || l.segment}</Td>
                      <Td className="text-right">
                        {l.propensity !== null ? (
                          <>
                            <span className="num font-semibold">{(l.propensity * 100).toFixed(1)}%</span>
                            <span className="block">
                              <Pill tone={BAND_TONE[l.band || "standard"]}>{l.band}</Pill>
                            </span>
                          </>
                        ) : (
                          "-"
                        )}
                      </Td>
                      <Td>
                        {ROUTE[l.route || ""] || l.route_label || "-"}
                        {l.sla_hours && <span className="block text-[13px] text-muted">within {l.sla_hours} h</span>}
                      </Td>
                      <Td>
                        <Pill tone={STATUS_TONE[l.status] || "neutral"}>{l.status}</Pill>
                        {l.assigned_to && <span className="block text-[13px] text-muted">{l.assigned_to}</span>}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          )}
          <div className="mt-3 flex items-center gap-2">
            <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>
              Previous
            </Button>
            <span className="text-[14px] text-muted">
              Page {page + 1} of {Math.max(1, Math.ceil(data.total / PAGE))}
            </span>
            <Button size="sm" variant="secondary" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>
              Next
            </Button>
          </div>
        </>
      )}
      {open && <LeadPanel id={open} onClose={() => setOpen(null)} onSaved={(r) => setData((d) => (d ? { ...d, leads: d.leads.map((x) => (x.id === r.id ? { ...x, ...r } : x)) } : d))} />}
    </OpsShell>
  );
}
