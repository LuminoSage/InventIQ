"""The InventIQ engine: data -> Demand Radar -> joint futures -> Portfolio Optimizer -> Risk Shield.

``Engine`` builds everything once (about 20 seconds; cached on disk afterwards) and then answers plan
requests in about a second. Plans are cached by budget, risk profile and locked decisions.
"""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .catalog import BY_ID, CVAR_ALPHA, OPTIONS, RISK, SEASON, TODAY
from .data import synth
from .forecast import radar
from .optimize import portfolio as pf
from .risk import shield
from .simulate import scenarios as sc

DEFAULT_BUDGET = 20_000_000  # ₹2 crore
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


@dataclass
class Built:
    current: pd.DataFrame
    forecast: pd.DataFrame
    correlation: np.ndarray
    backtest: dict
    importance: list[dict]
    history_rows: int


def _build() -> Built:
    history, current = synth.generate()
    bt = radar.backtest(history)
    model = radar.production(history)
    forecast = model.predict(current)
    forecast.index = current["option_id"]
    calib = history[pd.to_datetime(history["start"]) >= pd.Timestamp(date(2025, 7, 1))]
    ids = [o.id for o in OPTIONS]
    corr = sc.estimate_correlation(calib, model.predict(calib), ids, {o.id: (o.cluster, o.region) for o in OPTIONS})
    return Built(current.drop(columns=["hidden_demand"]), forecast, corr, bt, model.importance(), len(history))


def _signals(row: pd.Series) -> dict:
    return {
        "on_books": int(row["on_books"]),
        "on_books_ly": int(row["on_books_ly"]),
        "pace_yoy": float(np.log1p(row["on_books"]) - np.log1p(row["on_books_ly"])),
        "searches": int(row["searches"]),
        "search_yoy": float(np.log1p(row["searches"]) - np.log1p(row["searches_ly"])),
        "look_to_book": float(row["searches"] / max(row["on_books"], 1.0)),
        "soldout_nights_ly": int(row["soldout_nights_ly"]),
        "rate_change": float(row["rate_change"]),
        "ly_demand": int(row["ly_demand"]),
        "lead_days": int(row["lead_days"]),
    }


def _hist(values: list[np.ndarray], bins: int = 36) -> dict:
    lo = min(float(np.quantile(v, 0.002)) for v in values)
    hi = max(float(np.quantile(v, 0.998)) for v in values)
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, bins + 1)
    return {
        "edges": [round(e, 2) for e in edges.tolist()],
        "counts": [np.histogram(np.clip(v, lo, hi), edges)[0].tolist() for v in values],
    }


def _stats(p: np.ndarray) -> dict:
    return {
        "expected": float(p.mean()),
        "cvar": pf.cvar(p),
        "p_loss": float(np.mean(p < 0)),
        "p05": float(np.quantile(p, 0.05)),
        "p95": float(np.quantile(p, 0.95)),
    }


