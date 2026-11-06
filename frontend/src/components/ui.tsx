import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Database, Info, Loader2, Minus, Plus, Radio, XCircle } from "lucide-react";
import { forwardRef, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { inr } from "../lib/api";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "quiet";
  loading?: boolean;
  block?: boolean;
  size?: "md" | "sm" | "lg";
};

export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "primary", loading, block, size = "md", className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-[background-color,border-color,color,box-shadow] duration-150 disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" && "min-h-10 px-3.5 text-[15px]",
        size === "md" && "min-h-12 px-5 text-[17px]",
        size === "lg" && "min-h-14 px-6 text-lg",
        block && "w-full",
        variant === "primary" && "bg-brand text-white shadow-[var(--shadow-card)] hover:bg-brand-2 active:bg-brand-2",
        variant === "secondary" && "border border-control bg-white text-ink hover:border-ink-3 hover:bg-mist",
        variant === "ghost" && "text-brand-ink underline-offset-4 hover:underline",
        variant === "quiet" && "bg-line/70 text-ink hover:bg-line",
        variant === "danger" && "border border-rust bg-white text-rust hover:bg-rust-soft",
        className,
      )}
      {...rest}
    >
      {loading && <Loader2 className="size-5 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

export function Field({ label, hint, error, children, htmlFor, optional }: { label: ReactNode; hint?: ReactNode; error?: string | null; children: ReactNode; htmlFor?: string; optional?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block font-semibold text-ink">
        {label}
        {optional && <span className="ml-1 font-normal text-muted">({optional})</span>}
      </label>
      {children}
      {hint && !error && <p className="text-[15px] text-muted">{hint}</p>}
      {error && (
        <p className="flex items-start gap-1.5 text-[15px] font-medium text-rust" role="alert">
          <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
        </p>
      )}
    </div>
  );
}

const inputCls =
  "w-full min-h-12 rounded-lg border border-control bg-white px-3.5 text-[17px] text-ink transition-colors placeholder:text-muted/70 hover:border-ink-3 focus:border-ink focus:outline-none disabled:bg-mist disabled:text-muted aria-[invalid=true]:border-rust aria-[invalid=true]:bg-rust-soft/30";

/** Lets a caller override the control's height, width or text size without two conflicting utilities. */
function controlCls(extra?: string) {
  if (!extra) return inputCls;
  const groups = [/^min-h-/, /^text-\[\d/, /^w-/];
  const ex = extra.split(/\s+/).filter(Boolean);
  const base = inputCls.split(/\s+/).filter((b) => !groups.some((g) => g.test(b) && ex.some((e) => g.test(e))));
  return [...base, ...ex].join(" ");
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={controlCls(className)} {...rest} />;
});

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={clsx(controlCls(className), "appearance-none bg-[length:20px] bg-[right_12px_center] bg-no-repeat pr-10")} style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%231e2229' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")` }} {...rest}>
      {children}
    </select>
  );
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={clsx(controlCls(clsx("min-h-24", className)), "py-2.5")} {...rest} />;
}

export function Checkbox({ checked, onChange, children, id, disabled }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; id?: string; disabled?: boolean }) {
  const auto = useId();
  const cid = id || auto;
  return (
    <label htmlFor={cid} className={clsx("flex min-h-11 cursor-pointer items-start gap-3 py-1", disabled && "cursor-not-allowed opacity-60")}>
      <input id={cid} type="checkbox" className="mt-1 size-5 shrink-0 accent-[var(--color-brand)]" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

/** A selectable row (radio-style). Used for payment methods, decisions, GST yes/no and call-back times. */
export function OptionRow({ checked, onChange, name, children, className, center }: { checked: boolean; onChange: () => void; name: string; children: ReactNode; className?: string; center?: boolean }) {
  return (
    <label
      className={clsx(
        "flex min-h-12 cursor-pointer items-center gap-3 rounded-lg border bg-white px-3.5 transition-colors",
        checked ? "border-brand bg-brand-soft/60 ring-1 ring-brand" : "border-control hover:border-ink-3",
        center && "justify-center text-center",
        className,
      )}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} className={clsx("size-4 shrink-0 accent-[var(--color-brand)]", center && "sr-only")} />
      <span className={clsx("min-w-0", checked && "font-semibold")}>{children}</span>
    </label>
  );
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx("relative inline-flex h-8 w-14 shrink-0 items-center rounded-full transition-colors duration-150 disabled:opacity-50", checked ? "bg-brand" : "bg-control/70")}
    >
      <span className={clsx("inline-block size-6 rounded-full bg-white shadow transition-transform duration-150", checked ? "translate-x-7" : "translate-x-1")} />
    </button>
  );
}

