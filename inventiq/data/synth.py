"""Synthetic booking history, shaped like a B2B travel distributor's own feeds.

For every option in the catalogue we build a weekly series of stay windows (same weekday and length
as the option) from January 2021 up to the option's own window in the coming season. Each window has:

* a realised, unconstrained demand (bookings plus the demand lost to sold-out nights), and
* the signals a buyer could see before the stay, at several lead times: units already on the books,
  searches, the same window last year, sold-out nights last year and the supplier rate change.

Demand = calendar level x yearly growth x shocks. The shocks are shared through a factor structure
(the whole market, a region, a cluster of markets that share travellers), so markets move together the
way they do in real data. Every draw comes from one seeded generator, so every run is identical.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..catalog import OPTIONS, TODAY, Option

HISTORY_START = date(2021, 1, 4)
LEADS = (28, 42, 56, 70, 84)  # days before the stay at which the signals are read
SEED = 2026

# log-scale volatility of the shared weekly shocks
SIGMA_MARKET, SIGMA_REGION, SIGMA_CLUSTER = 0.05, 0.07, 0.10
VOL_SCALE = 1.4  # travel demand is volatile: scales each option's own noise


def _event_strength(o: Option, mid: date) -> np.ndarray:
    """The calendar part of demand at a window midpoint: off-season base plus each event's bump."""
    s = 0.0
    for ev in o.events:
        best = min(abs((mid - ev.centre(y)).days) for y in (mid.year - 1, mid.year, mid.year + 1))
        s += ev.height * np.exp(-0.5 * (best / ev.width) ** 2)
    return s


def _calendar(o: Option, starts: list[date]) -> np.ndarray:
    """Expected demand per window: peak x growth x calendar shape, scaled so the option's window = peak."""
    half = timedelta(days=o.nights / 2)
    shape = np.array([o.base + _event_strength(o, t + half) for t in starts])
    ref = o.base + _event_strength(o, o.start + half)
    years = np.array([(t - o.start).days / 365.25 for t in starts])
    return o.peak * (1 + o.growth) ** years * shape / ref


def _weekly_shocks(rng: np.random.Generator) -> dict:
    """Shared weekly shocks, keyed by ISO (year, week): one for the market, per region and per cluster."""
    weeks = {}
    d = HISTORY_START - timedelta(days=400)
    end = date(2027, 6, 1)
    regions = sorted({o.region for o in OPTIONS})
    clusters = sorted({o.cluster for o in OPTIONS})
    while d <= end:
        key = d.isocalendar()[:2]
        weeks[key] = {
            "market": rng.normal(0, SIGMA_MARKET),
            **{f"r:{r}": rng.normal(0, SIGMA_REGION) for r in regions},
            **{f"c:{c}": rng.normal(0, SIGMA_CLUSTER) for c in clusters},
        }
        d += timedelta(days=7)
    return weeks


def generate(seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (history, current).

    history: one row per option, stay window and lead time, for windows that finished before TODAY,
             with the signals and the realised demand.
    current: one row per option for its coming window, with the signals as of TODAY. Its realised
             demand is kept in ``hidden_demand`` only so tests can check the forecast; the models never
             read it.
    """
    rng = np.random.default_rng(seed)
    shocks = _weekly_shocks(rng)
    rows, current = [], []

    for o in OPTIONS:
        n = (o.start - HISTORY_START).days // 7
        starts = [o.start - timedelta(days=7 * k) for k in range(n, -1, -1)]  # oldest first, ends at o.start
        level = _calendar(o, starts)
        # shared shocks are keyed by the ISO week of the stay's midpoint, so windows that overlap in
        # time (Goa hotels and Delhi to Goa seats over New Year) share them
        keys = [(t + timedelta(days=o.nights / 2)).isocalendar()[:2] for t in starts]
        shared = np.array(
            [shocks[k]["market"] + shocks[k][f"r:{o.region}"] + shocks[k][f"c:{o.cluster}"] for k in keys]
        )
        vol = o.noise * VOL_SCALE
        idio_sd = np.sqrt(max(vol**2 - SIGMA_MARKET**2 - SIGMA_REGION**2 - SIGMA_CLUSTER**2, 0.006))
        shock = shared + rng.normal(0, idio_sd, len(starts))
        demand = np.maximum(0, np.round(level * np.exp(shock - 0.5 * vol**2)))
        capacity = 0.9 * o.peak * (1 + o.growth) ** np.array([(t - o.start).days / 365.25 for t in starts])
        rate_chg = np.zeros(len(starts))

        # signals per lead, drawn once per window and lead
        sig = {}
        for lead in LEADS + ("now",):
            booked_share = np.exp(-(o.lead_days if lead == "now" else lead) / o.pace_days)
            sig[lead] = {
                # bookings already made: a Poisson draw from the share of demand booked by this lead
                "on_books": rng.poisson(demand * booked_share * np.exp(rng.normal(0, 0.15, len(starts)))).astype(float),
                # searches show intent early: they carry the expected level and only part of this
                # window's shock, plus their own noise
                "searches": np.round(9.0 * level * np.exp(0.45 * shock + rng.normal(0, 0.22, len(starts)))),
            }

        for i, t in enumerate(starts):
            if i < 52:
                continue  # the first year only feeds the "last year" signals
            ly = i - 52
            # suppliers move rates with expected demand, within a contract band
            rate_chg[i] = np.clip(
                0.35 * np.log(level[i] / level[ly]) + 0.25 * shared[i] + rng.normal(0, 0.03), -0.15, 0.2
            )
            soldout_ly = int(np.clip(np.round(o.nights * (demand[ly] / capacity[ly] - 0.85) / 0.3), 0, o.nights))
            mid = t + timedelta(days=o.nights / 2)
            base = {
                "option_id": o.id,
                "start": t,
                "month": mid.month,
                "doy": mid.timetuple().tm_yday,
                "nights": o.nights,
                "region": o.region,
                "kind": o.kind,
                "event_strength": float(_event_strength(o, mid)),
                "ly_demand": float(demand[ly]),
                "soldout_nights_ly": soldout_ly,
                "rate_change": float(rate_chg[i]),
            }
            leads = ("now",) if t == o.start else LEADS
            for lead in leads:
                lead_days = o.lead_days if lead == "now" else lead
                if lead != "now" and t + timedelta(days=o.nights) > TODAY:
                    continue  # not finished yet: no realised demand to learn from
                if lead != "now" and t - timedelta(days=lead_days) > TODAY:
                    continue
                s, s_ly = sig[lead], sig[lead]
                row = {
                    **base,
                    "lead_days": lead_days,
                    "on_books": float(s["on_books"][i]),
                    "on_books_ly": float(s_ly["on_books"][ly]),
                    "searches": float(s["searches"][i]),
                    "searches_ly": float(s_ly["searches"][ly]),
                }
                if lead == "now":
                    current.append({**row, "hidden_demand": float(demand[i])})
                else:
                    rows.append({**row, "demand": float(demand[i])})

    history = pd.DataFrame(rows).sort_values(["start", "option_id", "lead_days"]).reset_index(drop=True)
    return history, pd.DataFrame(current).set_index("option_id").loc[[o.id for o in OPTIONS]].reset_index()
