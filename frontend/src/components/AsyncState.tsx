import type { ReactNode } from "react";
import { WarningCircleIcon, CircleNotchIcon } from "@phosphor-icons/react";

// Every async view needs these three states rendered explicitly -- a blank
// screen while loading, or a screen that silently keeps yesterday's numbers
// on a failed request, are both things this project's own README warns
// against ("a failed write cannot render as a good one" applies to reads too).

export function Loading({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="skeleton flex items-center gap-2 p-4 text-sm text-ink-3"
    >
      <CircleNotchIcon size={16} className="animate-spin" aria-hidden />
      Loading {label}...
    </div>
  );
}

export function ErrorState({ label, message, onRetry }: { label: string; message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col gap-2 p-4 text-sm text-red">
      <div className="flex items-center gap-2 font-semibold">
        <WarningCircleIcon size={16} weight="fill" aria-hidden />
        Could not load {label}
      </div>
      <div className="font-mono text-xs text-ink-2">{message}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 w-fit border border-line px-2 py-1 text-xs font-semibold text-ink hover:border-ink-3"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="p-4 text-sm text-ink-3">{children}</div>;
}
