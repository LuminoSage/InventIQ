"""Portfolio Optimizer: choose hard units and allotment for every option within one budget.

For option i, a plan is (h, a): h hard units paid upfront and a allotment units held for a small fee.
In a future where demand is d, its profit is

    sold       = min(d, h + a)
    profit     = price * sold - hard_cost * h - allot_cost * (sold - min(d, h))
                 - allot_fee * a + salvage * (h - min(d, h))

Each option offers a set of candidate plans (hard units at 'sure to sell' quantiles of its demand, crossed
with 0, half or all of the allotment on offer). We pick one candidate per option to maximise

    (1 - w) * E[profit] + w * CVaR_5%[profit]        subject to  sum(cash) <= budget

where profit is summed over options in each joint future and CVaR_5% is the average over the worst 5%
of futures. The weight w comes from the risk profile.

Two solvers share this formulation:

* ``fast`` (the desk, about half a second): Lagrangian relaxation of the budget. For a price mu per rupee of
  cash, coordinate ascent maximises objective - mu * cash, evaluating every candidate of an option against
  all futures at once. Bisection on mu brackets the budget. From there three routes reach a plan that
  fits: climb from the best plans just under the budget, step down from the plan just over it (dropping
  the units that cost the least objective per rupee), and grow a plan from nothing by the best gain per
  rupee. Each ends with an ascent under the budget, and the best is kept.
* ``exact``: the same choice as a mixed-integer programme, with CVaR in its linear form (Rockafellar and
  Uryasev, 2000): CVaR = max_eta  eta - E[(eta - profit)+] / 0.05. SCIP solves it through OR-Tools on
  600 futures stratified across the profit range, warm-started from the fast plan, and reports its bound.

Either way the chosen plan is scored on all 10,000 futures.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from ortools.linear_solver import pywraplp

from ..catalog import CVAR_ALPHA, Option

SURE_LEVELS = (0.99, 0.97, 0.95, 0.92, 0.90, 0.85, 0.80, 0.75, 0.70, 0.60, 0.50)
ALLOT_SHARES = (0.0, 0.5, 1.0)
LADDER = (0.25, 0.5, 0.75)
N_SEARCH = 2_000  # futures the fast search scores against (more does not change the plan)
N_EXACT = 600  # futures in the mixed-integer programme


def payoff(o: Option, d: np.ndarray, h: int, a: int) -> np.ndarray:
    sold = np.minimum(d, h + a)
    sold_hard = np.minimum(d, h)
    allot_cost = o.allot_cost or 0.0
    return (
        o.sell_price * sold
        - o.hard_cost * h
        - allot_cost * (sold - sold_hard)
        - o.allot_fee * a
        + o.salvage * (h - sold_hard)
    )


def cash(o: Option, h: int, a: int) -> float:
    return o.hard_cost * h + o.allot_fee * a


def can_hard(o: Option) -> bool:
    return o.sell_price > o.hard_cost and o.supply_cap > 0


def can_allot(o: Option) -> bool:
    return o.allot_cost is not None and o.allot_cost < o.sell_price and o.allot_cap > 0


def candidates(o: Option, d: np.ndarray) -> list[tuple[int, int]]:
    """Hard levels at 'sure to sell' quantiles of demand (plus a ladder of smaller blocks), crossed with
    allotment shares of the cap."""
    hs = {0}
    if can_hard(o):
        for s in SURE_LEVELS:
            hs.add(int(min(o.supply_cap, np.quantile(d, 1 - s))))
        floor = min(hs - {0}, default=0)
        for share in LADDER:  # smaller blocks below the safest level, so a buy can grow
            hs.add(int(floor * share))  # in steps instead of one lump
    hs.discard(0)
    hs.add(0)
    shares = ALLOT_SHARES if can_allot(o) else (0.0,)
    return sorted({(h, int(round(o.allot_cap * s))) for h in hs for s in shares})


def cvar(p: np.ndarray, alpha: float = CVAR_ALPHA) -> float:
    k = max(1, int(round(len(p) * alpha)))
    return float(np.mean(np.partition(p, k - 1)[:k]))


def objective(total: np.ndarray, w: float) -> float:
    return (1 - w) * float(total.mean()) + w * cvar(total)


def _objective_rows(totals: np.ndarray, w: float) -> np.ndarray:
    """objective() for every row of a (candidates, futures) array at once."""
    k = max(1, int(round(totals.shape[1] * CVAR_ALPHA)))
    tail = np.partition(totals, k - 1, axis=1)[:, :k].mean(axis=1)
    return (1 - w) * totals.mean(axis=1) + w * tail


@dataclass
class Pick:
    option: Option
    h: int
    a: int
    forced: bool = False

    @property
    def cash(self) -> float:
        return cash(self.option, self.h, self.a)


@dataclass
class Solution:
    picks: dict[str, Pick]
    method: str
    seconds: float
    objective: float  # (1 - w) * mean + w * CVaR on all futures, in rupees
    candidates: int
    exact_status: str = "not run"
    exact_bound: float | None = None
    notes: list[str] = field(default_factory=list)


class _Search:
    def __init__(self, pay, costs, w, frozen):
        self.pay, self.costs, self.w, self.frozen = pay, costs, w, frozen

    def ascent(self, idx, mu=0.0, budget=None, sweeps=60):
        idx = dict(idx)
        total = sum(self.pay[i][k] for i, k in idx.items())
        spent = sum(self.costs[i][k] for i, k in idx.items())
        for _ in range(sweeps):
            moved = False
            for i, rows in self.pay.items():
                if i in self.frozen:
                    continue
                base = total - rows[idx[i]]
                vals = _objective_rows(base + rows, self.w) - mu * self.costs[i]
                if budget is not None:
                    vals = np.where(spent - self.costs[i][idx[i]] + self.costs[i] > budget + 1e-6, -np.inf, vals)
                k = int(np.argmax(vals))
                if k != idx[i] and vals[k] > vals[idx[i]] + 1e-6:
                    total = base + rows[k]
                    spent += self.costs[i][k] - self.costs[i][idx[i]]
                    idx[i] = k
                    moved = True
            if not moved:
                break
        return idx, spent, objective(total, self.w)

    def repair(self, idx, budget):
        """From a plan over budget, step down whichever option loses the least objective per rupee freed,
        until the plan fits."""
        idx = dict(idx)
        total = sum(self.pay[i][k] for i, k in idx.items())
        spent = sum(self.costs[i][k] for i, k in idx.items())
        cur = objective(total, self.w)
        while spent > budget + 1e-6:
            best = (np.inf, None, None)
            for i, rows in self.pay.items():
                if i in self.frozen:
                    continue
                cheaper = np.flatnonzero(self.costs[i] < self.costs[i][idx[i]])
                if not len(cheaper):
                    continue
                base = total - rows[idx[i]]
                vals = _objective_rows(base + rows[cheaper], self.w)
                ratio = (cur - vals) / (self.costs[i][idx[i]] - self.costs[i][cheaper])
                j = int(np.argmin(ratio))
                if ratio[j] < best[0]:
                    best = (ratio[j], i, int(cheaper[j]))
            if best[1] is None:
                break
            _, i, k = best
            total = total - self.pay[i][idx[i]] + self.pay[i][k]
            spent += self.costs[i][k] - self.costs[i][idx[i]]
            idx[i] = k
            cur = objective(total, self.w)
        return idx

    def greedy(self, start, budget):
        """Grow the plan one upgrade at a time, always taking the upgrade with the most objective gained
        per rupee that still fits: the classic rule for a budget split across many small bets."""
        idx = dict(start)
        total = sum(self.pay[i][k] for i, k in idx.items())
        spent = sum(self.costs[i][k] for i, k in idx.items())
        cur = objective(total, self.w)
        while True:
            best = (1e-12, None, None)
            for i, rows in self.pay.items():
                if i in self.frozen:
                    continue
                dc = self.costs[i] - self.costs[i][idx[i]]
                ok = np.flatnonzero((dc > 0) & (spent + dc <= budget + 1e-6))
                if not len(ok):
                    continue
                vals = _objective_rows(total - rows[idx[i]] + rows[ok], self.w)
                ratio = (vals - cur) / dc[ok]
                j = int(np.argmax(ratio))
                if ratio[j] > best[0]:
                    best = (ratio[j], i, int(ok[j]))
            if best[1] is None:
                return idx
            _, i, k = best
            total = total - self.pay[i][idx[i]] + self.pay[i][k]
            spent += self.costs[i][k] - self.costs[i][idx[i]]
            idx[i] = k
            cur = objective(total, self.w)

    def run(self, start, budget):
        idx, spent, val = self.ascent(start)
        if spent <= budget:
            return idx
        lo, hi, feasible, over = 0.0, 2.0, [], idx
        warm = idx
        for _ in range(18):
            mu = (lo + hi) / 2
            warm, spent, val = self.ascent(warm, mu)
            if spent <= budget:
                hi = mu
                feasible.append((val, warm))
            else:
                lo = mu
                over = warm
        routes = [self.repair(over, budget), self.greedy(start, budget)]  # down from over, up from empty
        routes += [w for _, w in sorted(feasible, key=lambda p: -p[0])[:2]]  # up from just under it
        best = (-np.inf, None)
        for r in routes:
            r_idx, r_spent, r_val = self.ascent(r, 0.0, budget)
            if r_spent <= budget + 1e-6 and r_val > best[0]:
                best = (r_val, r_idx)
        return best[1] if best[1] is not None else self.ascent(start, 0.0, budget)[0]


def _exact(options, cands, pay, costs, budget, w, hint, order, n, time_limit):
    solver = pywraplp.Solver.CreateSolver("SCIP") or pywraplp.Solver.CreateSolver("CBC")
    solver.SetTimeLimit(int(time_limit * 1000))
    scale = 1e5  # lakh rupees keep the coefficients well scaled
    pick = order[np.linspace(0, len(order) - 1, n).round().astype(int)]
    xs = {o.id: [solver.BoolVar(f"x_{o.id}_{k}") for k in range(len(cands[o.id]))] for o in options}
    for o in options:
        solver.Add(sum(xs[o.id]) == 1)
    solver.Add(sum(costs[o.id][k] / scale * x for o in options for k, x in enumerate(xs[o.id])) <= budget / scale)
    sub = {o.id: pay[o.id][:, pick] / scale for o in options}
    eta = solver.NumVar(-solver.infinity(), solver.infinity(), "eta")
    us = [solver.NumVar(0.0, solver.infinity(), f"u_{j}") for j in range(n)]
    for j in range(n):
        ct = solver.Constraint(-solver.infinity(), 0.0)  # eta - profit_j - u_j <= 0
        ct.SetCoefficient(eta, 1.0)
        ct.SetCoefficient(us[j], -1.0)
        for o in options:
            col = sub[o.id][:, j]
            for k, x in enumerate(xs[o.id]):
                if col[k] != 0.0:
                    ct.SetCoefficient(x, -float(col[k]))
    obj = solver.Objective()
    for o in options:
        means = sub[o.id].mean(axis=1)
        for k, x in enumerate(xs[o.id]):
            obj.SetCoefficient(x, (1 - w) * float(means[k]))
    obj.SetCoefficient(eta, w)
    for u in us:
        obj.SetCoefficient(u, -w / (CVAR_ALPHA * n))
    obj.SetMaximization()
    solver.SetHint(
        [x for o in options for x in xs[o.id]],
        [1.0 if k == hint[o.id] else 0.0 for o in options for k in range(len(xs[o.id]))],
    )
    code = solver.Solve()
    status = {pywraplp.Solver.OPTIMAL: "optimal", pywraplp.Solver.FEASIBLE: "feasible (time limit)"}.get(
        code, "no solution"
    )
    if status == "no solution":
        return status, None, None
    ks = {o.id: int(np.argmax([x.solution_value() for x in xs[o.id]])) for o in options}
    return status, ks, float(obj.BestBound() * scale)


def solve(
    options: list[Option],
    demand: dict[str, np.ndarray],
    budget: float,
    cvar_weight: float,
    forced: dict[str, tuple[int, int]] | None = None,
    exact: bool = False,
    time_limit: float = 10.0,
) -> Solution:
    forced = forced or {}
    t0 = time.perf_counter()
    w = cvar_weight
    cands, pay, pay_s, costs = {}, {}, {}, {}
    for o in options:
        d = demand[o.id]
        c = [forced[o.id]] if o.id in forced else [ha for ha in candidates(o, d) if cash(o, *ha) <= budget]
        cands[o.id] = c
        pay[o.id] = np.array([payoff(o, d, *ha) for ha in c])
        pay_s[o.id] = pay[o.id][:, :N_SEARCH]
        costs[o.id] = np.array([cash(o, *ha) for ha in c])
    start = {o.id: 0 if o.id in forced else cands[o.id].index((0, 0)) for o in options}
    ks = _Search(pay_s, costs, w, set(forced)).run(start, budget)
    total = sum(pay[i][k] for i, k in ks.items())
    best, method, status, bound = objective(total, w), "Lagrangian search", "not run", None
    if exact:
        status, mk, bound = _exact(options, cands, pay, costs, budget, w, ks, np.argsort(total), N_EXACT, time_limit)
        if mk is not None:
            mtotal = sum(pay[i][k] for i, k in mk.items())
            if objective(mtotal, w) > best + 1e-6:
                ks, best, method = mk, objective(mtotal, w), "MILP (SCIP)"
    picks = {o.id: Pick(o, *cands[o.id][ks[o.id]], forced=o.id in forced) for o in options}
    return Solution(
        picks, method, round(time.perf_counter() - t0, 2), best, sum(len(c) for c in cands.values()), status, bound
    )


def buy_at_peak(options: list[Option], p90: dict[str, float], budget: float) -> dict[str, Pick]:
    """The rule of thumb InventIQ replaces: buy the P90 forecast as hard units, best margin first,
    until the budget runs out."""
    picks, left = {o.id: Pick(o, 0, 0) for o in options}, budget
    for o in sorted((o for o in options if can_hard(o)), key=lambda o: -(o.sell_price - o.hard_cost) / o.hard_cost):
        h = int(min(o.supply_cap, round(p90[o.id]), left // o.hard_cost))
        if h >= 10:
            picks[o.id] = Pick(o, h, 0)
            left -= h * o.hard_cost
    return picks