export function QtyStepper({ value, onChange, min = 0, max = 99, label }: { value: number; onChange: (v: number) => void; min?: number; max?: number; label: string }) {
  return (
    <div className="inline-flex items-center rounded-lg border border-control bg-white" role="group" aria-label={label}>
      <button type="button" className="grid size-11 place-items-center rounded-l-lg text-ink hover:bg-mist disabled:opacity-30" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min} aria-label={`${label}: -1`}>
        <Minus className="size-4" />
      </button>
      <span className="num w-9 text-center font-semibold" aria-live="polite">
        {value}
      </span>
      <button type="button" className="grid size-11 place-items-center rounded-r-lg text-ink hover:bg-mist disabled:opacity-30" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} aria-label={`${label}: +1`}>
        <Plus className="size-4" />
      </button>
    </div>
  );
}

const toneMap = {
  info: { cls: "border-line bg-white text-ink", Icon: Info },
  success: { cls: "border-leaf/30 bg-leaf-soft text-leaf", Icon: CheckCircle2 },
  warn: { cls: "border-amber/30 bg-amber-soft text-amber", Icon: AlertTriangle },
  error: { cls: "border-rust/30 bg-rust-soft text-rust", Icon: XCircle },
} as const;

export function Notice({ tone = "info", title, children, action, className }: { tone?: keyof typeof toneMap; title?: ReactNode; children?: ReactNode; action?: ReactNode; className?: string }) {
  const { cls, Icon } = toneMap[tone];
  return (
    <div className={clsx("flex animate-rise gap-3 rounded-xl border px-4 py-3", cls, className)} role={tone === "error" ? "alert" : "status"}>
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className="text-[15px] leading-snug text-ink">{children}</div>}
        {action && <div className="pt-1">{action}</div>}
      </div>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-muted" role="status">
      <Loader2 className="size-5 animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

/** Placeholder blocks while content loads (pulse is switched off under reduced motion). */
export function Skeleton({ className }: { className?: string }) {
  return <span className={clsx("block animate-pulse rounded-md bg-line/80", className)} aria-hidden />;
}

export function SkeletonCard({ lines = 3, label, className }: { lines?: number; label?: string; className?: string }) {
  return (
    <div className={clsx("space-y-3 rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)] sm:p-5", className)} role="status" aria-label={label}>
      <Skeleton className="h-5 w-2/5" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={clsx("h-4", i % 3 === 0 ? "w-full" : i % 3 === 1 ? "w-11/12" : "w-3/5")} />
      ))}
      {label && <span className="sr-only">{label}</span>}
    </div>
  );
}

export function Money({ value, paise = true, className, testId }: { value: number | null | undefined; paise?: boolean; className?: string; testId?: string }) {
  return (
    <span className={clsx("num", className)} data-testid={testId}>
      {inr(value, paise)}
    </span>
  );
}

export function Card({ children, className, as: As = "section" }: { children: ReactNode; className?: string; as?: any }) {
  return <As className={clsx("rounded-xl border border-line bg-white p-4 shadow-[var(--shadow-card)] sm:p-5", className)}>{children}</As>;
}

export function Stamp({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("stamp", className)}>{children}</div>;
}

export function EmptyState({ title, children, action, icon }: { title: string; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-white px-5 py-9 text-center">
      {icon && <div className="mx-auto mb-3 grid size-11 place-items-center rounded-full bg-mist text-ink-3">{icon}</div>}
      <p className="font-semibold text-ink">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-[46ch] text-muted">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Pill({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "bad" | "ink" | "brand"; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[14px] font-semibold whitespace-nowrap",
        tone === "neutral" && "bg-mist text-ink-3 ring-1 ring-line ring-inset",
        tone === "good" && "bg-leaf-soft text-leaf",
        tone === "warn" && "bg-amber-soft text-amber",
        tone === "bad" && "bg-rust-soft text-rust",
        tone === "ink" && "bg-ink text-white",
        tone === "brand" && "bg-brand-soft text-brand-ink",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Says where a number comes from: the running prototype, or the synthetic case-study data. */
export function SourceBadge({ kind, children }: { kind: "live" | "synthetic"; children?: ReactNode }) {
  return kind === "live" ? (
    <Pill tone="good" className="max-w-full whitespace-normal">
      <Radio className="size-3.5 shrink-0" aria-hidden /> {children || "Live prototype data"}
    </Pill>
  ) : (
    <Pill tone="neutral" className="max-w-full whitespace-normal">
      <Database className="size-3.5 shrink-0" aria-hidden /> {children || "Synthetic case data"}
    </Pill>
  );
}

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-4 space-y-1">
      <h1 className="text-[26px] leading-tight font-bold text-ink">{children}</h1>
      {sub && <p className="text-muted">{sub}</p>}
    </div>
  );
}
