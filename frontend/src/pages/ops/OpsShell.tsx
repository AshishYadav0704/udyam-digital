import clsx from "clsx";
import { ClipboardCheck, FlaskConical, Gauge, Handshake, LogOut, PhoneCall, ScrollText, Truck, Users } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import { BrandMark } from "../../components/Shell";
import { Button, Field, Input, Notice, Pill } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { useJourney } from "../../lib/store";

export const NAV = [
  { to: "/ops", label: "Overview", Icon: Gauge, roles: ["sales", "partner", "kyc_reviewer", "admin"], end: true },
  { to: "/ops/leads", label: "Leads", Icon: Users, roles: ["sales", "partner", "admin"] },
  { to: "/ops/kyc", label: "KYC queue", Icon: ClipboardCheck, roles: ["kyc_reviewer", "admin"] },
  { to: "/ops/orders", label: "Orders", Icon: Truck, roles: ["sales", "partner", "admin"] },
  { to: "/ops/partners", label: "Partners", Icon: Handshake, roles: ["sales", "partner", "admin"] },
  { to: "/ops/callbacks", label: "Call-backs", Icon: PhoneCall, roles: ["sales", "admin"] },
  { to: "/ops/audit", label: "Audit log", Icon: ScrollText, roles: ["admin"] },
];

const ROLE_LABEL: Record<string, string> = { sales: "Sales", partner: "Channel partner", kyc_reviewer: "KYC reviewer", admin: "Admin" };

export function OpsShell({ children, title, actions }: { children: ReactNode; title: string; actions?: ReactNode }) {
  const { j, logoutStaff } = useJourney();
  const loc = useLocation();
  if (!j.staffToken || !j.staff) return <Navigate to="/ops/login" replace state={{ from: loc.pathname }} />;
  const items = NAV.filter((n) => n.roles.includes(j.staff!.role));
  const link = ({ isActive }: { isActive: boolean }) =>
    clsx(
      "relative flex min-h-10 items-center gap-2.5 rounded-lg px-3 text-[15px] font-medium whitespace-nowrap transition-colors",
      isActive ? "bg-white/10 text-white before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:bg-brand" : "text-white/75 hover:bg-white/5 hover:text-white",
    );
  return (
    <div className="min-h-dvh bg-mist lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="on-dark relative bg-ink text-white lg:sticky lg:top-0 lg:h-dvh">
        <div className="flex items-center gap-2.5 px-4 py-3.5 lg:py-4">
          <BrandMark />
          <div className="leading-tight">
            <p className="font-bold">Accel Business</p>
            <p className="text-[13px] text-white/70">Back office</p>
          </div>
        </div>
        <nav aria-label="Back office" className="flex gap-1 overflow-x-auto px-3 pb-3 [scrollbar-width:thin] lg:flex-col lg:overflow-visible">
          {items.map(({ to, label, Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={link}>
              <Icon className="size-4.5 shrink-0" aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden border-t border-white/10 px-4 py-3 text-[14px] lg:absolute lg:bottom-0 lg:block lg:w-full">
          <p className="font-semibold">{j.staff.name}</p>
          <p className="text-white/70">
            {ROLE_LABEL[j.staff.role] || j.staff.role}
            {j.staff.partner_code ? ` (${j.staff.partner_code})` : ""}
          </p>
          <button onClick={logoutStaff} className="mt-1 inline-flex min-h-10 items-center gap-1.5 text-white/85 underline-offset-4 hover:underline">
            <LogOut className="size-4" aria-hidden /> Log out
          </button>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-white px-5 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[22px] font-bold">{title}</h1>
            <Pill tone="warn">
              <FlaskConical className="size-3.5" aria-hidden /> Prototype, demo accounts
            </Pill>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {actions}
            <span className="flex items-center text-[14px] text-muted lg:hidden">
              {j.staff.name}, {ROLE_LABEL[j.staff.role]}
              <button onClick={logoutStaff} className="ml-2 inline-flex min-h-10 items-center font-semibold text-brand-ink underline underline-offset-2">
                Log out
              </button>
            </span>
          </div>
        </header>
        <main className="p-5">
          <div key={loc.pathname} className="animate-page-in">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

const DEMO = [
  { email: "sales@accel.demo", role: "Sales" },
  { email: "partner@accel.demo", role: "Partner (PTN-LKO-01)" },
  { email: "kyc@accel.demo", role: "KYC reviewer" },
  { email: "admin@accel.demo", role: "Admin" },
];

export function OpsLogin() {
  const { set } = useJourney();
  const nav = useNavigate();
  const loc = useLocation() as any;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await api<{ token: string; user: any }>("/api/auth/staff/login", { body: { email, password } });
      set({ staffToken: r.token, staff: r.user });
      nav(loc.state?.from && loc.state.from !== "/ops/login" ? loc.state.from : "/ops", { replace: true });
    } catch (e) {
      setErr(e instanceof ApiError ? (e.status === 0 ? "Server not reachable." : e.status === 401 ? "Email or password is incorrect." : e.message) : "Login failed.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid min-h-dvh place-items-center bg-mist px-4">
      <div className="w-full max-w-sm">
        <div className="mb-5 flex items-center gap-2.5">
          <BrandMark />
          <div>
            <p className="font-bold">Accel Business</p>
            <p className="text-[14px] text-muted">Back office sign-in</p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-3 rounded-xl border border-line bg-white p-5 shadow-[var(--shadow-raised)]">
          <Field label="Work email" htmlFor="em">
            <Input id="em" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </Field>
          <Field label="Password" htmlFor="pw">
            <Input id="pw" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          {err && <Notice tone="error">{err}</Notice>}
          <Button type="submit" block loading={busy}>
            Sign in
          </Button>
        </form>
        <div className="mt-4 rounded-xl border border-dashed border-amber/60 bg-amber-soft/60 p-4 text-[15px]">
          <p className="font-semibold">Demo accounts (password demo1234)</p>
          <ul className="mt-2 space-y-1">
            {DEMO.map((d) => (
              <li key={d.email}>
                <button type="button" className="min-h-10 text-left underline-offset-4 hover:underline" onClick={() => { setEmail(d.email); setPassword("demo1234"); }}>
                  <span className="num">{d.email}</span> <span className="text-muted">- {d.role}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[14px] text-muted">Shown only in the prototype. Production uses SSO with MFA.</p>
        </div>
        <p className="mt-4 text-center">
          <Link to="/" className="inline-flex min-h-10 items-center font-semibold text-brand-ink underline-offset-4 hover:underline">
            Customer site
          </Link>
        </p>
      </div>
    </div>
  );
}

/** Small table primitives for dense back-office lists. */
export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return <th scope="col" className={clsx("border-b border-line bg-mist/60 px-3 py-2.5 text-left text-[14px] font-semibold whitespace-nowrap text-ink-3", className)}>{children}</th>;
}
export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={clsx("border-b border-line px-3 py-2.5 align-top text-[15px]", className)}>{children}</td>;
}
export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-[var(--shadow-card)]">{children}</div>;
}
