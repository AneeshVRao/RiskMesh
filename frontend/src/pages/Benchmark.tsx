import { getBenchmark } from "../api/client";
import { useFetch } from "../hooks/useFetch";
import { fmt } from "../format";
import { Loading, ErrorState, EmptyState } from "../components/AsyncState";
import type { BaselineRow } from "../api/types";

// Functional reference view (PRD: do not over-invest here). Reads /benchmark
// once and renders it verbatim -- integrity panel, all seven baseline rows,
// the ablation table, bootstrap CIs. The XGBoost row's held_out is null (the
// panel refused every candidate before any held-out read) and MUST render as
// a visible "Refused" state with its reason rather than crash or blank --
// this is the exact regression Task 7 had to fix in the JS mockup.

export function Benchmark() {
  const { data: b, loading, error, reload } = useFetch(getBenchmark, []);

  if (loading) return <Loading label="benchmark" />;
  if (error) return <ErrorState label="benchmark" message={error} onRetry={reload} />;
  if (!b) return <EmptyState>No data.</EmptyState>;

  const signalEntries = Object.entries(b.single_signal_max_f1).sort((a, c) => c[1] - a[1]);
  const topSignal = signalEntries[0]?.[1] ?? 1;
  const shipped = b.baselines.baselines.find((r) => r.baseline === "ring_score");
  const shippedF1 = shipped?.held_out?.f1 ?? 0;
  const sortedBaselines = [...b.baselines.baselines].sort(
    (x, y) => (y.held_out ? y.held_out.f1 : -1) - (x.held_out ? x.held_out.f1 : -1),
  );
  const fullAblation = b.ablations.configurations.find((c) => c.group === "full");
  const restAblations = b.ablations.configurations
    .filter((c) => c.group !== "full")
    .sort((x, y) => x.delta_f1 - y.delta_f1);

  return (
    <div className="flex flex-col gap-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border border-line bg-bg px-3 py-2 text-ink-2">
        <span>
          F1 <b className="num">{fmt.f4(b.primary.f1)}</b>
        </span>
        <span>
          Precision <b className="num">{fmt.f4(b.primary.precision)}</b>
        </span>
        <span>
          Recall <b className="num">{fmt.f4(b.primary.recall)}</b>
        </span>
        <span>
          FP rate <b className="num">{fmt.pct2(b.primary.false_positive_rate)}</b>
        </span>
        <span className="text-good">
          Rings recovered <b className="num">{b.primary.rings_recovered}</b>/<b className="num">{b.primary.rings_in_test}</b> (
          {fmt.pct1(b.primary.ring_recovery_rate)})
        </span>
        <span
          className={`ml-auto px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
            b.panel.verdict === "PASS" ? "bg-good text-white" : "bg-red text-white"
          }`}
        >
          Integrity panel: {b.panel.verdict}
        </span>
        <span className="num text-[11px] text-ink-3">cfg {b.config_fingerprint}</span>
      </div>

      <p className="border border-line-2 bg-fill p-2.5 text-[11px] leading-relaxed text-ink-2">
        <b className="text-ink">Ground truth rule:</b> {b.ground_truth_rule}
      </p>

      <p className="border border-line-2 bg-fill p-2.5 text-[11px] leading-relaxed text-ink-2">
        <b className="text-ink">Secondary metric ({b.secondary.unit}-level, {fmt.int(b.secondary.scored_accounts)} scored):</b>{" "}
        precision <b className="num">{fmt.f4(b.secondary.precision)}</b> · recall{" "}
        <b className="num">{fmt.f4(b.secondary.recall)}</b> · F1 <b className="num">{fmt.f4(b.secondary.f1)}</b> · FP rate{" "}
        <b className="num">{fmt.pct2(b.secondary.false_positive_rate)}</b> · tp/fp/tn/fn{" "}
        <b className="num">
          {b.secondary.tp}/{b.secondary.fp}/{b.secondary.tn}/{b.secondary.fn}
        </b>
        . {b.secondary.note}
      </p>

      {/* Integrity panel checks */}
      <section className="border border-line bg-bg">
        <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
          Non-triviality panel -- computed on {b.panel.computed_on}
        </h2>
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-fill text-right text-[10px] uppercase tracking-wide text-ink-3">
              <th className="border-b border-line px-2 py-1 text-left">Check</th>
              <th className="border-b border-line px-2 py-1">Value</th>
              <th className="border-b border-line px-2 py-1">Bound</th>
              <th className="border-b border-line px-2 py-1">Status</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(b.panel.checks).map(([name, c]) => (
              <tr key={name} className="border-b border-line-2">
                <td className="px-2 py-1">{name.replace(/_/g, " ")}</td>
                <td className="num px-2 py-1 text-right">
                  {c.value === null ? "—" : Array.isArray(c.value) ? c.value.join(", ") : String(c.value)}
                </td>
                <td className="num px-2 py-1 text-right text-ink-2">{c.bound}</td>
                <td className="px-2 py-1 text-right">
                  <span
                    className={`px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                      c.status === "PASS" ? "bg-good text-white" : "bg-amber text-white"
                    }`}
                  >
                    {c.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Single-signal max F1 */}
      <section className="border border-line bg-bg">
        <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
          Single-signal max F1 -- no signal should separate perfectly alone
        </h2>
        <div className="flex flex-col gap-1 p-2.5">
          {signalEntries.map(([name, f1]) => (
            <div key={name} className="grid grid-cols-[180px_1fr_60px] items-center gap-2">
              <span className="text-ink-2">{name.replace(/_/g, " ")}</span>
              <div className="h-3 bg-fill-2">
                <div className={`h-full ${f1 === topSignal ? "bg-red" : "bg-quiet"}`} style={{ width: `${f1 * 100}%` }} />
              </div>
              <span className="num text-right font-semibold">{f1.toFixed(4)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Baselines */}
      <section className="border border-line bg-bg">
        <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
          Baseline sanity checks -- all seven rows, ordered by held-out F1
        </h2>
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-fill text-right text-[10px] uppercase tracking-wide text-ink-3">
              <th className="border-b border-line px-2 py-1 text-left">Baseline</th>
              <th className="border-b border-line px-2 py-1">Uses graph</th>
              <th className="border-b border-line px-2 py-1">Operating point</th>
              <th className="border-b border-line px-2 py-1">Held-out F1</th>
              <th className="border-b border-line px-2 py-1">FP rate</th>
              <th className="border-b border-line px-2 py-1">Hard-negatives-only F1</th>
            </tr>
          </thead>
          <tbody>
            {sortedBaselines.map((r) => (
              <BaselineTableRow key={r.baseline} row={r} shippedF1={shippedF1} />
            ))}
          </tbody>
        </table>
      </section>

      {/* Ablations */}
      <section className="border border-line bg-bg">
        <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
          Leave-one-group-out ablation -- full model first, then most damaging removal first
        </h2>
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-fill text-right text-[10px] uppercase tracking-wide text-ink-3">
              <th className="border-b border-line px-2 py-1 text-left">Group removed</th>
              <th className="border-b border-line px-2 py-1">Weight removed</th>
              <th className="border-b border-line px-2 py-1">Held-out F1</th>
              <th className="border-b border-line px-2 py-1">Delta F1</th>
              <th className="border-b border-line px-2 py-1">Hard-negatives-only F1</th>
            </tr>
          </thead>
          <tbody>
            {fullAblation && (
              <tr className="border-b border-line-2 bg-fill font-semibold">
                <td className="px-2 py-1.5">
                  <div>— full model</div>
                  <div className="text-[11px] font-normal text-ink-2">
                    All eight signals · threshold {fullAblation.threshold} · rings{" "}
                    {fullAblation.held_out.rings_recovered}/{fullAblation.held_out.rings_in_test}
                  </div>
                </td>
                <td className="px-2 py-1.5 text-right">—</td>
                <td className="num px-2 py-1.5 text-right">{fullAblation.held_out.f1.toFixed(4)}</td>
                <td className="px-2 py-1.5 text-right">—</td>
                <td className="num px-2 py-1.5 text-right">{fullAblation.held_out_hard_negatives_only.f1.toFixed(4)}</td>
              </tr>
            )}
            {restAblations.map((c) => (
              <tr key={c.group} className="border-b border-line-2">
                <td className="px-2 py-1.5">
                  <div className="font-semibold">{c.group.replace(/_/g, " ")}</div>
                  <div className="text-[11px] text-ink-2">
                    {c.signals_removed.join(", ")}
                    {c.identical_to_full ? " · identical to full by construction (weight already 0.0)" : ` · threshold ${c.threshold}`}
                  </div>
                </td>
                <td className="num px-2 py-1.5 text-right">{c.weight_removed.toFixed(4)}</td>
                <td className="num px-2 py-1.5 text-right">{c.held_out.f1.toFixed(4)}</td>
                <td
                  className={`num px-2 py-1.5 text-right ${
                    c.delta_f1 === 0 ? "" : c.delta_f1 < 0 ? "text-red" : "text-good"
                  }`}
                >
                  {c.delta_f1 > 0 ? "+" : ""}
                  {c.delta_f1.toFixed(4)}
                </td>
                <td className="num px-2 py-1.5 text-right">{c.held_out_hard_negatives_only.f1.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="grid grid-cols-12 gap-2">
        {/* Bootstrap CI */}
        <section className="col-span-12 border border-line bg-bg lg:col-span-6">
          <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
            Bootstrap confidence intervals -- reporting only, not a second read
          </h2>
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-fill text-right text-[10px] uppercase tracking-wide text-ink-3">
                <th className="border-b border-line px-2 py-1 text-left">Metric</th>
                <th className="border-b border-line px-2 py-1">Point</th>
                <th className="border-b border-line px-2 py-1">95% CI</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(b.bootstrap_ci.metrics as Record<string, { point_estimate: number; ci_low: number; ci_high: number }>).map(
                ([name, m]) => (
                  <tr key={name} className="border-b border-line-2">
                    <td className="px-2 py-1">{name.replace(/_/g, " ")}</td>
                    <td className="num px-2 py-1 text-right font-semibold">{m.point_estimate.toFixed(4)}</td>
                    <td className="num px-2 py-1 text-right text-ink-2">
                      [{m.ci_low.toFixed(4)}, {m.ci_high.toFixed(4)}]
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
          <p className="p-2.5 text-[11px] text-ink-3">
            n_resamples {String((b.bootstrap_ci as Record<string, unknown>).n_resamples ?? "")}, percentile bootstrap.
          </p>
        </section>

        {/* Weight search candidates */}
        <section className="col-span-12 border border-line bg-bg lg:col-span-6">
          <h2 className="border-b border-line bg-ink px-2.5 py-1 text-[11px] font-semibold text-white">
            Weight-search candidates
          </h2>
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-fill text-right text-[10px] uppercase tracking-wide text-ink-3">
                <th className="border-b border-line px-2 py-1 text-left">Policy</th>
                <th className="border-b border-line px-2 py-1">Verdict</th>
                <th className="border-b border-line px-2 py-1">Expected loss</th>
                <th className="border-b border-line px-2 py-1">Status</th>
              </tr>
            </thead>
            <tbody>
              {b.weight_search.candidates.map((c) => (
                <tr key={c.policy} className="border-b border-line-2 align-top">
                  <td className="px-2 py-1.5">
                    <div className="num font-semibold">{c.policy}</div>
                    {c.reason && <div className="text-[11px] text-ink-2">{c.reason}</div>}
                  </td>
                  <td className={`px-2 py-1.5 text-right ${c.panel_verdict === "FAIL" ? "text-red" : ""}`}>
                    {c.panel_verdict}
                  </td>
                  <td className="num px-2 py-1.5 text-right">
                    {c.expected_loss == null ? "—" : fmt.money(c.expected_loss)}
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <span
                      className={`px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        c.feasible ? "bg-good text-white" : "bg-fill-2 text-ink-2"
                      }`}
                    >
                      {c.feasible ? (c.policy === "A_baseline" ? "Kept" : "Tied") : "Refused"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <p className="border border-line-2 bg-fill p-2.5 text-[11px] text-ink-3">
        Reproducibility: seed {String(b.reproducibility.seed)} · python {String(b.reproducibility.python_version)} ·{" "}
        {String(b.reproducibility.note)}
      </p>
    </div>
  );
}

function BaselineTableRow({ row, shippedF1 }: { row: BaselineRow; shippedF1: number }) {
  const h = row.held_out;
  const hard = row.held_out_hard_negatives_only;
  const beatsShipped = h && row.baseline !== "ring_score" && h.f1 >= shippedF1;
  const op = row.cutoff != null ? `${row.direction === ">=" ? "≥" : "≤"} ${row.cutoff}` : row.threshold != null ? `≥ ${row.threshold}` : "—";

  return (
    <tr className="border-b border-line-2 align-top">
      <td className="px-2 py-1.5">
        <div className="num font-semibold">{row.baseline}</div>
        <div className="text-[11px] text-ink-2">
          {row.description}
          {!h && row.status ? ` — ${row.status}` : ""}
        </div>
      </td>
      <td className="px-2 py-1.5 text-right">{String(row.uses_graph)}</td>
      <td className="num px-2 py-1.5 text-right">{op}</td>
      <td className={`num px-2 py-1.5 text-right ${beatsShipped ? "font-bold text-red" : ""}`}>
        {h ? (
          h.f1.toFixed(4)
        ) : (
          <span className="bg-fill-2 px-1.5 py-0.5 text-[10px] font-bold uppercase text-ink-2">Refused</span>
        )}
      </td>
      <td className="num px-2 py-1.5 text-right">{h ? fmt.pct2(h.false_positive_rate) : "—"}</td>
      <td className={`num px-2 py-1.5 text-right ${hard && hard.f1 >= 1 ? "font-bold text-red" : ""}`}>
        {hard ? hard.f1.toFixed(4) : "—"}
      </td>
    </tr>
  );
}
