"""The only writer in the service. Append-only JSONL.

Chosen over SQLite deliberately. The access pattern is append, then tail-N for
one component; the payload is a nested evidence snapshot that is already JSON;
and everything else in this project is an inspectable file on disk. Every
advantage SQLite has here -- indexes, transactions, concurrent writers, query
planning -- is an advantage over a problem this service does not have.

Switch to SQLite the moment any of these becomes true: more than one writer
process, a need to query across components, or mutable records. The whole
surface is `append()` and `tail()`, so that swap stays inside this file.

Durability: one `json.dumps` line, no embedded newlines, opened in "a" mode. A
torn write can only corrupt the final line, and the reader skips unparsable
lines rather than failing the request -- so a crash mid-append costs at most the
record being written, never the history. A deliberate ceiling, not an oversight.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import OUT

LOG = OUT / "audit_log.jsonl"
ACTIONS = ("allow", "watch", "review", "escalate")


def evidence_sha256(snapshot: dict) -> str:
    """Stable hash of the evidence as shown, so drift is detectable later."""
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record(component_id: str, analyst_action: str, *, score: float, band: dict,
           system_action: str, fingerprint: str, snapshot: dict,
           analyst: str = "demo", note: str | None = None) -> dict:
    """Build the audit record. Pure -- does not write."""
    if analyst_action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}, got {analyst_action!r}")
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component_id": component_id,
        "analyst_action": analyst_action,
        "analyst": analyst,
        "note": note,
        "score": score,
        "band": band,
        "system_action": system_action,
        "agreed_with_system": analyst_action == system_action,
        "config_fingerprint": fingerprint,
        "evidence_sha256": evidence_sha256(snapshot),
        # Embedded, not referenced. A foreign key into components.csv would
        # silently change meaning the next time the pipeline re-freezes; the
        # point of an audit trail is that it still says what the analyst saw.
        "evidence_snapshot": snapshot,
    }


def append(rec: dict, path: Path = LOG) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, separators=(",", ":"))
    assert "\n" not in line
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
    return rec


def tail(component_id: str | None = None, n: int = 20,
         path: Path = LOG) -> list[dict]:
    """Newest first. Unparsable lines are skipped, never raised."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn final line costs that record, not the history
        if component_id is None or rec.get("component_id") == component_id:
            out.append(rec)
    return out[::-1][:n]
