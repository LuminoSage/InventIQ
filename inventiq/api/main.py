"""HTTP API for the buying desk. Interactive docs are served at /docs.

Run:  python -m inventiq serve        (or: uvicorn inventiq.api.main:app)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..catalog import BY_ID, RISK
from ..engine import DEFAULT_BUDGET, Engine
from .store import DecisionStore

WEB_DIST = Path(os.environ.get("INVENTIQ_WEB_DIST", Path(__file__).resolve().parents[2] / "web" / "dist"))
DB_PATH = os.environ.get("INVENTIQ_DB", str(Path(__file__).resolve().parents[2] / "data" / "decisions.db"))

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["engine"] = state.get("engine") or Engine()
    state["store"] = state.get("store") or DecisionStore(DB_PATH)
    yield


app = FastAPI(
    title="InventIQ API",
    version=__version__,
    description="Pre-buy planning for travel inventory: range forecasts, 10,000 joint futures, "
    "a budget optimiser with a CVaR risk term, and a buyer approval log.",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Risk = Literal["cautious", "balanced", "bold"]


class PlanRequest(BaseModel):
    budget: float = Field(DEFAULT_BUDGET, ge=0, le=1e9, description="Cash available for pre-buys, in rupees")
    risk: Risk = "balanced"
    exact: bool = Field(False, description="Also solve the mixed-integer programme with SCIP (slower)")


class DecisionRequest(BaseModel):
    option_id: str
    action: Literal["approve", "edit", "reject", "undo"]
    hard: int | None = Field(None, ge=0)
    allot: int | None = Field(None, ge=0)
    budget: float | None = None
    risk: Risk | None = None
    note: str | None = Field(None, max_length=500)


def engine() -> Engine:
    return state["engine"]


def store() -> DecisionStore:
    return state["store"]


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "version": __version__}


@app.get("/api/meta", tags=["system"])
def meta():
    return engine().meta()


@app.get("/api/options", tags=["forecast"])
def options():
    """The twelve options with their range forecast, booking signals and unit economics."""
    return engine().options()


@app.get("/api/backtest", tags=["forecast"])
def backtest():
    """Out-of-sample accuracy of the Demand Radar on the last finished season."""
    return engine().backtest()


@app.get("/api/correlation", tags=["forecast"])
def correlation():
    """Correlation of forecast errors between options, used to draw joint futures."""
    return engine().correlation()


@app.post("/api/plan", tags=["plan"])
def plan(req: PlanRequest):
    """Optimise the season's buys for a budget and risk profile. Approved, edited and rejected options
    are locked as decided; the rest are re-planned around them."""
    return engine().plan(req.budget, req.risk, store().forced(), req.exact)


@app.get("/api/plan", tags=["plan"])
def plan_get(budget: float = Query(DEFAULT_BUDGET, ge=0, le=1e9), risk: Risk = "balanced"):
    return engine().plan(budget, risk, store().forced())


@app.get("/api/decisions", tags=["decisions"])
def decisions():
    return {"current": store().current(), "log": store().log()}


@app.post("/api/decisions", tags=["decisions"], status_code=201)
def decide(req: DecisionRequest):
    if req.option_id not in BY_ID:
        raise HTTPException(404, f"unknown option {req.option_id!r}")
    o = BY_ID[req.option_id]
    if req.action in ("approve", "edit"):
        if req.hard is None or req.allot is None:
            raise HTTPException(422, "approve and edit need hard and allot")
        if req.hard > o.supply_cap:
            raise HTTPException(422, f"only {o.supply_cap} hard units are available for {o.name}")
        if req.allot > o.allot_cap:
            raise HTTPException(422, f"the supplier holds at most {o.allot_cap} allotment units for {o.name}")
    if req.risk is not None and req.risk not in RISK:
        raise HTTPException(422, "unknown risk profile")
    return store().add(req.option_id, req.action, req.hard, req.allot, req.budget, req.risk, req.note)


@app.delete("/api/decisions", tags=["decisions"])
def reset_decisions():
    store().clear()
    return {"cleared": True}


if WEB_DIST.is_dir():
    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        if path and f.is_file() and WEB_DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
