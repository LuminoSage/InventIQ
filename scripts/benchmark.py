"""Reproduce the results tables in the README.

    python scripts/benchmark.py

1. The plan against 'buy the P90 forecast upfront' for several budgets and every risk profile,
   scored on the same 10,000 joint futures.
2. The fast Lagrangian search against the exact mixed-integer programme (SCIP).
"""

from __future__ import annotations

import time

from inventiq.catalog import OPTIONS, RISK
from inventiq.engine import Engine
from inventiq.optimize import portfolio as pf


def lakh(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}₹{abs(v) / 1e5:.1f} L"


def main() -> None:
    eng = Engine()
    bt = eng.backtest()["all"]
    print(
        f"Back-test: WAPE {bt['wape_p50']:.1%} vs {bt['wape_naive']:.1%} naive, coverage {bt['coverage_p10_p90']:.1%}\n"
    )

    print("| Budget | Risk | Expected | Worst 5% | Loss chance | P90 upfront: expected | worst 5% | loss chance |")
    print("|---|---|---|---|---|---|---|---|")
    for budget in (5e6, 1e7, 2e7, 3e7):
        for risk in RISK:
            p = eng.plan(budget, risk)
            s, b = p["summary"], p["baseline"]
            print(
                f"| ₹{budget / 1e7:.1f} Cr | {RISK[risk]['label']} | {lakh(s['expected'])} | {lakh(s['cvar'])} | "
                f"{s['p_loss']:.1%} | {lakh(b['expected'])} | {lakh(b['cvar'])} | {b['p_loss']:.1%} |"
            )

    print("\n| Budget | Risk | Fast search | Exact (SCIP) | Gap | Fast time | Exact time |")
    print("|---|---|---|---|---|---|---|")
    for budget in (5e6, 1e7, 2e7):
        for risk in ("cautious", "bold"):
            w = RISK[risk]["cvar_weight"]
            t = time.perf_counter()
            fast = pf.solve(list(OPTIONS), eng.demand, budget, w)
            tf = time.perf_counter() - t
            t = time.perf_counter()
            exact = pf.solve(list(OPTIONS), eng.demand, budget, w, exact=True, time_limit=30)
            te = time.perf_counter() - t
            gap = 1 - fast.objective / exact.objective
            print(
                f"| ₹{budget / 1e7:.1f} Cr | {RISK[risk]['label']} | {lakh(fast.objective)} | {lakh(exact.objective)} | "
                f"{gap:.2%} | {tf:.1f} s | {te:.1f} s |"
            )


if __name__ == "__main__":
    main()