class Engine:
    def __init__(self, cache_dir: Path | None = CACHE_DIR):
        self.built = self._load(cache_dir)
        self.scenarios = sc.simulate(self.built.forecast, self.built.correlation)
        self.demand = {o.id: self.scenarios.column(o.id) for o in OPTIONS}
        self.signals = {r["option_id"]: _signals(r) for _, r in self.built.current.iterrows()}
        self._plans: dict = {}

    @staticmethod
    def _load(cache_dir: Path | None) -> Built:
        if cache_dir is None:
            return _build()
        src = "".join(p.read_text(encoding="utf8") for p in sorted(Path(__file__).parent.rglob("*.py")))
        key = hashlib.sha1((__version__ + src).encode()).hexdigest()[:12]
        path = Path(cache_dir) / f"engine-{key}.pkl"
        if path.exists():
            with path.open("rb") as fh:
                return pickle.load(fh)
        built = _build()
        path.parent.mkdir(parents=True, exist_ok=True)
        for old in path.parent.glob("engine-*.pkl"):
            old.unlink()
        with path.open("wb") as fh:
            pickle.dump(built, fh)
        return built

    # ------------------------------------------------------------------ read-only views
    def forecast_of(self, oid: str) -> dict:
        r = self.built.forecast.loc[oid]
        return {"p10": float(r["p10"]), "p50": float(r["p50"]), "p90": float(r["p90"])}

    def options(self) -> list[dict]:
        out = []
        for o in OPTIONS:
            out.append(
                {
                    "id": o.id,
                    "name": o.name,
                    "product": o.product,
                    "kind": o.kind,
                    "unit": o.unit,
                    "region": o.region,
                    "dates": o.dates,
                    "start": o.start.isoformat(),
                    "nights": o.nights,
                    "image": o.image,
                    "image_alt": o.image_alt,
                    "economics": {
                        "hard_cost": o.hard_cost,
                        "sell_price": o.sell_price,
                        "allot_cost": o.allot_cost,
                        "allot_fee": o.allot_fee,
                        "allot_cap": o.allot_cap,
                        "salvage": o.salvage,
                        "supply_cap": o.supply_cap,
                        "suppliers": o.suppliers,
                        "held": o.held,
                        "breakeven_sure": shield.breakeven_sure(o),
                    },
                    "forecast": self.forecast_of(o.id),
                    "signals": self.signals[o.id],
                }
            )
        return out

    def meta(self) -> dict:
        return {
            "version": __version__,
            "season": SEASON,
            "today": TODAY.isoformat(),
            "default_budget": DEFAULT_BUDGET,
            "scenarios": len(self.scenarios.demand),
            "cvar_alpha": CVAR_ALPHA,
            "history_rows": self.built.history_rows,
            "risk_profiles": [{"id": k, **v} for k, v in RISK.items()],
        }

    def backtest(self) -> dict:
        return {**self.built.backtest, "production_importance": self.built.importance}

    def correlation(self) -> dict:
        return {"ids": [o.id for o in OPTIONS], "matrix": np.round(self.built.correlation, 3).tolist()}

    # ------------------------------------------------------------------ planning
    @lru_cache(maxsize=32)
    def _unconstrained(self, risk: str, forced_key: tuple) -> dict[str, tuple[int, int]]:
        forced = {k: (h, a) for k, h, a in forced_key}
        sol = pf.solve(list(OPTIONS), self.demand, 1e12, RISK[risk]["cvar_weight"], forced)
        return {i: (p.h, p.a) for i, p in sol.picks.items()}

    def plan(
        self,
        budget: float = DEFAULT_BUDGET,
        risk: str = "balanced",
        forced: dict[str, tuple[int, int]] | None = None,
        exact: bool = False,
    ) -> dict:
        if risk not in RISK:
            raise ValueError(f"unknown risk profile {risk!r}")
        forced = forced or {}
        forced_key = tuple(sorted((k, int(h), int(a)) for k, (h, a) in forced.items()))
        key = (round(budget / 1e5), risk, forced_key, exact)
        if key not in self._plans:
            self._plans[key] = self._plan(budget, risk, forced, forced_key, exact)
            if len(self._plans) > 64:
                self._plans.pop(next(iter(self._plans)))
        return self._plans[key]

    def _plan(self, budget, risk, forced, forced_key, exact) -> dict:
        w = RISK[risk]["cvar_weight"]
        sol = pf.solve(list(OPTIONS), self.demand, budget, w, forced, exact=exact)
        free = self._unconstrained(risk, forced_key)
        p90 = {o.id: self.forecast_of(o.id)["p90"] for o in OPTIONS}
        base = pf.buy_at_peak(list(OPTIONS), p90, budget)

        total = np.zeros(len(self.scenarios.demand))
        btotal = np.zeros_like(total)
        rows, all_alerts = [], []
        for o in OPTIONS:
            d = self.demand[o.id]
            pk, bk = sol.picks[o.id], base[o.id]
            p = pf.payoff(o, d, pk.h, pk.a)
            bp = pf.payoff(o, d, bk.h, bk.a)
            total += p
            btotal += bp
            f = self.forecast_of(o.id)
            stats = shield.pick_stats(o, d, pk.h, pk.a)
            action = shield.action_for(o, pk.h, pk.a, free[o.id])
            sig = self.signals[o.id]
            al = shield.alerts(o, f, d, pk.h, pk.a, sig)
            all_alerts += al
            rows.append(
                {
                    "id": o.id,
                    "action": action,
                    "label": shield.ACTION_LABEL[action],
                    "locked": pk.forced,
                    "plan": {"hard": pk.h, "allot": pk.a, "cash": pk.cash},
                    "unconstrained": {"hard": free[o.id][0], "allot": free[o.id][1]},
                    "forecast": f,
                    "signals": sig,
                    "stats": stats,
                    "profit": _stats(p),
                    "baseline": {"hard": bk.h, **_stats(bp)},
                    "reasons": shield.reasons(o, f, sig, pk.h, pk.a, stats, action, RISK[risk]["label"]),
                    "alerts": al,
                    "demand_hist": _hist([d], 30),
                    "profit_hist": _hist([p, bp], 30),
                }
            )
        order = {
            "prebuy_allot": 0,
            "prebuy": 0,
            "allot_only": 1,
            "over_budget": 2,
            "add_supplier": 3,
            "watch": 4,
            "renegotiate": 5,
        }
        rows.sort(key=lambda r: (order[r["action"]], -r["profit"]["expected"]))
        for rank, r in enumerate(rows, 1):
            r["rank"] = rank
        hard = sum(r["plan"]["hard"] for r in rows)
        sold_hard = sum(r["stats"]["hard_sell_through"] * r["plan"]["hard"] for r in rows if r["plan"]["hard"])
        sev = {"warning": 0, "info": 1}
        return {
            "budget": budget,
            "risk": risk,
            "risk_label": RISK[risk]["label"],
            "solver": {
                "method": sol.method,
                "seconds": sol.seconds,
                "candidates": sol.candidates,
                "exact_status": sol.exact_status,
                "objective": sol.objective,
            },
            "summary": {
                "cash": sum(r["plan"]["cash"] for r in rows),
                "hard_units": hard,
                "allot_units": sum(r["plan"]["allot"] for r in rows),
                "hard_sell_through": sold_hard / hard if hard else None,
                **_stats(total),
            },
            "baseline": {
                "name": "Buy the P90 forecast upfront",
                "cash": sum(b.cash for b in base.values()),
                **_stats(btotal),
            },
            "histogram": _hist([total, btotal], 40),
            "rows": rows,
            "alerts": sorted(all_alerts, key=lambda a: (sev[a["severity"]], a["date"])),
        }

    def option_ids(self) -> list[str]:
        return list(BY_ID)
