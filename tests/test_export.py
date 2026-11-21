import json

from inventiq.export import export


def test_export_writes_a_static_snapshot(engine, tmp_path):
    res = export(tmp_path, engine, budgets=[20_000_000])
    assert res["files"] == 4 + 3  # four read-only endpoints, one plan per risk profile
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["demo_budgets"][0] == 2_500_000 and meta["demo_budgets"][-1] == 50_000_000
    plan = json.loads((tmp_path / "plans" / "balanced-200.json").read_text(encoding="utf-8"))
    live = engine.plan(20_000_000, "balanced")
    assert plan["summary"]["expected"] == float(f"{live['summary']['expected']:.6g}")
    assert len(plan["rows"]) == 12
