import pytest
from fastapi.testclient import TestClient

from inventiq.api import main
from inventiq.api.store import DecisionStore


@pytest.fixture(scope="module")
def client(engine):
    main.state["engine"] = engine
    main.state["store"] = DecisionStore(":memory:")
    with TestClient(main.app) as c:
        yield c


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["scenarios"] == 10_000
    assert {r["id"] for r in meta["risk_profiles"]} == {"cautious", "balanced", "bold"}


def test_options_have_ordered_forecasts(client):
    opts = client.get("/api/options").json()
    assert len(opts) == 12
    for o in opts:
        f = o["forecast"]
        assert f["p10"] <= f["p50"] <= f["p90"]


def test_plan_shape_and_budget(client):
    r = client.post("/api/plan", json={"budget": 15_000_000, "risk": "cautious"}).json()
    assert r["summary"]["cash"] <= 15_000_000
    assert len(r["rows"]) == 12
    assert r["summary"]["expected"] > r["baseline"]["expected"]
    assert len(r["histogram"]["counts"]) == 2


def test_rejects_bad_input(client):
    assert client.post("/api/plan", json={"budget": -1}).status_code == 422
    assert client.post("/api/plan", json={"risk": "reckless"}).status_code == 422
    assert client.post("/api/decisions", json={"option_id": "atlantis", "action": "reject"}).status_code == 404
    assert client.post("/api/decisions", json={"option_id": "goa", "action": "approve"}).status_code == 422
    assert (
        client.post(
            "/api/decisions", json={"option_id": "goa", "action": "edit", "hard": 10, "allot": 9999}
        ).status_code
        == 422
    )


def test_decisions_lock_the_plan_and_can_be_undone(client):
    client.delete("/api/decisions")
    assert (
        client.post("/api/decisions", json={"option_id": "goa", "action": "edit", "hard": 120, "allot": 40}).status_code
        == 201
    )
    assert client.post("/api/decisions", json={"option_id": "dubai", "action": "reject"}).status_code == 201
    rows = {r["id"]: r for r in client.post("/api/plan", json={"budget": 20_000_000}).json()["rows"]}
    assert rows["goa"]["plan"]["hard"] == 120 and rows["goa"]["plan"]["allot"] == 40 and rows["goa"]["locked"]
    assert rows["dubai"]["plan"]["hard"] == 0 and rows["dubai"]["locked"]
    client.post("/api/decisions", json={"option_id": "goa", "action": "undo"})
    d = client.get("/api/decisions").json()
    assert "goa" not in d["current"] and "dubai" in d["current"]
    assert [e["action"] for e in d["log"]][:3] == ["undo", "reject", "edit"]
