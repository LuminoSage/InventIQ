import numpy as np
import pytest

from inventiq.catalog import BY_ID, OPTIONS
from inventiq.optimize import portfolio as pf


def test_payoff_by_hand():
    o = BY_ID["goa"]
    d = np.array([300.0, 600.0, 900.0])
    p = pf.payoff(o, d, h=400, a=200)
    fee = o.allot_fee * 200
    low = 8400 * 300 - 5800 * 400 + o.salvage * 100 - fee  # 100 hard rooms unsold
    mid = 8400 * 600 - 5800 * 400 - 6300 * 200 - fee  # every unit sold
    high = mid  # capped at h + a
    assert p.tolist() == pytest.approx([low, mid, high])


def test_cvar_is_the_mean_of_the_worst_five_percent():
    p = np.arange(1, 101, dtype=float)
    assert pf.cvar(p) == pytest.approx(3.0)


@pytest.fixture(scope="module")
def demand():
    rng = np.random.default_rng(0)
    return {o.id: np.maximum(0, rng.normal(o.peak, 0.2 * o.peak, 6000)).round() for o in OPTIONS}


@pytest.mark.parametrize("budget", [5e6, 2e7])
def test_plan_respects_budget_supply_and_allotment(demand, budget):
    sol = pf.solve(list(OPTIONS), demand, budget, 0.3)
    assert sum(p.cash for p in sol.picks.values()) <= budget + 1e-6
    for p in sol.picks.values():
        assert p.h <= p.option.supply_cap
        assert p.a <= p.option.allot_cap
        if not pf.can_hard(p.option):
            assert p.h == 0


def test_locked_decisions_are_kept(demand):
    sol = pf.solve(list(OPTIONS), demand, 2e7, 0.3, forced={"goa": (100, 0), "dubai": (0, 0)})
    assert (sol.picks["goa"].h, sol.picks["goa"].a) == (100, 0)
    assert (sol.picks["dubai"].h, sol.picks["dubai"].a) == (0, 0)


def test_fast_search_is_close_to_the_exact_programme(demand):
    fast = pf.solve(list(OPTIONS), demand, 1e7, 0.3)
    exact = pf.solve(list(OPTIONS), demand, 1e7, 0.3, exact=True, time_limit=30)
    assert exact.objective >= fast.objective - 1e-6
    assert fast.objective >= 0.98 * exact.objective


def test_more_budget_never_hurts(demand):
    small = pf.solve(list(OPTIONS), demand, 5e6, 0.3)
    large = pf.solve(list(OPTIONS), demand, 2e7, 0.3)
    assert large.objective >= small.objective - 1e-6


def test_beats_buying_at_the_peak(demand):
    p90 = {k: float(np.quantile(v, 0.9)) for k, v in demand.items()}
    sol = pf.solve(list(OPTIONS), demand, 2e7, 0.3)
    base = pf.buy_at_peak(list(OPTIONS), p90, 2e7)
    plan = sum(pf.payoff(p.option, demand[i], p.h, p.a) for i, p in sol.picks.items())
    peak = sum(pf.payoff(p.option, demand[i], p.h, p.a) for i, p in base.items())
    assert plan.mean() > peak.mean() and pf.cvar(plan) > pf.cvar(peak)
