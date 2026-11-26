// Thin typed client. Same-origin paths: nginx (Docker) or Vite (dev) forwards them to the API.
// The UI only formats what comes back; it never computes a bid number itself.

export type Health = { status: string; version: string; database: string; llm_mode: string; runs: Record<string, number> };
export type Agent = { kind: string; title: string; job: string; built: boolean };
export type Doc = { id: string; kind: string; filename: string; size_bytes: number; created_at: string };
export type Run = {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  document_id: string | null;
  params: Record<string, unknown>;
  progress: number;
  message: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  cost_usd: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export type GoalSeek = { value: number | null; achieved: number | null; iterations: number; converged: boolean; elapsed_ms: number; message: string };

export type BridgeStep = { label: string; where: string | null; delta: number; after: number; assumed: boolean };
export type Driver = { cell: string; label: string; value: number; low: number; high: number; swing: number; exact: boolean };
export type MustDo = { cr: number; per_mw_inr: number; our_mw: number; from: string; clause: string; pdf_page: number | null; quote: string };
export type Brief = {
  document_id: string;
  as_received: number | null;
  corrected: number | null;
  entry_bid: number | null;
  target_low: number | null;
  target_high: number | null;
  walk_away: number | null;
  reasons: string[];
  basis: string[];
  bridge: BridgeStep[];
  depends_most_on: Driver[];
  must_dos: Record<string, MustDo>;
  snapshot_id: string | null;
  sources: Record<string, string>;
  pending: string[];
};

export type Fix = { overrides: Record<string, unknown>; formula_patches: Record<string, string>; note: string };
export type Finding = {
  id: string;
  where: string;
  severity: "high" | "medium" | "low" | "info";
  title: string;
  evidence: string;
  impact_inr_per_kwh: number | null;
  fix: Fix | null;
  assumptions: string[];
  clauses: string[];
};
export type Findings = {
  document_id: string;
  tender_facts_used: number;
  breakeven_as_received: number;
  corrected_breakeven: number;
  findings: Finding[];
};

export type LadderPoint = {
  tariff: number;
  p_win_any: number;
  p_win_full: number;
  expected_mw: number;
  p_h1_eliminated: number;
  equity_irr: number | null;
  min_dscr: number | null;
  npv_cr: number | null;
  expected_value_cr: number | null;
};
export type Recommendation = { entry_bid: number; target_low: number; target_high: number; walk_away: number; reasons: string[] };
export type EngineResult = {
  breakeven_tariff: number | null;
  dscr_tariff: number | null;
  hurdle: number;
  curve: { tariff: number; equity_irr: number | null; min_dscr: number | null }[];
  ladder: LadderPoint[];
  recommendation: Recommendation | null;
  snapshot_id: string | null;
  regime?: string;
  why_no_ladder?: string;
};

export type RivalProfile = {
  name: string;
  archetype: "leader" | "mid_pack" | "laggard" | "wildcard";
  p_participate: number;
  capacity_mw: [number, number][];
  floor_p10: number;
  floor_p50: number;
  floor_p90: number;
  why: string[];
  sources: string[];
};
export type Snapshot = { id: string; regime: string; seed: number; n_draws: number; profiles: RivalProfile[]; sha256: string };
export type RivalResult = { seed: number; shift_inr_per_kwh: number; rivals: number; snapshots: Record<string, Snapshot> };

export type TenderFact = {
  field: string;
  value: unknown;
  unit: string;
  clause: string;
  pdf_page: number;
  printed_page: number | null;
  quote: string;
  verified: boolean;
  source: string;
};
export type TenderResult = { pages: number; facts: TenderFact[]; unusual_clauses: TenderFact[]; verified: number; sources: Record<string, number>; cost_usd: number };

export type Scenario = { id: string; name: string; document_id: string; overrides: Record<string, unknown>; rival_run_id: string | null; source: string; created_at: string };
export type ChatReply = { answer: string; scenario_id: string | null; run_id: string | null; grounded: string[]; ungrounded: string[]; cost_usd: number };
export type ReplayEvent = Record<string, unknown> & { minute: number; type: string };
export type Replay = { snapshot_id: string; draw: number; events: ReplayEvent[] };
export type AssumptionRow = { id: string; assumption: string; value: string; source: string; used_by: string; change_in: string };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => call<Health>("/health"),
  agents: () => call<Agent[]>("/api/agents"),
  documents: () => call<Doc[]>("/api/documents"),
  runs: (query = "limit=40") => call<Run[]>(`/api/runs?${query}`),
  run: (id: string) => call<Run>(`/api/runs/${id}`),
  latestRun: async (kind: string, documentId?: string) => {
    // A what-if reruns the engine for its scenario; the base line is the latest run without overrides.
    const q = `kind=${kind}&status=succeeded&limit=50` + (documentId ? `&document_id=${documentId}` : "");
    const rows = await call<Run[]>(`/api/runs?${q}`);
    return rows.find((r) => !r.params?.scenario_id && !r.params?.overrides) ?? null;
  },
  startRun: (kind: string, document_id: string | null, params: Record<string, unknown> = {}) =>
    post<Run>("/api/runs", { kind, document_id, params }),
  brief: (docId: string) => call<Brief>(`/api/brief/${docId}`),
  findings: (docId: string) => call<Findings>(`/api/workbooks/${docId}/findings`),
  drivers: (docId: string) => call<{ drivers: Driver[] }>(`/api/workbooks/${docId}/drivers`),
  replay: (docId: string, draw: number, open: number, floor: number, regime: string) =>
    call<Replay>(`/api/replay/${docId}?draw=${draw}&open=${open}&floor=${floor}&regime=${regime}`),
  scenarios: () => call<Scenario[]>("/api/scenarios"),
  chat: (message: string, document_id?: string) => post<ChatReply>("/api/chat", { message, document_id }),
  assumptions: () => call<{ rows: AssumptionRow[]; count: number }>("/api/assumptions"),
  goalSeek: (docId: string, variable: string, target: string, targetValue: number) =>
    post<GoalSeek>(`/api/workbooks/${docId}/goal-seek`, { variable, target, target_value: targetValue }),
  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/documents", { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
    return res.json();
  },
};

export const inr = (v: number | null | undefined, digits = 2) => (v == null ? "n/a" : `₹${v.toFixed(digits)}`);
export const pct = (v: number | null | undefined, digits = 0) => (v == null ? "n/a" : `${(v * 100).toFixed(digits)}%`);
export const paise = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)} paise`;
