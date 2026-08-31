"""The only reader of frozen artifacts. Stdlib only, no web framework.

Everything the API serves already exists on disk. This module loads it once,
asserts the whole set came from one pipeline run, and hands typed-ish dicts to
the payload builders. Nothing else under `api/` opens a file for reading.

`riskmesh.score` is deliberately not imported here or anywhere under `api/`. A
live re-score is the one thing this service must never do: it would let the
number on screen drift from the number in the frozen record, and the project's
whole discipline rests on those being the same number.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "out"

# Every artifact the API reads, and where its fingerprint lives inside it.
_FINGERPRINTED = {
    "eval_report.json": ("config_fingerprint",),
    "threshold.json": ("config_fingerprint",),
    "integrity_report.json": ("reproducibility", "config_fingerprint"),
    "abstention_policy.json": ("config_fingerprint",),
    "weight_policy.json": ("config_fingerprint",),
    "baselines.json": ("config_fingerprint",),
    "ablations.json": ("config_fingerprint",),
    "xgboost_policy.json": ("config_fingerprint",),
    "graphsage_policy.json": ("config_fingerprint",),
}
_PLAIN = ("graph_edges.json",)

SIGNAL_ORDER = ("device_sharing", "temporal_burst", "instrument_sharing",
                "instrument_pool_concentration", "failure_refund_rate",
                "ip_sharing", "account_newness", "merchant_concentration")


class ArtifactsNotFrozen(RuntimeError):
    """Raised when the artifacts on disk did not come from one pipeline run.

    Raise, don't warn -- the same rule select_threshold() and
    select_abstention_band() already follow. An API serving eval_report from one
    run and components.csv from another is silently, invisibly wrong, and a
    warning in a log nobody reads is not a safeguard.
    """


def _dig(obj: dict, path: tuple[str, ...]) -> str | None:
    cur: object = obj
    for key in path:
        cur = cur.get(key) if isinstance(cur, dict) else None
    return cur if isinstance(cur, str) else None


class Artifacts:
    """One pipeline run's outputs, loaded once and held."""

    def __init__(self, out: Path = OUT) -> None:
        self.out = out
        missing = [n for n in (*_FINGERPRINTED, *_PLAIN, "components.csv")
                   if not (out / n).exists()]
        if missing:
            raise ArtifactsNotFrozen(
                f"missing from {out}: {', '.join(sorted(missing))}. "
                f"Run `python -m riskmesh` to regenerate."
            )

        self.json: dict[str, dict] = {
            name: json.loads((out / name).read_text(encoding="utf-8"))
            for name in (*_FINGERPRINTED, *_PLAIN)
        }
        self.fingerprint = self._assert_one_run()
        self.components = self._load_components(out / "components.csv")
        self.by_id = {c["component_id"]: c for c in self.components}

    def _assert_one_run(self) -> str:
        seen = {name: _dig(self.json[name], path)
                for name, path in _FINGERPRINTED.items()}
        distinct = set(seen.values())
        if len(distinct) != 1 or None in distinct:
            detail = "; ".join(f"{n}={v}" for n, v in sorted(seen.items()))
            raise ArtifactsNotFrozen(
                f"artifacts disagree on config_fingerprint -- {detail}. "
                f"These files did not come from one pipeline run; re-run "
                f"`python -m riskmesh` rather than serving a mixed vintage."
            )
        only = distinct.pop()
        assert only is not None  # guarded by the check above
        return only

    @staticmethod
    def _load_components(path: Path) -> list[dict]:
        rows = []
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                row = {
                    "component_id": r["component_id"],
                    "split": r["split"],
                    "size": int(r["size"]),
                    "n_txns": int(r["n_txns"]),
                    "exposure": float(r["exposure"]),
                    "score": float(r["score"]),
                    "is_positive": bool(int(r["is_positive"])),
                    "ring_id": r["ring_id"] or None,
                    "has_family": bool(int(r["has_family"])),
                    "signals": {},
                }
                for name in SIGNAL_ORDER:
                    raw = r[f"{name}_raw"]
                    row["signals"][name] = {
                        "raw": float(raw) if raw not in ("", None) else 0.0,
                        "normalized": float(r[f"{name}_norm"]),
                        "detail": r[f"{name}_detail"],
                    }
                rows.append(row)
        return rows

    # --- accessors the payload builders use -------------------------------
    @property
    def weights(self) -> dict[str, float]:
        """The weights that actually produced the scores on disk.

        NOT weight_policy.json's copy. That record rounds to 4dp for display --
        its A_baseline weights sum to 0.9999, not 1.0 -- so recomputing
        contributions from it drifts from the frozen score by up to 6e-5 on 60
        of 100 components. Small, but it is exactly the drift between "the
        number on screen" and "the number in the frozen record" that this
        service exists to prevent.

        Config is the authoritative source: it is what score.py read, and it is
        what the config_fingerprint is derived from, so the startup assertion
        already guards it against drifting from the artifacts on disk. Importing
        it is not importing the scorer -- Config is inert data, and
        score_component() is still never called here.

        weight_policy.json remains the provenance record and is served verbatim
        by /benchmark, rounding and all.
        """
        from ..config import Config
        return dict(Config().weights)

    @property
    def band(self) -> dict[str, float]:
        result = self.json["abstention_policy.json"]["result"]
        return {"t_lo": result["t_lo"], "t_hi": result["t_hi"]}

    @property
    def costs(self) -> dict:
        return self.json["abstention_policy.json"]["costs"]

    def graph(self, component_id: str) -> dict | None:
        return self.json["graph_edges.json"].get(component_id)

    def in_split(self, split: str) -> list[dict]:
        return [c for c in self.components if c["split"] == split]
