export type Risk = "cautious" | "balanced" | "bold";
export type Action = "prebuy_allot" | "prebuy" | "allot_only" | "over_budget" | "watch" | "add_supplier" | "renegotiate";

export interface Forecast { p10: number; p50: number; p90: number }
export interface Signals {
  on_books: number; on_books_ly: number; pace_yoy: number; searches: number; search_yoy: number;
  look_to_book: number; soldout_nights_ly: number; rate_change: number; ly_demand: number; lead_days: number;
}
export interface Economics {
  hard_cost: number; sell_price: number; allot_cost: number | null; allot_fee: number; allot_cap: number;
  salvage: number; supply_cap: number; suppliers: number; held: number; breakeven_sure: number | null;
}
export interface OptionInfo {
  id: string; name: string; product: string; kind: "hotel" | "flight"; unit: string; region: string;
  dates: string; start: string; nights: number; image: string | null; image_alt: string;
  economics: Economics; forecast: Forecast; signals: Signals;
}
export interface Dist { expected: number; cvar: number; p_loss: number; p05: number; p95: number }
export interface Hist { edges: number[]; counts: number[][] }
export interface Alert {
  kind: "release" | "reprice" | "supplier" | "buy_now"; option_id: string; date: string;
  severity: "warning" | "info"; title: string; detail: string; suggested_cut?: number;
}
export interface PlanRow {
  id: string; rank: number; action: Action; label: string; locked: boolean;
  plan: { hard: number; allot: number; cash: number };
  unconstrained: { hard: number; allot: number };
  forecast: Forecast; signals: Signals;
  stats: { p_hard_all_sell: number | null; hard_sell_through: number | null; expected_unsold_hard: number;
           expected_allot_used: number; p_sold_out: number; expected_lost_demand: number };
  profit: Dist; baseline: Dist & { hard: number };
  reasons: string[]; alerts: Alert[]; demand_hist: Hist; profit_hist: Hist;
}
export interface Plan {
  budget: number; risk: Risk; risk_label: string;
  solver: { method: string; seconds: number; candidates: number; exact_status: string; objective: number };
  summary: Dist & { cash: number; hard_units: number; allot_units: number; hard_sell_through: number | null };
  baseline: Dist & { name: string; cash: number };
  histogram: Hist; rows: PlanRow[]; alerts: Alert[];
}
export interface Meta {
  version: string; season: string; today: string; default_budget: number; scenarios: number;
  cvar_alpha: number; history_rows: number; risk_profiles: { id: Risk; label: string; cvar_weight: number }[];
}
export interface EvalBlock {
  rows: number; wape_p50: number; wape_naive: number; improvement: number; coverage_p10_p90: number;
  below_p10: number; above_p90: number; pinball: Record<string, number>;
}
export interface Backtest {
  train_rows: number; calibration_rows: number; test_period: string; all: EvalBlock; peak_windows: EvalBlock;
  by_lead_wape: Record<string, number>;
  by_option: Record<string, { wape_p50: number; wape_naive: number; coverage: number }>;
  band_correction_log: { p10: number; p90: number };
  importance: { feature: string; share: number }[];
}
export interface Decision {
  id: number; option_id: string; action: "approve" | "edit" | "reject" | "undo"; hard: number | null;
  allot: number | null; budget: number | null; risk: Risk | null; note: string | null; created_at: string;
}
export interface Decisions { current: Record<string, Decision>; log: Decision[] }
export interface Correlation { ids: string[]; matrix: number[][] }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail ?? msg; } catch { /* not json */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json() as Promise<T>;
}

const liveApi = {
  meta: () => call<Meta>("/api/meta"),
  options: () => call<OptionInfo[]>("/api/options"),
  plan: (budget: number, risk: Risk, exact = false) =>
    call<Plan>("/api/plan", { method: "POST", body: JSON.stringify({ budget, risk, exact }) }),
  backtest: () => call<Backtest>("/api/backtest"),
  correlation: () => call<Correlation>("/api/correlation"),
  decisions: () => call<Decisions>("/api/decisions"),
  decide: (body: DecisionBody) => call<Decision>("/api/decisions", { method: "POST", body: JSON.stringify(body) }),
  resetDecisions: () => call<{ cleared: boolean }>("/api/decisions", { method: "DELETE" }),
};

type DecisionBody = {
  option_id: string; action: Decision["action"]; hard?: number; allot?: number; budget?: number; risk?: Risk; note?: string;
};

/*
  Demo build (npm run build:demo): no server. Plans were computed by the engine for every budget from
  ₹25 lakh to ₹5 crore in ₹25 lakh steps and each risk profile (python -m inventiq export), and are read
  as static files. Decisions are kept in this browser's storage.
*/
export const DEMO = import.meta.env.VITE_DEMO === "1";
const DEMO_STEP = 2_500_000;
export const BUDGET = { min: 2_500_000, max: 50_000_000, step: DEMO ? DEMO_STEP : 500_000 };
const DEMO_BASE = import.meta.env.BASE_URL + "demo/";
const STORE_KEY = "inventiq-demo-decisions";
let memoryLog: Decision[] | null = null;

const snap = (b: number) => Math.min(BUDGET.max, Math.max(BUDGET.min, Math.round(b / DEMO_STEP) * DEMO_STEP));

function loadLog(): Decision[] {
  if (memoryLog) return memoryLog;
  try { memoryLog = JSON.parse(localStorage.getItem(STORE_KEY) || "[]"); } catch { memoryLog = []; }
  return memoryLog ?? [];
}

function saveLog(log: Decision[]) {
  memoryLog = log;
  try { localStorage.setItem(STORE_KEY, JSON.stringify(log)); } catch { /* storage blocked: keep it for this visit */ }
}

function decisionsOf(log: Decision[]): Decisions {
  const current: Record<string, Decision> = {};
  for (const d of log) {
    if (d.action === "undo") delete current[d.option_id];
    else current[d.option_id] = d;
  }
  return { current, log: [...log].reverse() };
}

const demoApi: typeof liveApi = {
  meta: () => call<Meta>(DEMO_BASE + "meta.json"),
  options: () => call<OptionInfo[]>(DEMO_BASE + "options.json"),
  plan: (budget: number, risk: Risk) => call<Plan>(`${DEMO_BASE}plans/${risk}-${snap(budget) / 100_000}.json`),
  backtest: () => call<Backtest>(DEMO_BASE + "backtest.json"),
  correlation: () => call<Correlation>(DEMO_BASE + "correlation.json"),
  decisions: async () => decisionsOf(loadLog()),
  decide: async (body: DecisionBody) => {
    const log = loadLog();
    const d: Decision = {
      id: log.length + 1, option_id: body.option_id, action: body.action, hard: body.hard ?? null,
      allot: body.allot ?? null, budget: body.budget ?? null, risk: body.risk ?? null, note: body.note ?? null,
      created_at: new Date().toISOString(),
    };
    saveLog([...log, d]);
    return d;
  },
  resetDecisions: async () => { saveLog([]); return { cleared: true }; },
};

export const api = DEMO ? demoApi : liveApi;
