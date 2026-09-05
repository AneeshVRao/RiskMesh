import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getEvidence, getRings } from "../api/client";
import { useFetch } from "../hooks/useFetch";
import { fmt } from "../format";
import { StatusTag } from "../components/StatusTag";
import { RingGraph, graphCaption } from "../components/RingGraph";
import { ActionBar } from "../components/ActionBar";
import { AuditTrail } from "../components/AuditTrail";
import { ExplainPanel } from "../components/ExplainPanel";
import { Loading, ErrorState, EmptyState } from "../components/AsyncState";
import type { EvidenceResponse, RingRow } from "../api/types";

const SHADES = ["#d81f26", "#a8171d", "#8f5400", "#b07a2e", "#5c6670", "#8a939c"];

export function Investigator() {
  const { componentId } = useParams();
  const navigate = useNavigate();

  // Picker: every non-allow component, grouped by disposition. Loaded once;
  // does not need to re-run when the selection changes.
  const { data: ringsData, loading: ringsLoading, error: ringsError, reload: reloadRings } = useFetch(
    () => getRings(),
    [],
  );

  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [evLoading, setEvLoading] = useState(false);
  const [evError, setEvError] = useState<string | null>(null);
  const [evReloadTick, setEvReloadTick] = useState(0);

  const flagged = ringsData ? ringsData.rings.filter((r) => r.action !== "allow") : [];

  // Redirect to the top-ranked flagged component when none is named in the
  // URL -- mirrors mockups/api.js's initInvestigator() opening on flagged[0].
  useEffect(() => {
    if (!componentId && flagged.length > 0) {
      navigate(`/investigator/${encodeURIComponent(flagged[0].component_id)}`, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [componentId, flagged.length]);

  useEffect(() => {
    if (!componentId) return;
    let cancelled = false;
    setEvLoading(true);
    setEvError(null);
    getEvidence(componentId)
      .then((ev) => {
        if (cancelled) return;
        setEvidence(ev);
        setEvLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setEvError(err instanceof Error ? err.message : String(err));
        setEvLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [componentId, evReloadTick]);

  if (ringsLoading) return <Loading label="component queue" />;
  if (ringsError) return <ErrorState label="component queue" message={ringsError} onRetry={reloadRings} />;
  if (!ringsData) return <EmptyState>No data.</EmptyState>;
  if (flagged.length === 0) return <EmptyState>No escalate/review components in this split.</EmptyState>;

  const group = (action: "escalate" | "review") => flagged.filter((r) => r.action === action);

  return (
    <div className="grid grid-cols-12 gap-2">
      {/* Picker */}
      <section className="col-span-12 border border-line bg-bg lg:col-span-3">
        <h2 className="flex border-b border-line text-[11px] font-semibold">
          <span className="bg-ink px-2.5 py-1 text-white">Components</span>
          <span className="ml-auto self-center px-2.5 font-mono text-[10px] font-normal text-ink-3">
            {flagged.length} flagged
          </span>
        </h2>
        <div className="max-h-[600px] overflow-auto">
          {(["escalate", "review"] as const).map((action) => {
            const rows = group(action);
            if (rows.length === 0) return null;
            return (
              <div key={action}>
                <div className="sticky top-0 border-b border-line bg-fill px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-ink-3">
                  {action === "escalate" ? "Escalate" : "Review"} · {rows.length}
                </div>
                {rows.map((r) => (
                  <PickerRow key={r.component_id} row={r} active={r.component_id === componentId} />
                ))}

              </div>
            );
          })}
        </div>
        <p className="border-t border-line-2 p-2.5 text-[11px] leading-relaxed text-ink-2">
          Allowed components are not listed here. Nothing is auto-blocked: escalation opens a case,
          it does not stop a payment.
        </p>
      </section>

      {/* Detail */}
      <section className="col-span-12 lg:col-span-9">
        {evLoading && <Loading label="component evidence" />}
        {evError && (
          <ErrorState
            label="component evidence"
            message={evError}
            onRetry={() => setEvReloadTick((t) => t + 1)}
          />
        )}
        {!evLoading && !evError && evidence && <Detail evidence={evidence} onRecorded={setEvidence} />}
      </section>
    </div>
  );
}

function PickerRow({ row, active }: { row: RingRow; active: boolean }) {
  return (
    <Link
      to={`/investigator/${encodeURIComponent(row.component_id)}`}
      aria-current={active ? "true" : undefined}
      className={`grid grid-cols-[1fr_auto] gap-x-2 gap-y-0.5 border-b border-line-2 px-2.5 py-1.5 text-xs no-underline ${
        active ? "bg-[#ffe0e0] shadow-[inset_3px_0_0_var(--color-red)]" : "hover:bg-[#fff8f8]"
      }`}
    >
      <span className="num text-[11px] font-semibold text-ink">{row.component_id}</span>
      <span className="num text-right text-[11px] font-semibold">{fmt.f4(row.score)}</span>
      <span className="col-span-1 text-[10px] text-ink-3">
        {row.label || "family"} · {row.size} accounts
      </span>
      <span className="col-span-1 justify-self-end">
        <StatusTag action={row.action} />
      </span>
    </Link>
  );
}

function Detail({
  evidence: ev,
  onRecorded,
}: {
  evidence: EvidenceResponse;
  onRecorded: (fresh: EvidenceResponse) => void;
}) {
  const ringLabel = ev.summary.ring_id || (ev.summary.has_family ? "family" : "unlabelled");
  const weighted = ev.decomposition.signals.filter((s) => s.weighted);
  const maxContribution = Math.max(...ev.decomposition.signals.map((s) => s.contribution), 1e-9);

  return (
    <div className="flex flex-col gap-2">
      <div className="border border-line bg-bg">
        <h2 className="flex flex-wrap items-center gap-2 border-b border-line px-2.5 py-1.5">
          <span className="num text-sm font-bold">{ev.component_id}</span>
          <span className="text-xs text-ink-3">
            {ringLabel} · {ev.summary.size} accounts · rank {ev.rank.position} of {ev.rank.of}
          </span>
          <span className="ml-auto">
            <StatusTag action={ev.action} size="md" />
          </span>
        </h2>

        <div className="border-b border-line-2 bg-fill p-2.5">
          <RingGraph componentId={ev.component_id} graph={ev.graph} />
        </div>
        <p className="border-b border-line-2 p-2.5 text-[11px] leading-relaxed text-ink-2">
          {graphCaption(ev)}
        </p>

        <ActionBar componentId={ev.component_id} audit={ev.audit} onRecorded={onRecorded} />
      </div>

      <ExplainPanelHost componentId={ev.component_id} />

      {/* Score decomposition */}
      <div className="border border-line bg-bg">
        <h2 className="flex border-b border-line text-[11px] font-semibold">
          <span className="bg-ink px-2.5 py-1 text-white">Score decomposition</span>
          <span className="ml-auto self-center px-2.5 font-mono text-[10px] font-normal text-ink-3">
            {fmt.f4(ev.decomposition.score)} = sum of w times x
          </span>
        </h2>
        <div className="p-2.5">
          <div className="flex h-7 overflow-hidden border border-line">
            {weighted.map((s, i) => (
              <div
                key={s.name}
                style={{ flex: Math.max(s.contribution, 0.0001), background: SHADES[i % SHADES.length] }}
              />
            ))}
            <div style={{ flex: Math.max(ev.decomposition.headroom, 0.0001), background: "#eceef1" }} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-ink-2">
            {weighted.map((s, i) => (
              <span key={s.name} className="inline-flex items-center gap-1">
                <i className="inline-block h-2 w-2" style={{ background: SHADES[i % SHADES.length] }} />
                {s.name.replace(/_/g, " ")} <b className="num">{s.contribution.toFixed(4)}</b>
              </span>
            ))}
            <span className="inline-flex items-center gap-1">
              <i className="inline-block h-2 w-2 bg-fill-2" />
              headroom <b className="num">{ev.decomposition.headroom.toFixed(4)}</b>
            </span>
          </div>
        </div>

        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-fill text-right text-[10px] uppercase tracking-wide text-ink-3">
              <th className="border-b border-line px-2 py-1 text-left">Signal</th>
              <th className="border-b border-line px-2 py-1">Raw</th>
              <th className="border-b border-line px-2 py-1">Norm</th>
              <th className="border-b border-line px-2 py-1">Weight</th>
              <th className="border-b border-line px-2 py-1">Contrib</th>
            </tr>
          </thead>
          <tbody>
            {ev.decomposition.signals.map((s) => (
              <tr key={s.name} className={`border-b border-line-2 ${s.weighted ? "" : "text-ink-3"}`}>
                <td className="px-2 py-1">
                  <div className="font-semibold">{s.name.replace(/_/g, " ")}</div>
                  <div className="text-[11px] text-ink-2">
                    {s.detail}
                    {s.note ? ` (zero-weighted — ${s.note})` : ""}
                  </div>
                </td>
                <td className="num px-2 py-1 text-right">
                  {typeof s.raw === "number" && !Number.isInteger(s.raw) ? s.raw.toFixed(4) : s.raw}
                </td>
                <td className="num px-2 py-1 text-right">{s.normalized.toFixed(4)}</td>
                <td className="num px-2 py-1 text-right">{s.weight.toFixed(4)}</td>
                <td className="num px-2 py-1 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="h-1.5 w-16 bg-fill-2">
                      <div
                        className={`h-full ${s.weighted ? "bg-red" : "bg-line"}`}
                        style={{ width: `${Math.max(2, (s.contribution / maxContribution) * 100)}%` }}
                      />
                    </div>
                    {s.contribution.toFixed(4)}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-fill font-semibold">
              <td className="px-2 py-1">Component score</td>
              <td colSpan={3}></td>
              <td className="num px-2 py-1 text-right">{ev.decomposition.score.toFixed(4)}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {ev.comparison && <Comparison comparison={ev.comparison} />}

      <div className="border border-line bg-bg">
        <h2 className="flex border-b border-line text-[11px] font-semibold">
          <span className="bg-ink px-2.5 py-1 text-white">Audit trail</span>
          <span className="ml-auto self-center px-2.5 font-mono text-[10px] font-normal text-ink-3">
            evidence snapshot per action
          </span>
        </h2>
        <AuditTrail audit={ev.audit} />
      </div>
    </div>
  );
}

function ExplainPanelHost({ componentId }: { componentId: string }) {
  return (
    <div className="border border-line bg-bg">
      <ExplainPanel componentId={componentId} />
    </div>
  );
}

function Comparison({ comparison: cmp }: { comparison: NonNullable<EvidenceResponse["comparison"]> }) {
  const rows: [string, keyof typeof cmp.subject, (v: never) => string][] = [
    ["Accounts", "accounts", (v: number) => fmt.int(v)],
    ["Median account age", "median_account_age_days", (v: number) => `${v} d`],
    ["Burst convergence", "burst", (v: string) => v],
    ["Max accounts per IP", "max_accounts_per_ip", (v: number) => fmt.int(v)],
    ["Shared instruments", "shared_instruments", (v: number) => fmt.int(v)],
    ["Refund rate", "refund_rate", (v: number) => fmt.pct1(v)],
    ["Exposure", "exposure", (v: number) => fmt.money(v)],
  ];
  const hot = new Set(cmp.separating_fields);
  return (
    <div className="border border-line bg-bg">
      <h2 className="flex border-b border-line text-[11px] font-semibold">
        <span className="bg-red px-2.5 py-1 text-white">Ring vs household</span>
        <span className="ml-auto self-center px-2.5 font-mono text-[10px] font-normal text-ink-3">
          why this one escalates and that one waits
        </span>
      </h2>
      <div className="grid grid-cols-1 divide-y divide-line-2 md:grid-cols-2 md:divide-x md:divide-y-0">
        {(["subject", "peer"] as const).map((side) => {
          const d = cmp[side];
          return (
            <div key={side} className="p-2.5">
              <h3 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-2">
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${side === "subject" ? "bg-red" : "bg-amber"}`}
                />
                {d.component_id} · {d.label || "family"} · {d.action} {fmt.f4(d.score)}
              </h3>
              <dl className="grid grid-cols-[1fr_auto] gap-x-2 gap-y-0.5 text-[11px]">
                {rows.map(([label, key, format]) => (
                  <div key={key} className="contents">
                    <dt className="text-ink-3">{label}</dt>
                    <dd
                      className={`num font-semibold ${
                        hot.has(key as string) ? (side === "subject" ? "text-red" : "text-amber") : "text-ink-2"
                      }`}
                    >
                      {format(d[key] as never)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          );
        })}
      </div>
    </div>
  );
}
