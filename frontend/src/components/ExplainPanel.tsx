import { useEffect, useRef, useState } from "react";
import { WarningCircleIcon } from "@phosphor-icons/react";
import { postExplain } from "../api/client";

// PRD Flow 3 (LLM-failure degradation): this panel is mounted by the parent
// AFTER the deterministic evidence, graph, and score are already on screen,
// and it never blocks them -- it fetches /explain independently in its own
// effect and renders its own loading/error state locally. If /explain fails
// or is slow, everything else on the Investigator screen stays fully usable;
// this panel just says narration is unavailable.
//
// A `current` guard drops a stale response: clicking to a different
// component while a slow /explain is in flight must not print the previous
// component's sentence under the new component's numbers.
export function ExplainPanel({ componentId }: { componentId: string }) {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "ok"; text: string; groundedIn: string[]; fallback: boolean }
    | { kind: "error"; message: string }
  >({ kind: "loading" });
  const current = useRef(componentId);

  useEffect(() => {
    current.current = componentId;
    setState({ kind: "loading" });
    postExplain(componentId)
      .then((x) => {
        if (current.current !== componentId) return; // stale, drop it
        setState({ kind: "ok", text: x.text, groundedIn: x.grounded_in, fallback: x.fallback_used });
      })
      .catch((err: unknown) => {
        if (current.current !== componentId) return;
        setState({ kind: "error", message: err instanceof Error ? err.message : String(err) });
      });
  }, [componentId]);

  return (
    <div className={`border-b border-line-2 bg-fill p-3 text-sm leading-relaxed ${state.kind === "error" ? "text-red" : "text-ink-2"}`}>
      <span className="font-semibold text-ink">Why: </span>
      {state.kind === "loading" && <span className="skeleton">Reading frozen evidence...</span>}
      {state.kind === "ok" && <span>{state.text}</span>}
      {state.kind === "error" && (
        <span className="inline-flex items-center gap-1">
          <WarningCircleIcon size={14} weight="fill" aria-hidden />
          Explanation unavailable — deterministic evidence below is unaffected.
        </span>
      )}
      <div className="num mt-1 text-[10px] text-ink-3">
        {state.kind === "ok" &&
          `grounded in ${state.groundedIn.join(", ")} · ${
            state.fallback ? "deterministic fallback, no model called" : "model narration"
          }`}
        {state.kind === "error" && `narration unavailable — ${state.message}`}
      </div>
    </div>
  );
}
