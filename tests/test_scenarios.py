import numpy as np
import pandas as pd

from inventiq.simulate import scenarios as sc


def test_quantile_map_round_trips():
    z = np.linspace(-3, 3, 13)
    d = sc.to_demand(z, 100.0, 150.0, 260.0)
    assert np.allclose(sc.to_z(d, 100.0, 150.0, 260.0), z, atol=1e-9)


def test_marginals_match_the_forecast():
    f = pd.DataFrame({"p10": [100.0, 400.0], "p50": [150.0, 500.0], "p90": [260.0, 580.0]}, index=["a", "b"])
    s = sc.simulate(f, np.array([[1.0, 0.5], [0.5, 1.0]]), n=40_000)
    for i, oid in enumerate(f.index):
        q = np.quantile(s.demand[:, i], [0.1, 0.5, 0.9])
        assert np.allclose(q, f.loc[oid].to_numpy(), rtol=0.03)


def test_copula_carries_the_correlation():
    f = pd.DataFrame({"p10": [100.0, 100.0], "p50": [150.0, 150.0], "p90": [200.0, 200.0]}, index=["a", "b"])
    s = sc.simulate(f, np.array([[1.0, 0.6], [0.6, 1.0]]), n=40_000)
    r = np.corrcoef(sc.to_z(s.demand[:, 0], 100, 150, 200), sc.to_z(s.demand[:, 1], 100, 150, 200))[0, 1]
    assert abs(r - 0.6) < 0.03


def test_nearest_correlation_repairs_an_invalid_matrix():
    bad = np.array([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]])
    fixed = sc.nearest_correlation(bad)
    assert np.allclose(np.diag(fixed), 1.0)
    assert np.linalg.eigvalsh(fixed).min() > 0
