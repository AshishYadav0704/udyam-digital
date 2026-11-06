import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Money, Notice, SkeletonCard, SourceBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { useJourney } from "../../lib/store";
import { OpsShell, Td, TableWrap, Th } from "./OpsShell";

type Kpis = { leads: number; activated: number; activation_rate: number; cac: number; mrr: number; avg_bundle: number; churn_6m: number; days_to_activate: number; status_calls: number };
type OverviewData = {
  baseline: { period: string; overall: Kpis; funnel: { stage: string; count: number; conversion: number | null }[]; segments: Record<string, Kpis>; channels: Record<string, Kpis> };
  live: { funnel: { stage: string; count: number }[]; orders: number; pending_kyc: number; kyc_review: number | null; stuck_orders: number; activated_mrr: number; pipeline_mrr: number; open_escalations: number | null };
  lead_routes: Record<string, number>;
  model: { available: boolean };
};

const SEG: Record<string, string> = { micro: "Micro retail & services", prof: "Professional practices", multi: "Multi-site", mfg: "Manufacturing" };
const ROUTE: Record<string, string> = { self_serve: "Self-serve", assisted: "Assisted digital", partner: "Channel partner", sales: "Field / key-account sales", kyc_review: "KYC reviewer" };
const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "-" : `${(x * 100).toFixed(d)}%`);

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-white px-4 py-3 shadow-[var(--shadow-card)]">
      <p className="text-[14px] text-muted">{label}</p>
      <p className="num mt-0.5 text-[26px] leading-tight font-extrabold">{value}</p>
      {sub && <p className="text-[13px] text-muted">{sub}</p>}
    </div>
  );
}

