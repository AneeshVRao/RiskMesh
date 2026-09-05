import { useState } from "react";
import { CheckCircleIcon, EyeIcon, MagnifyingGlassIcon, WarningIcon } from "@phosphor-icons/react";
import { getEvidence, postReview } from "../api/client";
import type { AnalystAction, AuditRecord, EvidenceResponse } from "../api/types";

// The one write path in the console. Defense-only: this posts to
// /rings/{id}/review and nothing else -- no account or transaction is ever
// blocked from here. Writes are NOT optimistic: after the POST succeeds, the
// evidence (and its audit tail) is RE-FETCHED from the server and that
// response replaces what's on screen. If the fetch after the write fails,
// the UI says so rather than assuming the write took -- mirroring
// mockups/api.js's wireActions(), which restores the last server-confirmed
// audit state on any error in this sequence.

const BUTTONS: { action: AnalystAction; label: string; icon: typeof WarningIcon; go?: boolean }[] = [
  { action: "escalate", label: "Escalate", icon: WarningIcon, go: true },
  { action: "watch", label: "Watch", icon: EyeIcon },
  { action: "review", label: "Manual Review", icon: MagnifyingGlassIcon },
  { action: "allow", label: "Allow", icon: CheckCircleIcon },
];

export function ActionBar({
  componentId,
  audit,
  onRecorded,
}: {
  componentId: string;
  audit: AuditRecord[];
  onRecorded: (fresh: EvidenceResponse) => void;
}) {
  const [posting, setPosting] = useState<AnalystAction | null>(null);
  const [hint, setHint] = useState<{ text: string; kind: "idle" | "done" | "bad" }>({
    text: "Writes to audit trail · no auto-block",
    kind: "idle",
  });

  const alreadyRecorded = new Set(audit.map((a) => a.analyst_action));

  async function act(action: AnalystAction) {
    setPosting(action);
    setHint({ text: "Recording...", kind: "idle" });
    try {
      await postReview(componentId, action);
      // Non-optimistic: re-read the evidence (and its audit tail) from the
      // server rather than patching local state with what we assume happened.
      const fresh = await getEvidence(componentId);
      onRecorded(fresh);
      const latest = fresh.audit[0];
      setHint({
        text: latest
          ? `Recorded ${action} · ${latest.ts} · out/audit_log.jsonl`
          : `Recorded ${action}`,
        kind: "done",
      });
    } catch (err) {
      setHint({
        text: `Not recorded — ${err instanceof Error ? err.message : String(err)}`,
        kind: "bad",
      });
    } finally {
      setPosting(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 bg-fill p-2">
      {BUTTONS.map(({ action, label, icon: Icon, go }) => {
        const disabled = posting !== null || alreadyRecorded.has(action);
        return (
          <button
            key={action}
            type="button"
            disabled={disabled}
            onClick={() => act(action)}
            title={alreadyRecorded.has(action) ? "already recorded for this component" : ""}
            className={`inline-flex items-center gap-1.5 border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
              go
                ? "border-red bg-red text-white hover:bg-red-dark disabled:border-line-2 disabled:bg-fill-2 disabled:text-ink-2"
                : "border-line bg-bg text-ink hover:border-ink-3 disabled:border-line-2 disabled:bg-fill-2 disabled:text-ink-2"
            } disabled:cursor-default`}
          >
            <Icon size={13} weight="bold" aria-hidden />
            {label}
          </button>
        );
      })}
      <span
        role="status"
        aria-live="polite"
        className={`ml-auto text-[10px] ${
          hint.kind === "done" ? "font-semibold text-ink" : hint.kind === "bad" ? "font-semibold text-red" : "text-ink-3"
        }`}
      >
        {hint.text}
      </span>
    </div>
  );
}
