"""Feature engineering for the Demand Radar.

All features are known at decision time (the lead date). Demand and its drivers are heavy-tailed and
multiplicative, so volumes enter on a log scale and the model predicts log demand relative to last year;
quantiles survive the shift and the log transform unchanged, so exp(anchor + predicted quantile) is the
demand quantile.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..catalog import OPTIONS

OPTION_CODES = {o.id: i for i, o in enumerate(OPTIONS)}

FEATURES = [
    "option",
    "lead_days",
    "nights",
    "is_flight",
    "is_international",
    "month_sin",
    "month_cos",
    "event_strength",
    "log_ly_demand",
    "log_on_books",
    "log_on_books_ly",
    "pace_yoy",
    "log_searches",
    "search_yoy",
    "look_to_book",
    "soldout_nights_ly",
    "rate_change",
]
CATEGORICAL = ["option"]


def build(df: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=df.index)
    x["option"] = df["option_id"].map(OPTION_CODES).astype("int32")
    x["lead_days"] = df["lead_days"].astype(float)
    x["nights"] = df["nights"].astype(float)
    x["is_flight"] = (df["kind"] == "flight").astype(float)
    x["is_international"] = (df["region"] == "international").astype(float)
    angle = 2 * np.pi * (df["doy"] - 1) / 365.25
    x["month_sin"], x["month_cos"] = np.sin(angle), np.cos(angle)
    x["event_strength"] = df["event_strength"]
    x["log_ly_demand"] = np.log1p(df["ly_demand"])
    x["log_on_books"] = np.log1p(df["on_books"])
    x["log_on_books_ly"] = np.log1p(df["on_books_ly"])
    x["pace_yoy"] = x["log_on_books"] - x["log_on_books_ly"]
    x["log_searches"] = np.log1p(df["searches"])
    x["search_yoy"] = x["log_searches"] - np.log1p(df["searches_ly"])
    x["look_to_book"] = df["searches"] / np.maximum(df["on_books"], 1.0)
    x["soldout_nights_ly"] = df["soldout_nights_ly"].astype(float)
    x["rate_change"] = df["rate_change"]
    return x[FEATURES]


def anchor(df: pd.DataFrame) -> np.ndarray:
    """The models learn demand relative to the same window last year (a log ratio), which lets the trees
    follow growth they never saw in training; the anchor is added back after prediction."""
    return np.log1p(df["ly_demand"].to_numpy())


def target(df: pd.DataFrame) -> np.ndarray:
    return np.log1p(df["demand"].to_numpy()) - anchor(df)
