// Shapes returned by the FastAPI backend (subset the UI uses).
export type Chip = { value: string; label: string };

export type ChatMessage = { role: "assistant" | "user"; text: string; kind?: string; expecting?: string; gstin?: string };

export type QuoteLine = {
  product_id: string;
  name: string;
  category: string;
  unit: string;
  qty: number;
  unit_price: number;
  monthly: number;
  setup_unit: number;
  setup: number;
  min_contract_months: number;
  install_days: number;
  install_start_day: number;
  install_done_day: number;
};

export type Quote = {
  lines: QuoteLine[];
  monthly_subtotal: number;
  monthly_gst: number;
  monthly_total: number;
  setup_subtotal: number;
  setup_gst: number;
  setup_total: number;
  contract_months: number;
  contract_driver: string;
  total_contract_value: number;
  expected_activation_days: number;
  price_policy: string;
  gst_rate: number;
  valid_until: string;
  warnings: { code: string; product_id: string; params?: Record<string, any> }[];
  fingerprint: string;
};

export type PlanItem = {
  product_id: string;
  name: string;
  category: string;
  unit: string;
  unit_label: string;
  qty: number;
  unit_price: number;
  monthly: number;
  setup: number;
  min_contract_months: number;
  install_days: number;
  reason: string;
  need: string | null;
  share_of_similar: number | null;
  description: string;
  requires_gstin: boolean;
  reason_text: string;
};

export type Recommendation = {
  status: "ok" | "not_serviceable" | "needs_info";
  missing: string[];
  profile: Profile;
  notes: { code: string; text: string }[];
  items?: PlanItem[];
  add_ons?: PlanItem[];
  starter_ids?: string[];
  excluded?: { product_id: string; name: string; codes: string[]; text: string }[];
  quote?: Quote;
  starter_quote?: { monthly_subtotal: number; setup_subtotal: number; contract_months: number };
  explanation?: string;
  explanation_source?: "template" | "llm";
};

export type Profile = {
  business_name?: string | null;
  business_type?: string | null;
  segment?: "micro" | "prof" | "multi" | "mfg" | null;
  city?: string | null;
  city_tier?: 1 | 2 | 3 | null;
  state?: string | null;
  employees?: number | null;
  sites?: number | null;
  has_gstin?: boolean | null;
  gstin?: string | null;
  gstin_status?: string | null;
  needs?: string[];
  excluded_needs?: string[];
  monthly_spend?: number | null;
  budget?: number | null;
  language?: "en" | "hi";
};

export type AdvisorTurn = {
  session_id: string;
  language: "en" | "hi";
  messages: ChatMessage[];
  expecting: string | null;
  chips: Chip[];
  multi_select: boolean;
  profile: Profile;
  missing: string[];
  state: string;
  recommendation: Recommendation | null;
  llm?: { provider: string; used: boolean };
  escalated?: boolean;
  not_serviceable?: boolean;
};

export type TrackerStep = { stage: string; label: string; status: "done" | "current" | "upcoming"; at: string | null; expected: string | null };

export type OrderView = {
  order_id: string;
  order_no: string;
  status: string;
  payment_status: string | null;
  created_at: string;
  install_address: string;
  quote: Quote;
  profile: Profile;
  routing: { route: string; label: string; reasons: string[]; sla_hours: number } | null;
  kyc: { case_id: string; status: string } | null;
  tracker: {
    order_no: string;
    status: string;
    payment_status: string | null;
    steps: TrackerStep[];
    blockers: { stage: string; label: string; note: string | null; at: string }[];
    installations: { product_id: string; name: string; qty: number; expected: string }[];
    expected_activation: string | null;
    activated_at: string | null;
  };
};

export type KycField = { value: string | null; confidence: number; validated: boolean };
export type KycDoc = {
  id: string;
  slot: string;
  label: string;
  doc_type: string;
  quality: { width: number; height: number; blur_score: number; skew_degrees: number; is_blurry: boolean; is_low_resolution: boolean };
  deskewed_by: number;
  fields: Record<string, KycField>;
  uploaded_at: string | null;
};
export type KycFinding = { code: string; severity: "info" | "resubmit" | "review" | "block"; document: string | null; text: string; resolution?: string | null };
export type KycCase = {
  id: string;
  status: string;
  decision: "verified" | "action_required" | "manual_review" | null;
  decision_label: string | null;
  findings: KycFinding[];
  registry: Record<string, any>;
  documents: KycDoc[];
  reference_date: string | null;
  reviewer_note: string | null;
  declaration?: Record<string, any>;
};

export type ConsentNotice = {
  version: string;
  title: string;
  intro: string;
  purposes: { id: string; required: boolean; title: string; data: string[]; why: string; who: string; retention: string }[];
  always: string;
  rights: string[];
  contact: string;
  language_note: string;
};
