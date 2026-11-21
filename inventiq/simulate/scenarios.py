"""Turn range forecasts into 10,000 joint futures.

Marginals: each option's P10, P50 and P90 define a split log-normal. Below the median, log demand
spreads by (log P50 - log P10) / 1.2816 per standard deviation, above it by (log P90 - log P50) / 1.2816,
so a forecast that is more uncertain on the upside keeps its skew.

Dependence: a Gaussian copula. Markets that share travellers move together (Goa hotels and Delhi to Goa
seats peak on the same nights), so we estimate the correlation of forecast errors from the calibration
season, shrink it towards a cluster and region average for stability, repair it to a valid correlation
matrix and draw correlated standard normals through its Cholesky factor. Ignoring this would understate the portfolio's bad tail.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

Z90 = 1.2815515655446004
N_SCENARIOS = 10_000
SEED = 11


def _scales(p10, p50, p90):
    l10, l50, l90 = np.log1p(p10), np.log1p(p50), np.log1p(p90)
    return l50, np.maximum((l50 - l10) / Z90, 1e-4), np.maximum((l90 - l50) / Z90, 1e-4)


def to_demand(z: np.ndarray, p10, p50, p90) -> np.ndarray:
    """Map standard normal draws to demand through the split log-normal quantile function."""
    mid, down, up = _scales(np.asarray(p10), np.asarray(p50), np.asarray(p90))
    z = np.clip(z, -4.0, 4.0)
    log_d = mid + np.where(z < 0, z * down, z * up)
    return np.maximum(np.expm1(log_d), 0.0)


def to_z(y, p10, p50, p90) -> np.ndarray:
    """The inverse: how many (side-specific) standard deviations an outcome sits from the median."""
    mid, down, up = _scales(np.asarray(p10), np.asarray(p50), np.asarray(p90))
    r = np.log1p(np.asarray(y)) - mid
    return np.where(r < 0, r / down, r / up)


def nearest_correlation(r: np.ndarray, floor: float = 1e-3) -> np.ndarray:
    """Clip negative eigenvalues and rescale to a unit diagonal: a valid correlation matrix."""
    w, v = np.linalg.eigh((r + r.T) / 2)
    fixed = v @ np.diag(np.maximum(w, floor)) @ v.T
    d = np.sqrt(np.diag(fixed))
    return fixed / np.outer(d, d)


def estimate_correlation(
    rows: pd.DataFrame,
    pred: pd.DataFrame,
    ids: list[str],
    groups: dict[str, tuple[str, str]],
    shrink: float = 0.5,
    min_overlap: int = 20,
) -> np.ndarray:
    """Correlation of forecast errors between options, matched on the ISO week of the stay midpoint.

    Pairwise sample correlations from one or two seasons are noisy, so they are shrunk halfway towards a
    structured target: the average sample correlation of pairs in the same cluster, of pairs in the same
    region, and of all other pairs. ``groups`` maps an option id to its (cluster, region).
    """
    z = to_z(rows["demand"], pred["p10"], pred["p50"], pred["p90"])
    mid = pd.to_datetime(rows["start"]) + pd.to_timedelta(rows["nights"] / 2, unit="D")
    week = mid.dt.isocalendar()
    frame = pd.DataFrame(
        {"option_id": rows["option_id"].to_numpy(), "z": z, "wk": (week["year"] * 100 + week["week"]).to_numpy()}
    )
    wide = frame.groupby(["wk", "option_id"])["z"].mean().unstack().reindex(columns=ids)
    k = len(ids)
    sample = np.full((k, k), np.nan)
    np.fill_diagonal(sample, 1.0)
    for i in range(k):
        for j in range(i + 1, k):
            pair = wide[[ids[i], ids[j]]].dropna()
            if len(pair) >= min_overlap and pair.std().min() > 0:
                sample[i, j] = sample[j, i] = float(np.corrcoef(pair.iloc[:, 0], pair.iloc[:, 1])[0, 1])

    def kind(i: int, j: int) -> str:
        (ci, ri), (cj, rj) = groups[ids[i]], groups[ids[j]]
        return "cluster" if ci == cj else "region" if ri == rj else "other"

    means = {}
    for name in ("cluster", "region", "other"):
        vals = [
            sample[i, j] for i in range(k) for j in range(i + 1, k) if kind(i, j) == name and not np.isnan(sample[i, j])
        ]
        means[name] = float(np.mean(vals)) if vals else 0.0
    target = np.eye(k)
    for i in range(k):
        for j in range(k):
            if i != j:
                target[i, j] = means[kind(i, j)]
    blended = np.where(np.isnan(sample), target, (1 - shrink) * sample + shrink * target)
    return nearest_correlation(blended)


@dataclass
class Scenarios:
    ids: list[str]
    demand: np.ndarray  # shape (N, options)
    correlation: np.ndarray

    def column(self, option_id: str) -> np.ndarray:
        return self.demand[:, self.ids.index(option_id)]


def simulate(forecast: pd.DataFrame, correlation: np.ndarray, n: int = N_SCENARIOS, seed: int = SEED) -> Scenarios:
    """forecast: one row per option, indexed by option id, with p10, p50 and p90."""
    rng = np.random.default_rng(seed)
    chol = np.linalg.cholesky(correlation)
    z = rng.standard_normal((n, len(forecast))) @ chol.T
    d = to_demand(z, forecast["p10"].to_numpy(), forecast["p50"].to_numpy(), forecast["p90"].to_numpy())
    return Scenarios(list(forecast.index), np.round(d), correlation)
