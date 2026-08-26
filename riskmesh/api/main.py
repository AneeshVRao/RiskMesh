"""FastAPI app assembly.  Run:  uvicorn riskmesh.api.main:app --reload

Artifacts load once at startup and the fingerprint check runs there, so a
mixed-vintage set fails the process rather than a request. That is deliberate:
an API quietly serving eval_report from one run and components.csv from another
would be wrong in a way no endpoint could detect.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .artifacts import Artifacts
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading here means a mixed-vintage artifact set fails the process at
    # startup rather than surfacing as a wrong number in a response.
    app.state.artifacts = Artifacts()
    yield


app = FastAPI(
    title="RiskMesh",
    description="Read-only API over the frozen Tier 0/Tier 1 benchmark artifacts. "
                "Scores are never recomputed live.",
    version="1.0.0",
    lifespan=lifespan,
)

# The mockups are opened from file:// or a static server during the demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    arts = app.state.artifacts
    return {"status": "ok",
            "config_fingerprint": arts.fingerprint,
            "components": len(arts.components),
            "band": arts.band}
