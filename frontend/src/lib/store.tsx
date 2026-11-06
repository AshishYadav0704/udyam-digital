// Journey state: survives refreshes within the tab (sessionStorage), never written to localStorage.
// Tokens live here only for the prototype; production would use httpOnly, SameSite=strict cookies.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { ChatMessage, Chip, Recommendation } from "./types";
import { translate, type Lang } from "../i18n/strings";

export type Selection = { items: Record<string, number>; pkg: "recommended" | "starter" | "custom" };

export type Journey = {
  lang: Lang;
  sessionId: string | null;
  sessionToken: string | null;
  chat: ChatMessage[];
  expecting: string | null;
  chips: Chip[];
  multiSelect: boolean;
  advisorState: string | null;
  llmProvider: string;
  recommendation: Recommendation | null;
  selection: Selection | null;
  savedQuoteId: string | null;
  customerToken: string | null;
  customer: { id: string; name: string | null; mobile: string } | null;
  orderId: string | null;
  caseId: string | null;
  staffToken: string | null;
  staff: { id: string; name: string; role: string; partner_code: string | null } | null;
  attribution: { source: string; partner_code: string | null } | null;
};

const EMPTY: Journey = {
  lang: "en",
  sessionId: null,
  sessionToken: null,
  chat: [],
  expecting: null,
  chips: [],
  multiSelect: false,
  advisorState: null,
  llmProvider: "offline",
  recommendation: null,
  selection: null,
  savedQuoteId: null,
  customerToken: null,
  customer: null,
  orderId: null,
  caseId: null,
  staffToken: null,
  staff: null,
  attribution: null,
};

const KEY = "accel-journey-v1";

function load(): Journey {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) return { ...EMPTY, ...JSON.parse(raw) };
  } catch {
    /* storage unavailable: start fresh */
  }
  const urlLang = new URLSearchParams(window.location.search).get("lang");
  return { ...EMPTY, lang: urlLang === "hi" ? "hi" : "en" };
}

type Ctx = {
  j: Journey;
  set: (patch: Partial<Journey> | ((j: Journey) => Partial<Journey>)) => void;
  resetAdvisor: () => void;
  logoutCustomer: () => void;
  logoutStaff: () => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
};

const JourneyContext = createContext<Ctx | null>(null);

export function JourneyProvider({ children, initial }: { children: ReactNode; initial?: Partial<Journey> }) {
  const [j, setJ] = useState<Journey>(() => ({ ...load(), ...(initial || {}) }));

  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(j));
    } catch {
      /* ignore quota / private mode */
    }
    document.documentElement.lang = j.lang === "hi" ? "hi" : "en";
  }, [j]);

  const set = useCallback((patch: Partial<Journey> | ((j: Journey) => Partial<Journey>)) => {
    setJ((prev) => ({ ...prev, ...(typeof patch === "function" ? patch(prev) : patch) }));
  }, []);

  const resetAdvisor = useCallback(() => {
    setJ((prev) => ({
      ...prev,
      sessionId: null,
      sessionToken: null,
      chat: [],
      expecting: null,
      chips: [],
      multiSelect: false,
      advisorState: null,
      recommendation: null,
      selection: null,
      savedQuoteId: null,
    }));
  }, []);

  const logoutCustomer = useCallback(() => set({ customerToken: null, customer: null, orderId: null, caseId: null }), [set]);
  const logoutStaff = useCallback(() => set({ staffToken: null, staff: null }), [set]);
  const t = useCallback((key: string, vars?: Record<string, string | number>) => translate(j.lang, key, vars), [j.lang]);

  const value = useMemo(() => ({ j, set, resetAdvisor, logoutCustomer, logoutStaff, t }), [j, set, resetAdvisor, logoutCustomer, logoutStaff, t]);
  return <JourneyContext.Provider value={value}>{children}</JourneyContext.Provider>;
}

export function useJourney() {
  const ctx = useContext(JourneyContext);
  if (!ctx) throw new Error("useJourney outside provider");
  return ctx;
}

/** Selection helpers: the plan's recommended items as a qty map, add-ons default to 0. */
export function selectionFromRecommendation(rec: Recommendation, pkg: Selection["pkg"] = "recommended"): Selection {
  const items: Record<string, number> = {};
  for (const it of rec.items || []) items[it.product_id] = pkg === "starter" && !(rec.starter_ids || []).includes(it.product_id) ? 0 : it.qty;
  for (const it of rec.add_ons || []) items[it.product_id] = 0;
  return { items, pkg };
}

export function selectedLines(sel: Selection | null) {
  if (!sel) return [];
  return Object.entries(sel.items)
    .filter(([, q]) => q > 0)
    .map(([product_id, qty]) => ({ product_id, qty }));
}
