import type { AuditRecord } from "../api/types";
import { StatusTag } from "./StatusTag";

export function AuditTrail({ audit }: { audit: AuditRecord[] }) {
  if (audit.length === 0) {
    return (
      <p className="p-3 text-sm text-ink-3">
        No analyst actions recorded yet. Actions post to <span className="num">/rings/&#123;id&#125;/review</span>{" "}
        and append to <span className="num">out/audit_log.jsonl</span>.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-line-2 text-xs">
      {audit.map((a, i) => (
        <li key={i} className="flex flex-col gap-1 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="num text-ink-3">{a.ts}</span>
            <span className="num font-semibold">{a.component_id}</span>
            <span>
              score <span className="num font-semibold">{a.score.toFixed(4)}</span>
            </span>
            <span className="num text-ink-3">
              band {a.band.t_lo}/{a.band.t_hi}
            </span>
            <StatusTag action={a.analyst_action} />
            {!a.agreed_with_system && (
              <span className="text-red">overrode system {a.system_action}</span>
            )}
          </div>
          <div className="num text-ink-3">
            evidence snapshot · {a.evidence_snapshot.signals?.length ?? 0} signals · sha{" "}
            {a.evidence_sha256.slice(0, 12)}
          </div>
        </li>
      ))}
    </ul>
  );
}
