import pytest

from inventiq.catalog import BY_ID
from inventiq.risk import shield


def test_breakeven_sure_to_sell():
    o = BY_ID["goa"]
    assert shield.breakeven_sure(o) == pytest.approx((o.hard_cost - o.salvage) / (o.sell_price - o.salvage))


def test_actions():
    assert shield.action_for(BY_ID["srinagar"], 0, 0, (0, 0)) == "add_supplier"
    assert shield.action_for(BY_ID["bangkok"], 0, 0, (0, 0)) == "renegotiate"
    assert shield.action_for(BY_ID["goa"], 100, 50, (100, 50)) == "prebuy_allot"
    assert shield.action_for(BY_ID["goa"], 0, 0, (100, 0)) == "over_budget"
    assert shield.action_for(BY_ID["goa"], 0, 0, (0, 0)) == "watch"


def test_plan_rows_explain_themselves(engine):
    plan = engine.plan(2e7, "balanced")
    for row in plan["rows"]:
        assert row["reasons"], row["id"]
        assert row["reasons"][0].startswith("Demand is forecast")
    kinds = {a["kind"] for a in plan["alerts"]}
    assert {"release", "reprice", "supplier"} <= kinds
