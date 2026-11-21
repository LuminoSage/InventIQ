"""Demand Radar: a range forecast (P10, P50, P90) for every stay window.

Three LightGBM models are trained with the quantile (pinball) loss, one per quantile, on log demand.
The P10 to P90 band is then calibrated with conformalized quantile regression (CQR), one side at a
time: on a later calibration season we measure how far actual demand fell below P10 and above P90, and
move each edge by the 90th percentile of its misses, so about 10% of outcomes land below the band and
10% above it on data the models never saw.

``backtest()`` replays this on the last finished season and reports the error against a seasonal-naive
forecast (same window last year), the way a planner would judge it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd

from .features import CATEGORICAL, anchor, build, target

QUANTILES = (0.1, 0.5, 0.9)
PARAMS = dict(
    n_estimators=700,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=25,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    random_state=7,
    deterministic=True,
    force_row_wise=True,
    n_jobs=1,
    verbose=-1,
)


@dataclass
class Radar:
    models: dict[float, lgb.LGBMRegressor] = field(default_factory=dict)
    widen_lo: float = 0.0  # CQR corrections on the log scale for the lower and upper edge
    widen_hi: float = 0.0

    def fit(self, train: pd.DataFrame, calib: pd.DataFrame | None = None) -> Radar:
        x, y = build(train), target(train)
        for q in QUANTILES:
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, **PARAMS)
            m.fit(x, y, categorical_feature=CATEGORICAL)
            self.models[q] = m
        if calib is not None and len(calib):
            lo, _, hi = self._raw(calib)
            yc = target(calib) + anchor(calib)
            level = min(1.0, 0.9 * (1 + 1 / len(yc)))
            self.widen_lo = float(np.quantile(lo - yc, level))
            self.widen_hi = float(np.quantile(yc - hi, level))
        return self

    def _raw(self, df: pd.DataFrame) -> np.ndarray:
        x = build(df)
        preds = np.vstack([self.models[q].predict(x) for q in QUANTILES]) + anchor(df)
        return np.sort(preds, axis=0)  # no crossing quantiles

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        lo, mid, hi = self._raw(df)
        lo, hi = lo - self.widen_lo, hi + self.widen_hi
        out = pd.DataFrame(
            {
                "p10": np.expm1(lo),
                "p50": np.expm1(mid),
                "p90": np.expm1(hi),
            },
            index=df.index,
        ).clip(lower=0)
        out["p10"] = np.minimum(out["p10"], out["p50"])
        out["p90"] = np.maximum(out["p90"], out["p50"])
        return out

    def importance(self) -> list[dict]:
        m = self.models[0.5]
        gain = m.booster_.feature_importance(importance_type="gain")
        names = m.booster_.feature_name()
        total = gain.sum() or 1.0
        pairs = sorted(zip(names, gain / total, strict=True), key=lambda p: -p[1])
        return [{"feature": n, "share": round(float(s), 4)} for n, s in pairs]


def split(history: pd.DataFrame, calib_from: date, test_from: date | None = None):
    s = pd.to_datetime(history["start"])
    train = history[s < pd.Timestamp(calib_from)]
    if test_from is None:
        return train, history[s >= pd.Timestamp(calib_from)], history.iloc[0:0]
    calib = history[(s >= pd.Timestamp(calib_from)) & (s < pd.Timestamp(test_from))]
    test = history[s >= pd.Timestamp(test_from)]
    return train, calib, test


def pinball(y: np.ndarray, q: np.ndarray, tau: float) -> float:
    d = y - q
    return float(np.mean(np.maximum(tau * d, (tau - 1) * d)))


def evaluate(df: pd.DataFrame, pred: pd.DataFrame) -> dict:
    y = df["demand"].to_numpy()
    naive = df["ly_demand"].to_numpy()
    p50 = pred["p50"].to_numpy()
    wape = float(np.abs(y - p50).sum() / y.sum())
    naive_wape = float(np.abs(y - naive).sum() / y.sum())
    return {
        "rows": int(len(df)),
        "wape_p50": round(wape, 4),
        "wape_naive": round(naive_wape, 4),
        "improvement": round(1 - wape / naive_wape, 4) if naive_wape else None,
        "coverage_p10_p90": round(float(np.mean((y >= pred["p10"]) & (y <= pred["p90"]))), 4),
        "below_p10": round(float(np.mean(y < pred["p10"])), 4),
        "above_p90": round(float(np.mean(y > pred["p90"])), 4),
        "pinball": {
            f"p{int(q * 100)}": round(pinball(y, pred[f"p{int(q * 100)}"].to_numpy(), q), 2) for q in QUANTILES
        },
    }


def backtest(history: pd.DataFrame) -> dict:
    """Train before Jul 2024, calibrate on Jul 2024 to Jun 2025, test on stays from Jul 2025."""
    train, calib, test = split(history, date(2024, 7, 1), date(2025, 7, 1))
    radar = Radar().fit(train, calib)
    pred = radar.predict(test)
    peak = test["event_strength"] >= 0.6
    by_lead = {
        int(lead): evaluate(test[test["lead_days"] == lead], pred[test["lead_days"] == lead])["wape_p50"]
        for lead in sorted(test["lead_days"].unique())
    }
    by_option = {}
    for oid, g in test.groupby("option_id"):
        e = evaluate(g, pred.loc[g.index])
        by_option[oid] = {"wape_p50": e["wape_p50"], "wape_naive": e["wape_naive"], "coverage": e["coverage_p10_p90"]}
    return {
        "train_rows": int(len(train)),
        "calibration_rows": int(len(calib)),
        "test_period": "stays from 1 Jul 2025 to 20 Nov 2026",
        "all": evaluate(test, pred),
        "peak_windows": evaluate(test[peak], pred[peak]),
        "by_lead_wape": by_lead,
        "by_option": by_option,
        "band_correction_log": {"p10": round(radar.widen_lo, 4), "p90": round(radar.widen_hi, 4)},
        "importance": radar.importance()[:8],
    }


def production(history: pd.DataFrame) -> Radar:
    """The model the desk uses: trained up to Jul 2025, calibrated on everything since."""
    train, calib, _ = split(history, date(2025, 7, 1))
    return Radar().fit(train, calib)
