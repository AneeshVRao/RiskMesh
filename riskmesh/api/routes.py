"""HTTP routing. Thin by design -- every body comes from `payloads`.

The 8 endpoints named in the PRD. Six are pure reads of frozen artifacts, one
derives a response from them, and exactly one writes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import audit, payloads

router = APIRouter()


def _arts(request: Request):
    return request.app.state.artifacts


def _found(value, component_id: str):
    if value is None:
        raise HTTPException(404, f"unknown component {component_id!r}")
    return value


@router.get("/rings")
def get_rings(request: Request, split: str = payloads.DEFAULT_SPLIT,
              action: str | None = None):
    return payloads.rings(_arts(request), split=split, action=action)


@router.get("/rings/{component_id}")
def get_ring(request: Request, component_id: str):
    return _found(payloads.ring(_arts(request), component_id), component_id)


@router.get("/rings/{component_id}/evidence")
def get_evidence(request: Request, component_id: str):
    return _found(payloads.evidence(_arts(request), component_id), component_id)


class ReviewIn(BaseModel):
    action: str = Field(..., description="allow | watch | review | escalate")
    analyst: str = "demo"
    note: str | None = None


@router.post("/rings/{component_id}/review", status_code=201)
def post_review(request: Request, component_id: str, body: ReviewIn):
    """Appends to the audit trail. Blocks nothing, changes no frozen artifact.

    The UI says "written to audit trail - no auto-block" under the action bar;
    this endpoint is what makes that literally true rather than aspirational.
    """
    arts = _arts(request)
    ev = _found(payloads.evidence(arts, component_id), component_id)
    try:
        rec = audit.record(
            component_id, body.action,
            score=ev["score"], band=arts.band,
            system_action=ev["action"], fingerprint=arts.fingerprint,
            snapshot={"signals": ev["decomposition"]["signals"],
                      "summary": ev["summary"]},
            analyst=body.analyst, note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return audit.append(rec)


@router.get("/metrics")
def get_metrics(request: Request):
    return payloads.metrics(_arts(request))


@router.get("/threshold-analysis")
def get_threshold_analysis(request: Request):
    return payloads.threshold_analysis(_arts(request))


@router.get("/benchmark")
def get_benchmark(request: Request):
    return payloads.benchmark(_arts(request))


class ExplainIn(BaseModel):
    component_id: str
    audience: str = "analyst"


@router.post("/explain")
def post_explain(request: Request, body: ExplainIn):
    """Grounded narration. Currently the deterministic fallback only.

    The request carries no numbers by design: the caller names a component and
    the server reads the frozen evidence itself, so a client cannot induce a
    narration the detector never supported.

    No model is wired. Per the PRD's Tier 1 fallback rule this is the first
    thing to cut, and the deterministic composition below -- the scorer's own
    `detail` strings, in contribution order -- is already what the mockups show.
    """
    arts = _arts(request)
    ev = _found(payloads.evidence(arts, body.component_id), body.component_id)
    weighted = [s for s in ev["decomposition"]["signals"] if s["weighted"]]
    text = ". ".join(s["detail"] for s in weighted[:3]) + "."
    return {
        "component_id": body.component_id,
        "text": text,
        "grounded_in": [s["name"] for s in weighted[:3]],
        "config_fingerprint": arts.fingerprint,
        "fallback_used": True,
        "note": "deterministic composition of frozen detail strings; no model called",
    }
