import { useState } from "react";
import { getThresholdAnalysis } from "../api/client";
import { useFetch } from "../hooks/useFetch";
import { fmt } from "../format";
import { Loading, ErrorState, EmptyState } from "../components/AsyncState";

// PRD UI constraint: "Threshold/Cost and Evaluation/Benchmark should be
// functional reference views, not separate UI projects." This screen reads
// both the 4-row policy ladder (POLICY comparison) and the 101-row threshold
// sweep from Task 7 (how the six named columns move as the cutoff moves) --
// they answer different questions, so both are shown, but with plain tables
// rather than the bespoke visual treatment Control Center/Investigator get.

export function Threshold() {
  const { data: t, loading, error, reload } = useFetch(getThresholdAnalysis, []);
  const [showFullSweep, setShowFullSweep] = useState(false);

  if (loading) return <Loading label="threshold analysis" />;
  if (error) return <ErrorState label="threshold analysis" message={error} onRetry={reload} />;
  if (!t) return <EmptyState>No data.</EmptyState>;

  const worst = t.ladder.find((r) => r.policy === "flag_nothing")?.expected_loss ?? 1;
  const sweepRows = showFullSweep ? t.sweep.grid : t.sweep.grid.filter((_, i) => i % 5 === 0 || _.selected);

  return (
    <div className="flex flex-col gap-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border border-line bg-bg px-3 py-2 text-ink-2">
        <span>
          C_review <b className="num">{fmt.money(t.costs.manual_review)}</b>
        </span>
        <span>
          C_fn <b className="num">{fmt.money(t.costs.false_negative)}</b>
        </span>
        <span>
          C_fp <b className="num">{fmt.money(t.costs.false_positive)}</b>
        </span>
        <span>
          FN:FP <b className="num">{Math.round(t.costs.false_negative / t.costs.false_positive)}</b> : 1
        </span>
        <span>
          Band <b className="num">
            {t.band.t_lo} / {t.band.t_hi}
          </b>
        </span>
        <span className="ml-auto num text-[11px] text-ink-3">cfg {t.config_fingerprint}</span>
      </div>

      {/* Cost model derivation */}
      <section className="border border-line bg-bg">
        <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
          Cost model -- every figure traceable to a dataset quantity
        </h2>
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-fill text-[10px] uppercase tracking-wide text-ink-3">
              <th className="border-b border-line px-2 py-1 text-left">Cost</th>
              <th className="border-b border-line px-2 py-1 text-left">Derivation</th>
              <th className="border-b border-line px-2 py-1 text-right">INR</th>
            </tr>
          </thead>
          <tbody>
            {(["manual_review", "false_negative", "false_positive"] as const).map((k) => (
              <tr key={k} className="border-b border-line-2 align-top">
                <td className="num px-2 py-1.5 font-semibold">{k}</td>
                <td className="px-2 py-1.5 text-ink-2">{String(t.costs.derivation[k] ?? "")}</td>
                <td className="num px-2 py-1.5 text-right">{fmt.money(t.costs[k])}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-fill font-semibold">
              <td colSpan={2} className="px-2 py-1.5">
                Ratio C_fn : C_fp -- why the threshold sits low
              </td>
              <td className="num px-2 py-1.5 text-right">
                {Math.round(t.costs.false_negative / t.costs.false_positive)} : 1
              </td>
            </tr>
          </tfoot>
        </table>
      </section>

      <div className="grid grid-cols-12 gap-2">
        {/* Ladder */}
        <section className="col-span-12 border border-line bg-bg lg:col-span-6">
          <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
            Expected loss ladder
          </h2>
          <div className="flex flex-col gap-2 p-2.5">
            {t.ladder.map((row) => (
              <div key={row.policy} className="grid grid-cols-[140px_1fr_100px] items-center gap-2">
                <div>
                  <div className="font-semibold capitalize">{row.policy.replace(/_/g, " ")}</div>
                  <div className="text-[10px] text-ink-3">{row.detail}</div>
                </div>
                <div className="relative h-5 border border-line-2 bg-fill-2">
                  <div
                    className={`absolute inset-y-0 left-0 ${
                      row.policy === "three_way" ? "bg-red" : row.policy === "binary" ? "bg-amber" : "bg-quiet"
                    }`}
                    style={{ width: `${Math.min(100, (row.expected_loss / worst) * 100).toFixed(2)}%` }}
                  />
                </div>
                <div className="num text-right font-semibold">{fmt.money(row.expected_loss)}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Band search */}
        <section className="col-span-12 border border-line bg-bg lg:col-span-6">
          <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
            Band search -- {fmt.int(t.search.bands_considered)} candidate bands
          </h2>
          <div className="p-2.5">
            <div className="flex h-6 overflow-hidden border border-line text-[10px] font-semibold">
              <div
                className="flex items-center justify-center bg-[#f0d4d4] text-[#8f1a1f]"
                style={{ flex: t.search.bands_refused_by_coverage }}
              >
                {fmt.int(t.search.bands_refused_by_coverage)} refused
              </div>
              <div
                className="flex items-center justify-center bg-fill-2 text-quiet"
                style={{ flex: t.search.bands_considered - t.search.bands_refused_by_coverage }}
              >
                {fmt.int(t.search.bands_considered - t.search.bands_refused_by_coverage)} eligible
              </div>
            </div>
            <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-3">
              <span>review-rate gate {fmt.pct0(t.search.max_review_rate_gate)}</span>
              <span>
                {fmt.pct1(t.search.bands_refused_by_coverage / t.search.bands_considered)} of the grid refused
              </span>
            </div>
          </div>
          <table className="w-full border-collapse">
            <tbody>
              <tr className="border-b border-line-2">
                <td className="px-2 py-1">Integrity panel verdict</td>
                <td className="num px-2 py-1 text-right font-semibold text-good">{t.search.panel_verdict}</td>
              </tr>
              <tr className="border-b border-line-2">
                <td className="px-2 py-1">Selected on</td>
                <td className="px-2 py-1 text-right text-ink-2">{t.search.selected_on}</td>
              </tr>
              <tr className="border-b border-line-2">
                <td className="px-2 py-1">Validation expected loss</td>
                <td className="num px-2 py-1 text-right">{fmt.money(t.search.validation_expected_loss)}</td>
              </tr>
              <tr>
                <td className="px-2 py-1">Held-out expected loss</td>
                <td className="num px-2 py-1 text-right font-semibold">
                  {fmt.money(t.ladder.find((r) => r.policy === "three_way")?.expected_loss ?? 0)}
                </td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>

      {/* Policy comparison */}
      <section className="border border-line bg-bg">
        <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
          Policy comparison -- same held-out components
        </h2>
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-fill text-right text-[10px] uppercase tracking-wide text-ink-3">
              <th className="border-b border-line px-2 py-1 text-left">Policy</th>
              <th className="border-b border-line px-2 py-1">TP</th>
              <th className="border-b border-line px-2 py-1">FP</th>
              <th className="border-b border-line px-2 py-1">FN</th>
              <th className="border-b border-line px-2 py-1">TN</th>
              <th className="border-b border-line px-2 py-1">Touch rate</th>
              <th className="border-b border-line px-2 py-1">Expected loss</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-line-2">
              <td className="px-2 py-1.5">
                <div className="num font-semibold">Binary @ {t.comparison.binary.threshold}</div>
                <div className="text-[11px] text-ink-2">Every flag is an escalation.</div>
              </td>
              <td className="num px-2 py-1.5 text-right">{t.comparison.binary.tp}</td>
              <td className="num px-2 py-1.5 text-right text-amber">{t.comparison.binary.fp}</td>
              <td className="num px-2 py-1.5 text-right">{t.comparison.binary.fn}</td>
              <td className="num px-2 py-1.5 text-right">{t.comparison.binary.tn}</td>
              <td className="num px-2 py-1.5 text-right">{fmt.pct2(t.comparison.binary.review_rate)}</td>
              <td className="num px-2 py-1.5 text-right">{fmt.money(t.comparison.binary.expected_loss)}</td>
            </tr>
            <tr className="border-b border-line-2 bg-[#ffe0e0] shadow-[inset_3px_0_0_var(--color-red)]">
              <td className="px-2 py-1.5">
                <div className="num font-semibold">Three-way {t.band.t_lo} / {t.band.t_hi}</div>
                <div className="text-[11px] text-ink-2">
                  {t.comparison.three_way.actions.escalate} escalated, {t.comparison.three_way.actions.review}{" "}
                  reviewed, {t.comparison.three_way.actions.allow} allowed.
                </div>
              </td>
              <td className="num px-2 py-1.5 text-right" colSpan={3}>
                precision {fmt.pct2(t.comparison.three_way.precision)} · recall (escalate only){" "}
                {fmt.pct2(t.comparison.three_way.recall_escalate_only)}
              </td>
              <td className="num px-2 py-1.5 text-right text-good">
                {fmt.pct2(t.comparison.three_way.false_positive_rate_escalate_only)} FPR
              </td>
              <td className="num px-2 py-1.5 text-right">{fmt.pct2(t.comparison.three_way.review_rate)}</td>
              <td className="num px-2 py-1.5 text-right font-semibold">
                {fmt.money(t.comparison.three_way.expected_loss)}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="p-2.5 text-[11px] leading-relaxed text-ink-2">{t.comparison.three_way.note}</p>
      </section>

      {/* Threshold sweep */}
      <section className="border border-line bg-bg">
        <h2 className="flex items-center border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
          <span>
            Threshold sweep -- computed on {t.sweep.computed_on}, {t.sweep.n_components} components
          </span>
          <button
            type="button"
            onClick={() => setShowFullSweep((v) => !v)}
            className="ml-auto border border-white/40 px-2 py-0.5 text-[10px] font-normal normal-case text-white hover:bg-white/10"
          >
            {showFullSweep ? "Show every 5th row" : `Show all ${t.sweep.grid.length} rows`}
          </button>
        </h2>
        <div className="max-h-[420px] overflow-auto">
          <table className="w-full border-collapse text-right">
            <thead>
              <tr className="sticky top-0 bg-fill text-[10px] uppercase tracking-wide text-ink-3">
                <th className="border-b border-line px-2 py-1 text-left">Threshold</th>
                <th className="border-b border-line px-2 py-1">Precision</th>
                <th className="border-b border-line px-2 py-1">Recall</th>
                <th className="border-b border-line px-2 py-1">FP rate</th>
                <th className="border-b border-line px-2 py-1">FN rate</th>
                <th className="border-b border-line px-2 py-1">Reviews</th>
                <th className="border-b border-line px-2 py-1">Expected loss</th>
              </tr>
            </thead>
            <tbody>
              {sweepRows.map((row) => (
                <tr
                  key={row.threshold}
                  className={`border-b border-line-2 ${
                    row.selected ? "bg-[#ffe0e0] shadow-[inset_3px_0_0_var(--color-red)] font-semibold" : ""
                  }`}
                >
                  <td className="num px-2 py-1 text-left">
                    {row.threshold.toFixed(2)}
                    {row.selected ? " (selected)" : ""}
                  </td>
                  <td className="num px-2 py-1">{fmt.f4(row.precision)}</td>
                  <td className="num px-2 py-1">{fmt.f4(row.recall)}</td>
                  <td className="num px-2 py-1">{fmt.pct2(row.false_positive_rate)}</td>
                  <td className="num px-2 py-1">{fmt.pct2(row.false_negative_rate)}</td>
                  <td className="num px-2 py-1">
                    {row.manual_reviews} ({fmt.pct1(row.manual_review_rate)})
                  </td>
                  <td className="num px-2 py-1">{fmt.money(row.expected_loss)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border border-line-2 bg-[#fdf3e0] p-2.5 text-[11px] leading-relaxed text-ink-2">
        <div className="mb-1 inline-block bg-amber px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
          Sensitivity note
        </div>
        <p>{t.sensitivity.note}</p>
        <p className="mt-2 text-ink-3">{t.sample_variance_note}</p>
      </section>
    </div>
  );
}
