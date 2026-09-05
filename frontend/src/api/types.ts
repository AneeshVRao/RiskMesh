// Wire types for the 8 frozen RiskMesh endpoints. Shapes are read directly
// off riskmesh/api/payloads.py -- this file adds no field the backend does
// not already send, and no endpoint changes are made to support it.

export type Action = "allow" | "review" | "escalate";
export type AnalystAction = "allow" | "watch" | "review" | "escalate";

export interface RingRow {
  component_id: string;
  rank: number;
  score: number;
  action: Action;
  size: number;
  n_txns: number;
  exposure: number;
  label: string | null;
  is_positive: boolean;
  has_family: boolean;
}

export interface RingsResponse {
  config_fingerprint: string;
  band: { t_lo: number; t_hi: number };
  split: string;
  count: number;
  total_in_split: number;
  rings: RingRow[];
}

export interface Signal {
  name: string;
  raw: number | string;
  normalized: number;
  weight: number;
  contribution: number;
  detail: string;
  weighted: boolean;
  note?: string;
}

export interface GraphNode {
  id: string;
  type: "device" | "instrument" | "ip" | "merchant";
  degree: number;
}

export interface GraphEdge {
  account: string;
  node: string;
  kind: "device" | "instrument" | "ip" | "merchant";
  txns: number;
}

export interface RingGraphData {
  accounts: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ComparisonSide {
  component_id: string;
  label: string | null;
  score: number;
  accounts: number;
  median_account_age_days: number;
  burst: string;
  burst_fraction: number;
  max_accounts_per_ip: number;
  shared_instruments: number;
  refund_rate: number;
  exposure: number;
  action: Action;
}

export interface Comparison {
  subject: ComparisonSide;
  peer: ComparisonSide;
  peer_rule: string;
  separating_fields: string[];
}

export interface AuditRecord {
  ts: string;
  component_id: string;
  analyst_action: AnalystAction;
  analyst: string;
  note: string | null;
  score: number;
  band: { t_lo: number; t_hi: number };
  system_action: Action;
  agreed_with_system: boolean;
  config_fingerprint: string;
  evidence_sha256: string;
  evidence_snapshot: { signals: Signal[]; summary: Record<string, unknown> };
}

export interface EvidenceResponse {
  config_fingerprint: string;
  band: { t_lo: number; t_hi: number };
  component_id: string;
  split: string;
  score: number;
  action: Action;
  rank: { position: number; of: number };
  summary: {
    size: number;
    n_txns: number;
    exposure: number;
    ring_id: string | null;
    is_positive: boolean;
    has_family: boolean;
  };
  decomposition: { score: number; headroom: number; signals: Signal[] };
  graph: RingGraphData;
  comparison: Comparison | null;
  audit: AuditRecord[];
}

export interface MetricsResponse {
  config_fingerprint: string;
  band: { t_lo: number; t_hi: number };
  triage: {
    allow: number;
    review: number;
    escalate: number;
    review_rate: number;
    n_components: number;
  };
  narration: { escalate: string; review: string; allow: string };
  cost: { expected_loss: number; binary_baseline: number; delta: number };
  quality: {
    precision: number;
    recall: number;
    f1: number;
    false_positive_rate: number;
    rings_recovered: number;
    rings_in_test: number;
    escalated_false_positives: number;
  };
}

export interface SweepRow {
  threshold: number;
  precision: number;
  recall: number;
  false_positive_count: number;
  false_positive_rate: number;
  false_negative_count: number;
  false_negative_rate: number;
  manual_reviews: number;
  manual_review_rate: number;
  expected_loss: number;
  selected: boolean;
}

export interface LadderRow {
  policy: string;
  expected_loss: number;
  detail: string;
}

export interface ThresholdAnalysisResponse {
  config_fingerprint: string;
  band: { t_lo: number; t_hi: number };
  costs: { false_negative: number; false_positive: number; manual_review: number };
  ladder: LadderRow[];
  sweep: {
    computed_on: string;
    n_components: number;
    selected_threshold: number;
    grid: SweepRow[];
  };
  comparison: Record<string, unknown>;
  search: {
    bands_considered: number;
    bands_refused_by_coverage: number;
    max_review_rate_gate: number;
    panel_verdict: string;
    selected_on: string;
    validation_expected_loss: number;
  };
  sensitivity: unknown;
  sample_variance_note: string;
}

export interface BaselineRow {
  baseline: string;
  description: string;
  uses_graph: boolean;
  cutoff?: number;
  direction?: string;
  threshold?: number;
  status?: string;
  held_out: { f1: number; false_positive_rate: number } | null;
  held_out_hard_negatives_only: { f1: number } | null;
}

export interface AblationRow {
  group: string;
  weight_removed: number;
  signals_removed: string[];
  threshold: number;
  identical_to_full: boolean;
  delta_f1: number;
  held_out: { f1: number; rings_recovered: number; rings_in_test: number };
  held_out_hard_negatives_only: { f1: number };
}

export interface WeightCandidate {
  policy: string;
  panel_verdict: "PASS" | "FAIL";
  positives_below_max_negative: number;
  hard_negatives_inside_positive_range: number;
  feasible: boolean;
  expected_loss: number | null;
  refused_by?: string;
  reason?: string;
}

export interface PanelCheck {
  value: unknown;
  bound: string;
  status: "PASS" | "FLAG";
}

export interface BenchmarkResponse {
  config_fingerprint: string;
  band: { t_lo: number; t_hi: number };
  primary: Record<string, number>;
  secondary: Record<string, unknown>;
  ground_truth_rule: string;
  split: Record<string, unknown>;
  panel: {
    verdict: string;
    checks: Record<string, PanelCheck>;
    computed_on: string;
    positives_below_max_negative: number;
    hard_negatives_inside_positive_range: number;
  };
  single_signal_max_f1: Record<string, number>;
  baselines: { baselines: BaselineRow[] };
  ablations: { configurations: AblationRow[] };
  bootstrap_ci: Record<string, unknown>;
  weight_search: { gates: Record<string, unknown>; candidates: WeightCandidate[] };
  reproducibility: Record<string, unknown>;
}

export interface ExplainResponse {
  component_id: string;
  text: string;
  grounded_in: string[];
  config_fingerprint: string;
  fallback_used: boolean;
  note: string;
}
