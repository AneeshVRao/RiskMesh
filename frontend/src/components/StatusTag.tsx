import type { Icon } from "@phosphor-icons/react";
import { CheckCircleIcon, EyeIcon, MagnifyingGlassIcon, WarningIcon } from "@phosphor-icons/react";
import type { AnalystAction } from "../api/types";

// PRD accessibility requirement: "Risk status must use text labels and icons
// in addition to color." Every status renders all three -- background tint,
// an icon, and the word itself -- so nothing here depends on color alone.
const META: Record<AnalystAction, { label: string; icon: Icon; bg: string; fg: string }> = {
  escalate: { label: "Escalate", icon: WarningIcon, bg: "bg-red", fg: "text-white" },
  review: { label: "Review", icon: MagnifyingGlassIcon, bg: "bg-amber", fg: "text-white" },
  watch: { label: "Watch", icon: EyeIcon, bg: "bg-ink-2", fg: "text-white" },
  allow: { label: "Allow", icon: CheckCircleIcon, bg: "bg-quiet", fg: "text-white" },
};

export function StatusTag({ action, size = "sm" }: { action: AnalystAction; size?: "sm" | "md" }) {
  const m = META[action];
  const Icon = m.icon;
  const pad = size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1 font-bold uppercase tracking-wide ${pad} ${m.bg} ${m.fg}`}
    >
      <Icon size={size === "sm" ? 10 : 12} weight="bold" aria-hidden />
      {m.label}
    </span>
  );
}

export function actionMeta(action: AnalystAction) {
  return META[action];
}
