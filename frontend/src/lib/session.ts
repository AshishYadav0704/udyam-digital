import { api } from "./api";
import { selectionFromRecommendation, type Journey } from "./store";
import type { AdvisorTurn } from "./types";

type Setter = (patch: Partial<Journey> | ((j: Journey) => Partial<Journey>)) => void;

export async function createSession(j: Journey, set: Setter) {
  const r = await api<AdvisorTurn & { session_token: string }>("/api/advisor/sessions", {
    body: { language: j.lang, source: j.attribution?.source || "Website", partner_code: j.attribution?.partner_code || null },
  });
  set({
    sessionId: r.session_id,
    sessionToken: r.session_token,
    chat: r.messages,
    expecting: r.expecting,
    chips: r.chips,
    multiSelect: r.multi_select,
    advisorState: r.state,
    recommendation: null,
    selection: null,
  });
  return r;
}

/** Apply an advisor turn to the journey (messages, chips, recommendation). */
export function applyTurn(r: AdvisorTurn, set: Setter) {
  set((prev) => ({
    chat: [...prev.chat, ...r.messages],
    expecting: r.expecting,
    chips: r.chips || [],
    multiSelect: r.multi_select,
    advisorState: r.state,
    lang: r.language || prev.lang,
    llmProvider: r.llm?.provider || prev.llmProvider,
    ...(r.recommendation && r.recommendation.status === "ok"
      ? { recommendation: r.recommendation, selection: selectionFromRecommendation(r.recommendation) }
      : {}),
  }));
}
