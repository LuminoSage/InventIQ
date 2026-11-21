from inventiq.forecast import radar
from inventiq.forecast.features import FEATURES, build


def test_features_have_no_gaps(data):
    history, current = data
    x = build(history)
    assert list(x.columns) == FEATURES
    assert not x.isna().any().any()
    assert not build(current).isna().any().any()


def test_backtest_beats_seasonal_naive_and_is_calibrated(data):
    history, _ = data
    bt = radar.backtest(history)
    a = bt["all"]
    assert a["wape_p50"] < 0.75 * a["wape_naive"]
    assert 0.72 <= a["coverage_p10_p90"] <= 0.88
    assert a["below_p10"] < 0.16 and a["above_p90"] < 0.16


def test_quantiles_never_cross(data):
    history, current = data
    model = radar.production(history)
    p = model.predict(current)
    assert (p["p10"] <= p["p50"]).all() and (p["p50"] <= p["p90"]).all()
    assert (p["p10"] >= 0).all()
