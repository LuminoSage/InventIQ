"""A static snapshot of the API, so the desk can be hosted without a server.

    python -m inventiq export web/dist-demo/demo

writes the read-only endpoints and one plan per risk profile and budget, from ₹25 lakh to ₹5 crore in
₹25 lakh steps, computed by the same engine the API uses. The desk's demo build (``npm run build:demo``)
reads these files instead of calling the API.
"""

from __future__ import annotations

import json
from pathlib import Path

from .catalog import RISK
from .engine import Engine

STEP = 2_500_000
BUDGETS = [STEP * k for k in range(1, 21)]  # ₹25 lakh to ₹5 crore


def _compact(x):
    """Six significant digits are plenty for display and keep the files small."""
    if isinstance(x, float):
        return float(f"{x:.6g}")
    if isinstance(x, dict):
        return {k: _compact(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_compact(v) for v in x]
    return x


def export(out: str | Path, engine: Engine | None = None, budgets: list[int] | None = None) -> dict:
    eng = engine or Engine()
    out = Path(out)
    (out / "plans").mkdir(parents=True, exist_ok=True)

    def write(name: str, obj) -> None:
        text = json.dumps(
            _compact(obj),
            separators=(",", ":"),
            ensure_ascii=False,
            default=lambda o: o.item() if hasattr(o, "item") else str(o),
        )
        (out / name).write_text(text, encoding="utf-8")

    write("meta.json", {**eng.meta(), "demo_budgets": BUDGETS})
    write("options.json", eng.options())
    write("backtest.json", eng.backtest())
    write("correlation.json", eng.correlation())
    for risk in RISK:
        for budget in budgets or BUDGETS:
            write(f"plans/{risk}-{budget // 100_000}.json", eng.plan(budget, risk))
    files = list(out.rglob("*.json"))
    return {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}
