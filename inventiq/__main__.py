"""Command line: python -m inventiq <command>

build                      train the models and cache them (runs automatically when needed)
backtest                   print the Demand Radar's out-of-sample accuracy
plan [--budget --risk]     print the optimised plan for a budget and risk profile
serve [--host --port]      start the API and the buying desk
"""

from __future__ import annotations

import argparse
import json
import sys


def lakh(v: float) -> str:
    sign = "-" if v < 0 else "+"
    return f"{sign}₹{abs(v) / 1e5:,.1f} L"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="inventiq", description="Pre-buy planning for travel inventory")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    b = sub.add_parser("backtest")
    b.add_argument("--json", action="store_true")
    pl = sub.add_parser("plan")
    pl.add_argument("--budget", type=float, default=2e7, help="rupees (default 20000000 = ₹2 crore)")
    pl.add_argument("--risk", choices=["cautious", "balanced", "bold"], default="balanced")
    pl.add_argument("--exact", action="store_true", help="also run the SCIP mixed-integer solve")
    pl.add_argument("--json", action="store_true")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("inventiq.api.main:app", host=args.host, port=args.port)
        return 0

    from .engine import Engine

    eng = Engine()
    if args.cmd == "build":
        print(f"engine ready: {eng.meta()['history_rows']:,} history rows, {eng.meta()['scenarios']:,} futures")
    elif args.cmd == "backtest":
        bt = eng.backtest()
        if args.json:
            print(json.dumps(bt, indent=2))
        else:
            a, pk = bt["all"], bt["peak_windows"]
            print(f"Test period: {bt['test_period']} ({a['rows']:,} forecasts)")
            print(
                f"P50 error (WAPE): {a['wape_p50']:.1%}   same-window-last-year: {a['wape_naive']:.1%}   "
                f"improvement: {a['improvement']:.0%}"
            )
            print(
                f"P10-P90 coverage: {a['coverage_p10_p90']:.1%} (target 80%)   below: {a['below_p10']:.1%}   "
                f"above: {a['above_p90']:.1%}"
            )
            print(
                f"Peak windows: WAPE {pk['wape_p50']:.1%} vs {pk['wape_naive']:.1%}, coverage {pk['coverage_p10_p90']:.1%}"
            )
            print("Error by lead time: " + ", ".join(f"{k} days {v:.1%}" for k, v in bt["by_lead_wape"].items()))
    elif args.cmd == "plan":
        plan = eng.plan(args.budget, args.risk, exact=args.exact)
        if args.json:
            print(json.dumps(plan, indent=2, default=float))
            return 0
        s, b = plan["summary"], plan["baseline"]
        print(
            f"{plan['risk_label']} plan for ₹{args.budget / 1e7:.2f} crore "
            f"({plan['solver']['method']}, {plan['solver']['seconds']} s)"
        )
        print(
            f"{'#':>2}  {'option':34} {'action':13} {'hard':>6} {'allot':>6} {'cash':>12} {'expected':>11} {'worst 5%':>11}"
        )
        for r in plan["rows"]:
            name = next(o["name"] for o in eng.options() if o["id"] == r["id"])
            print(
                f"{r['rank']:>2}  {name:34} {r['label']:13} {r['plan']['hard']:>6} {r['plan']['allot']:>6} "
                f"{r['plan']['cash'] / 1e5:>10,.1f} L {lakh(r['profit']['expected']):>11} {lakh(r['profit']['cvar']):>11}"
            )
        print(
            f"\nInventIQ plan: cash ₹{s['cash'] / 1e7:.2f} Cr, expected {lakh(s['expected'])}, "
            f"worst 5% {lakh(s['cvar'])}, chance of a loss {s['p_loss']:.1%}"
        )
        print(
            f"{b['name']}: cash ₹{b['cash'] / 1e7:.2f} Cr, expected {lakh(b['expected'])}, "
            f"worst 5% {lakh(b['cvar'])}, chance of a loss {b['p_loss']:.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
