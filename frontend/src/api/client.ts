// Typed fetch wrappers for the 8 frozen endpoints. Mirrors mockups/api.js's
// `j()` helper: throw with the path and status on a non-OK response, and
// never swallow a failure into a fabricated value.

import type {
  Action,
  AnalystAction,
  BenchmarkResponse,
  EvidenceResponse,
  ExplainResponse,
  MetricsResponse,
  RingsResponse,
  ThresholdAnalysisResponse,
} from "./types";

export const API_BASE = "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export function getRings(opts: { split?: string; action?: Action } = {}) {
  const q = new URLSearchParams();
  if (opts.split) q.set("split", opts.split);
  if (opts.action) q.set("action", opts.action);
  const qs = q.toString();
  return get<RingsResponse>(`/rings${qs ? `?${qs}` : ""}`);
}

export function getEvidence(componentId: string) {
  return get<EvidenceResponse>(`/rings/${encodeURIComponent(componentId)}/evidence`);
}

export function postReview(
  componentId: string,
  action: AnalystAction,
  analyst = "demo",
) {
  return post<{ ts: string }>(`/rings/${encodeURIComponent(componentId)}/review`, {
    action,
    analyst,
  });
}

export function getMetrics() {
  return get<MetricsResponse>("/metrics");
}

export function getThresholdAnalysis() {
  return get<ThresholdAnalysisResponse>("/threshold-analysis");
}

export function getBenchmark() {
  return get<BenchmarkResponse>("/benchmark");
}

export function postExplain(componentId: string) {
  return post<ExplainResponse>("/explain", { component_id: componentId });
}
