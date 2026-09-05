import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getMetrics, getRings, getThresholdAnalysis } from "../api/client";
import { useFetch } from "../hooks/useFetch";
import { fmt } from "../format";
import { StatusTag } from "../components/StatusTag";
import { Loading, ErrorState, EmptyState } from "../components/AsyncState";
import type { Action, MetricsResponse, RingsResponse, ThresholdAnalysisResponse } from "../api/types";

type Bundle = { m: MetricsResponse; t: ThresholdAnalysisResponse; rings: RingsResponse };

async function load(): Promise<Bundle> {
  const [m, t, rings] = await Promise.all([getMetrics(), getThresholdAnalysis(), getRings()]);
  return { m, t, rings };
}

const FILTERS: { value: Action | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "escalate", label: "Escalate" },
  { value: "review", label: "Review" },
  { value: "allow", label: "Allow" },
];

export function ControlCenter() {
  const { data, loading, error, reload } = useFetch(load, []);
  const [filter, setFilter] = useState<Action | "all">("all");

  const filteredRings = useMemo(() => {
    if (!data) return [];
    return filter === "all" ? data.rings.rings : data.rings.rings.filter((r) => r.action === filter);
  }, [data, filter]);

  if (loading) return <Loading label="Risk Control Center" />;
  if (error) return <ErrorState label="Risk Control Center" message={error} onRetry={reload} />;
  if (!data) return <EmptyState>No data.</EmptyState>;

  const { m, t, rings } = data;
  const saved = Math.abs(m.cost.delta);
  const savedPct = m.cost.binary_baseline ? saved / m.cost.binary_baseline : 0;
  const ladder = Object.fromEntries(t.ladder.map((r) => [r.policy, r.expected_loss]));

  return (
    <div className="flex flex-col gap-2">
      {/* header rail */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border border-line bg-bg px-3 py-2 text-xs text-ink-2">
        <span>
          Components <b className="num">{fmt.int(rings.total_in_split)}</b>
        </span>
        <span>
          Expected loss <b className="num">{fmt.money(m.cost.expected_loss)}</b>
        </span>
        <span>
          Binary policy <b className="num">{fmt.money(m.cost.binary_baseline)}</b>
        </span>
        <span className="text-good">
          False escalations <b className="num">{fmt.int(m.quality.escalated_false_positives)}</b>
        </span>
        <span className="text-good">
          Rings recovered <b className="num">{fmt.int(m.quality.rings_recovered)}</b>/
          <b className="num">{fmt.int(m.quality.rings_in_test)}</b>
        </span>
        <span>
          Review rate <b className="num">{fmt.pct2(m.triage.review_rate)}</b>
        </span>
        <span className="ml-auto num text-[11px] text-ink-3">cfg {m.config_fingerprint}</span>
      </div>

      <div className="grid grid-cols-12 gap-2">
        {/* Triage summary */}
        <section className="col-span-12 border border-line bg-bg lg:col-span-7">
          <h2 className="flex border-b border-line text-[11px] font-semibold">
            <span className="bg-ink px-2.5 py-1 text-white">Triage</span>
            <span className="ml-auto self-center px-2.5 font-mono text-[10px] font-normal text-ink-3">
              {rings.total_in_split} components / 3 dispositions
            </span>
          </h2>
          <p className="px-2.5 pt-2 text-xs leading-relaxed text-ink-2">
            <b className="text-ink">{m.quality.escalated_false_positives === 0 ? "Zero" : m.quality.escalated_false_positives}</b>{" "}
            false-positive escalation{m.quality.escalated_false_positives === 1 ? "" : "s"} on held-out data.
          </p>
          <dl className="mt-1 flex flex-wrap border-t border-line-2">
            {(
              [
                ["Escalate", m.triage.escalate, m.narration.escalate, "text-red"],
                ["Review", m.triage.review, m.narration.review, "text-amber"],
                ["Allow", m.triage.allow, m.narration.allow, "text-ink"],
              ] as const
            ).map(([label, val, sub, cls]) => (
              <div key={label} className="flex-1 border-r border-line-2 px-2.5 py-2.5 last:border-r-0">
                <dt className="text-[10px] uppercase tracking-wide text-ink-3">{label}</dt>
                <dd className={`num mt-0.5 text-[28px] font-bold leading-none ${cls}`}>{val}</dd>
                <div className="mt-1 text-[10px] text-ink-2">{sub}</div>
              </div>
            ))}
          </dl>
          <dl className="flex border-t border-line-2">
            <div className="flex-1 border-r border-line-2 px-2.5 py-2">
              <dt className="text-[10px] uppercase tracking-wide text-ink-3">Expected loss</dt>
              <dd className="num text-lg font-semibold">{fmt.money(m.cost.expected_loss)}</dd>
              <div className="text-[10px] text-ink-2">was {fmt.money(m.cost.binary_baseline)} binary</div>
            </div>
            <div className="flex-1 px-2.5 py-2">
              <dt className="text-[10px] uppercase tracking-wide text-ink-3">Saved</dt>
              <dd className="num text-lg font-semibold text-good">{fmt.money(saved)}</dd>
              <div className="text-[10px] text-ink-2">{fmt.pct1(savedPct)} lower</div>
            </div>
          </dl>
          <div className="px-2.5 py-2.5">
            <div className="flex h-6 overflow-hidden border border-line">
              <div
                className="flex items-center justify-center bg-fill-2 text-[10px] font-semibold text-quiet"
                style={{ flex: m.triage.allow }}
              >
                ALLOW · {m.triage.allow}
              </div>
              <div
                className="flex items-center justify-center bg-[#ffeccc] text-[10px] font-semibold text-amber"
                style={{ flex: m.triage.review }}
              >
                REVIEW · {m.triage.review}
              </div>
              <div
                className="flex items-center justify-center bg-red text-[10px] font-semibold text-white"
                style={{ flex: m.triage.escalate }}
              >
                ESCALATE · {m.triage.escalate}
              </div>
            </div>
            <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-3">
              <span>score 0.000</span>
              <span>
                t_lo {m.band.t_lo} · t_hi {m.band.t_hi}
              </span>
              <span>1.000</span>
            </div>
          </div>
        </section>

        {/* Cost model */}
        <section className="col-span-12 border border-line bg-bg lg:col-span-5">
          <h2 className="flex border-b border-line text-[11px] font-semibold">
            <span className="bg-ink px-2.5 py-1 text-white">Cost model</span>
            <span className="ml-auto self-center px-2.5 font-mono text-[10px] font-normal text-ink-3">
              dataset-derived
            </span>
          </h2>
          <dl className="grid grid-cols-2 gap-px bg-line-2">
            {[
              ["Manual review", fmt.money(t.costs.manual_review), "per component"],
              ["False negative", fmt.money(t.costs.false_negative), "median ring exposure"],
              ["False positive", fmt.money(t.costs.false_positive), "review + friction"],
              ["FN : FP ratio", `${Math.round(t.costs.false_negative / t.costs.false_positive)} : 1`, "drives a low threshold"],
              ["Flag-everything", fmt.money(ladder.flag_everything ?? 0), "100% review rate"],
              ["This policy", fmt.money(ladder.three_way ?? 0), `${fmt.pct2(m.triage.review_rate)} review rate`],
            ].map(([label, val, sub]) => (
              <div key={label} className="bg-bg px-2.5 py-2">
                <dt className="text-[10px] uppercase tracking-wide text-ink-3">{label}</dt>
                <dd className="num text-base font-semibold">{val}</dd>
                <div className="text-[10px] text-ink-2">{sub}</div>
              </div>
            ))}
          </dl>
        </section>

        {/* Queue */}
        <section className="col-span-12 border border-line bg-bg">
          <h2 className="flex items-center border-b border-line text-[11px] font-semibold">
            <span className="bg-ink px-2.5 py-1 text-white">Queue</span>
            <span className="ml-auto flex gap-1 self-center px-2.5">
              {FILTERS.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  onClick={() => setFilter(f.value)}
                  className={`px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                    filter === f.value ? "bg-red text-white" : "border border-line-2 text-ink-2 hover:bg-fill"
                  }`}
                  aria-pressed={filter === f.value}
                >
                  {f.label}
                </button>
              ))}
            </span>
          </h2>
          <div className="max-h-[480px] overflow-auto">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="bg-fill text-[10px] uppercase tracking-wide text-ink-3">
                  <th className="border-b border-line px-2 py-1 text-left">Component</th>
                  <th className="border-b border-line px-2 py-1 text-left">Status</th>
                  <th className="border-b border-line px-2 py-1 text-right">Score</th>
                  <th className="border-b border-line px-2 py-1 text-right">Acc</th>
                  <th className="border-b border-line px-2 py-1 text-right">Txn</th>
                  <th className="border-b border-line px-2 py-1 text-right">Exposure</th>
                  <th className="border-b border-line px-2 py-1 text-left">Label</th>
                </tr>
              </thead>
              <tbody>
                {filteredRings.length === 0 && (
                  <tr>
                    <td colSpan={7} className="p-3 text-center text-ink-3">
                      No components match this filter.
                    </td>
                  </tr>
                )}
                {filteredRings.map((r) => (
                  <tr key={r.component_id} className="border-b border-line-2 hover:bg-[#fff8f8]">
                    <td className="px-2 py-1">
                      <Link
                        to={`/investigator/${encodeURIComponent(r.component_id)}`}
                        className="num font-medium text-ink underline-offset-2 hover:underline"
                      >
                        {r.component_id}
                      </Link>
                    </td>
                    <td className="px-2 py-1">
                      <StatusTag action={r.action} />
                    </td>
                    <td className="num px-2 py-1 text-right font-semibold">{fmt.f4(r.score)}</td>
                    <td className="num px-2 py-1 text-right">{r.size}</td>
                    <td className="num px-2 py-1 text-right">{r.n_txns}</td>
                    <td className="num px-2 py-1 text-right">{fmt.money(r.exposure)}</td>
                    <td className="px-2 py-1">
                      {r.label && r.label !== "family" ? (
                        r.label
                      ) : r.has_family ? (
                        <span className="border border-line-2 bg-fill px-1 text-[10px] text-ink-2">family</span>
                      ) : (
                        <span className="text-ink-3">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