function FunnelChart({ data }: { data: { stage: string; count: number; conversion: number | null }[] }) {
  const rows = data.map((d) => ({ ...d, label: d.conversion === null ? d.count.toLocaleString("en-IN") : `${d.count.toLocaleString("en-IN")} (${pct(d.conversion, 0)})` }));
  // the stage with the lowest pass rate is the one the product attacks first; it is the only bar in the accent colour
  const worst = rows.reduce((w, d, i) => (d.conversion !== null && (w < 0 || d.conversion < (rows[w].conversion ?? 1)) ? i : w), -1);
  return (
    <div className="h-[260px] w-full" role="img" aria-label={"Historic funnel: " + data.map((d) => `${d.stage} ${d.count}`).join(", ")}>
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 96, bottom: 4, left: 8 }} barCategoryGap={10}>
          <CartesianGrid horizontal={false} stroke="#e2e4e9" />
          <XAxis type="number" tick={{ fill: "#5f6673", fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey="stage" width={118} tick={{ fill: "#1e2229", fontSize: 13 }} axisLine={false} tickLine={false} />
          <Tooltip cursor={{ fill: "#f5f6f8" }} formatter={(v: number) => [v.toLocaleString("en-IN"), "Leads"]} contentStyle={{ borderRadius: 8, borderColor: "#e2e4e9" }} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {rows.map((_, i) => (
              <Cell key={i} fill={i === worst ? "#d81921" : "#4b5260"} />
            ))}
            <LabelList dataKey="label" position="right" fill="#1e2229" fontSize={12.5} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function OpsOverview() {
  const { j, logoutStaff } = useJourney();
  const [d, setD] = useState<OverviewData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api<OverviewData>("/api/backoffice/overview", { token: j.staffToken })
      .then(setD)
      .catch((e) => {
        if (e.status === 401) logoutStaff();
        setErr(e.message);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j.staffToken]);
  const isPartner = j.staff?.role === "partner";
  return (
    <OpsShell title="Overview">
      {err && <Notice tone="error">{err}</Notice>}
      {!d && !err && (
        <div className="grid gap-3 lg:grid-cols-2">
          <SkeletonCard lines={3} label="Loading" />
          <SkeletonCard lines={3} />
        </div>
      )}
      {d && (
        <div className="space-y-6">
          <section>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[18px] font-bold">Today's work</h2>
              <SourceBadge kind="live" />
            </div>
            <p className="mb-3 text-[14px] text-muted">Counts from orders, KYC cases and call-backs created in this prototype{isPartner ? `, scoped to partner ${j.staff?.partner_code}` : ""}.</p>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Orders awaiting KYC" value={d.live.pending_kyc} />
              {d.live.kyc_review !== null && <Stat label="KYC cases for a reviewer" value={d.live.kyc_review} />}
              <Stat label="Orders stuck over 48 h" value={d.live.stuck_orders} />
              {d.live.open_escalations !== null && <Stat label="Open call-back requests" value={d.live.open_escalations} />}
              <Stat label="Activated monthly revenue" value={<Money value={d.live.activated_mrr} paise={false} />} />
              <Stat label="Pipeline monthly revenue" value={<Money value={d.live.pipeline_mrr} paise={false} />} sub="Ordered, not yet active" />
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <Card>
                <h3 className="mb-2 font-bold">Digital journey, live</h3>
                <ol className="space-y-1.5">
                  {d.live.funnel.map((f, i) => (
                    <li key={f.stage} className="flex items-center justify-between gap-3 text-[15px]">
                      <span className="flex items-center gap-2">
                        <span className="num grid size-6 place-items-center rounded-full bg-mist text-[13px] font-bold">{i + 1}</span>
                        {f.stage}
                      </span>
                      <span className="num font-semibold">{f.count}</span>
                    </li>
                  ))}
                </ol>
              </Card>
              <Card>
                <h3 className="mb-2 font-bold">Where leads are routed</h3>
                {Object.keys(d.lead_routes).length === 0 ? (
                  <p className="text-muted">No leads yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {Object.entries(d.lead_routes)
                      .sort((a, b) => b[1] - a[1])
                      .map(([r, n]) => {
                        const total = Object.values(d.lead_routes).reduce((a, b) => a + b, 0);
                        return (
                          <li key={r} className="text-[15px]">
                            <div className="flex justify-between">
                              <span>{ROUTE[r] || r}</span>
                              <span className="num font-semibold">{n}</span>
                            </div>
                            <div className="mt-1 h-2 rounded-full bg-mist" role="presentation">
                              <div className="h-2 rounded-full bg-ink-3" style={{ width: `${Math.max(1.5, (n / total) * 100)}%` }} />
                            </div>
                          </li>
                        );
                      })}
                  </ul>
                )}
                {!d.model.available && <p className="mt-2 text-[14px] text-amber">Propensity model not loaded - leads are routed by rules only.</p>}
              </Card>
            </div>
          </section>

          <section>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[18px] font-bold">Historic baseline</h2>
              <SourceBadge kind="synthetic">Synthetic case data</SourceBadge>
            </div>
            <p className="mb-3 text-[14px] text-muted">{d.baseline.period}. Case-study data, not real Airtel or Accel performance.</p>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              <Stat label="Lead to activation" value={pct(d.baseline.overall.activation_rate, 2)} sub={`${d.baseline.overall.activated} of ${d.baseline.overall.leads.toLocaleString("en-IN")}`} />
              <Stat label="Blended CAC" value={<Money value={d.baseline.overall.cac} paise={false} />} sub="Total spend / activations" />
              <Stat label="Days to activate" value={d.baseline.overall.days_to_activate.toFixed(1)} />
              <Stat label="Status calls per customer" value={d.baseline.overall.status_calls.toFixed(1)} />
              <Stat label="6-month churn" value={pct(d.baseline.overall.churn_6m)} />
            </div>
            <Card className="mt-4">
              <h3 className="font-bold">Leads reaching each stage</h3>
              <p className="mb-1 text-[14px] text-muted">Bracket = share of the previous stage that moved on. Red marks the lowest pass rate.</p>
              <FunnelChart data={d.baseline.funnel} />
            </Card>
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <TableWrap>
                <table className="w-full">
                  <caption className="px-3 pt-3 text-left font-bold">By segment</caption>
                  <thead>
                    <tr>
                      <Th>Segment</Th>
                      <Th className="text-right">Leads</Th>
                      <Th className="text-right">Activation</Th>
                      <Th className="text-right">CAC</Th>
                      <Th className="text-right">Avg bundle / mo</Th>
                      <Th className="text-right">Churn 6m</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(d.baseline.segments).map(([k, s]) => (
                      <tr key={k}>
                        <Td>{SEG[k] || k}</Td>
                        <Td className="num text-right">{s.leads.toLocaleString("en-IN")}</Td>
                        <Td className="num text-right">{pct(s.activation_rate)}</Td>
                        <Td className="text-right"><Money value={s.cac} paise={false} /></Td>
                        <Td className="text-right"><Money value={s.avg_bundle} paise={false} /></Td>
                        <Td className="num text-right">{pct(s.churn_6m)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
              <TableWrap>
                <table className="w-full">
                  <caption className="px-3 pt-3 text-left font-bold">By lead source</caption>
                  <thead>
                    <tr>
                      <Th>Source</Th>
                      <Th className="text-right">Leads</Th>
                      <Th className="text-right">Activation</Th>
                      <Th className="text-right">CAC</Th>
                      <Th className="text-right">Churn 6m</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(d.baseline.channels)
                      .sort((a, b) => a[1].cac - b[1].cac)
                      .map(([k, s]) => (
                        <tr key={k}>
                          <Td>{k}</Td>
                          <Td className="num text-right">{s.leads.toLocaleString("en-IN")}</Td>
                          <Td className="num text-right">{pct(s.activation_rate)}</Td>
                          <Td className="text-right"><Money value={s.cac} paise={false} /></Td>
                          <Td className="num text-right">{pct(s.churn_6m)}</Td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </TableWrap>
            </div>
          </section>
        </div>
      )}
    </OpsShell>
  );
}
