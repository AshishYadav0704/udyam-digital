// Thin API client. The server recomputes every price and rule; the client never trusts its own numbers.
export class ApiError extends Error {
  status: number;
  detail: any;
  constructor(status: number, detail: any) {
    super(describe(status, detail));
    this.status = status;
    this.detail = detail;
  }
}

function describe(status: number, detail: any): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI/Pydantic validation errors: [{loc, msg}]
    return detail
      .map((d) => {
        const field = Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : "";
        return field ? `${String(field).replace(/_/g, " ")}: ${d.msg}` : d?.msg;
      })
      .filter(Boolean)
      .join("; ");
  }
  if (detail?.messages?.length) return detail.messages.join(" ");
  if (typeof detail?.detail === "string") return detail.detail;
  return `Request failed (${status})`;
}

type Opts = { method?: string; body?: any; token?: string | null; sessionToken?: string | null; form?: FormData; signal?: AbortSignal };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  if (opts.sessionToken) headers["X-Session-Token"] = opts.sessionToken;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body, signal: opts.signal });
  } catch (e: any) {
    if (e?.name === "AbortError") throw e;
    throw new ApiError(0, "network");
  }
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data ?? res.statusText);
  return data as T;
}

function safeJson(t: string) {
  try {
    return JSON.parse(t);
  } catch {
    return t;
  }
}

export async function fetchImage(path: string, token: string): Promise<string> {
  const res = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new ApiError(res.status, "image unavailable");
  return URL.createObjectURL(await res.blob());
}

export const inr = (x: number | null | undefined, paise = true) => {
  if (x === null || x === undefined || Number.isNaN(x)) return "-";
  const opts: Intl.NumberFormatOptions = { maximumFractionDigits: paise ? 2 : 0, minimumFractionDigits: 0 };
  return "₹" + new Intl.NumberFormat("en-IN", opts).format(x);
};

export const fmtDate = (iso: string | null | undefined, lang: string) => {
  if (!iso) return "-";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", year: "numeric" });
};
