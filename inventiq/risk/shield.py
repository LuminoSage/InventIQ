"""Risk Shield: turns a plan into actions a buyer can check, each with its reasons in plain English.

* The newsvendor line. A hard unit pays off when the chance it sells, P(demand >= h), is at least
  (hard_cost - salvage) / (sell_price - salvage). That ratio is each option's break-even 'sure to sell'
  level; the optimiser asks for more than that when the risk profile weighs the bad tail.
* Release dates. Allotment goes back to the hotel free of charge up to its release date. We give the
  pickup the buyer should see by then, and how much to hand back if pickup is short.
* Re-pricing. Units already held are compared with the forecast. Where they are likely to go unsold,
  the shield suggests a price cut sized by an assumed price elasticity of demand.
* Supply gaps. Where demand is strong but no connected supplier has stock, it asks for a new supplier.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from ..catalog import TODAY, Option

RELEASE_DAYS = 21  # allotment release date, days before arrival
ELASTICITY = -2.0  # % change in demand for a 1% change in price (assumed)


def breakeven_sure(o: Option) -> float | None:
    if o.sell_price <= o.salvage:
        return None
    return (o.hard_cost - o.salvage) / (o.sell_price - o.salvage)


def pick_stats(o: Option, d: np.ndarray, h: int, a: int) -> dict:
    sold_hard = np.minimum(d, h)
    sold = np.minimum(d, h + a)
    return {
        "p_hard_all_sell": float(np.mean(d >= h)) if h else None,
        "hard_sell_through": float(sold_hard.mean() / h) if h else None,
        "expected_unsold_hard": float((h - sold_hard).mean()),
        "expected_allot_used": float((sold - sold_hard).mean()),
        "p_sold_out": float(np.mean(d > h + a)),
        "expected_lost_demand": float(np.maximum(d - h - a, 0).mean()),
    }


def fmt_inr(v: float) -> str:
    return "₹" + f"{round(v):,}"


def action_for(o: Option, h: int, a: int, unconstrained: tuple[int, int]) -> str:
    if o.supply_cap == 0:
        return "add_supplier"
    if o.hard_cost >= o.sell_price:
        return "renegotiate"
    if h and a:
        return "prebuy_allot"
    if h:
        return "prebuy"
    if a:
        return "allot_only"
    if unconstrained[0] or unconstrained[1]:
        return "over_budget"
    return "watch"


ACTION_LABEL = {
    "prebuy_allot": "Buy + allot",
    "prebuy": "Pre-buy",
    "allot_only": "Allot only",
    "over_budget": "Over budget",
    "watch": "Watch",
    "add_supplier": "Add supplier",
    "renegotiate": "Renegotiate",
}


def reasons(o: Option, f: dict, sig: dict, h: int, a: int, stats: dict, action: str, risk_label: str) -> list[str]:
    u = o.unit
    out = [f"Demand is forecast at {f['p10']:,.0f} to {f['p90']:,.0f} {u}, most likely {f['p50']:,.0f}."]
    drivers = []
    search, pace = float(np.expm1(sig["search_yoy"])), float(np.expm1(sig["pace_yoy"]))  # log changes to %
    if abs(search) >= 0.1:
        drivers.append(f"searches are {'up' if search > 0 else 'down'} {abs(search):.0%} on last year")
    if abs(pace) >= 0.1:
        drivers.append(f"bookings on the books are {'ahead of' if pace > 0 else 'behind'} last year by {abs(pace):.0%}")
    if sig["soldout_nights_ly"]:
        drivers.append(
            f"this window sold out on {sig['soldout_nights_ly']} night{'s' if sig['soldout_nights_ly'] > 1 else ''} last year"
        )
    if drivers:
        out.append("Signals: " + "; ".join(drivers) + ".")
    be = breakeven_sure(o)
    if action in ("prebuy", "prebuy_allot"):
        out.append(
            f"Hard: {h:,} at {fmt_inr(o.hard_cost)}, {stats['p_hard_all_sell']:.0%} likely to all sell "
            f"(break-even is {be:.0%}); expected sell-through {stats['hard_sell_through']:.0%}."
        )
    if a:
        out.append(
            f"Allotment: {a:,} at {fmt_inr(o.allot_cost)} when sold, handed back unsold "
            f"{RELEASE_DAYS} days before arrival; about {stats['expected_allot_used']:,.0f} expected to be used."
        )
    if action == "over_budget":
        out.append(f"Worth buying, but the {risk_label.lower()} plan ranks other options higher for this budget.")
    if action == "watch":
        out.append(
            f"Not worth committing cash at the {risk_label.lower()} risk level: the margin of "
            f"{fmt_inr(o.sell_price - o.hard_cost)} per unit does not cover the downside."
        )
    if action == "add_supplier":
        out.append(
            f"No connected supplier has stock left ({o.suppliers} connected): add a supplier to capture "
            f"about {f['p50']:,.0f} {u} of demand."
        )
    if action == "renegotiate":
        out.append(
            f"The supplier rate {fmt_inr(o.hard_cost)} is above the selling price {fmt_inr(o.sell_price)}: "
            "renegotiate before buying."
        )
    if stats["p_sold_out"] >= 0.25 and action not in ("add_supplier", "renegotiate"):
        out.append(
            f"{stats['p_sold_out']:.0%} chance demand outruns this plan: about "
            f"{stats['expected_lost_demand']:,.0f} {u} would be turned away."
        )
    return out


def alerts(o: Option, f: dict, d: np.ndarray, h: int, a: int, sig: dict) -> list[dict]:
    out = []
    if a:
        release = o.start - timedelta(days=RELEASE_DAYS)
        on_track = f["p50"] * np.exp(-RELEASE_DAYS / o.pace_days)
        keep = max(0, int(np.quantile(d, 0.75)) - h)
        out.append(
            {
                "kind": "release",
                "option_id": o.id,
                "date": release.isoformat(),
                "severity": "info",
                "title": f"Release check for {o.name} on {release.strftime('%d %b')}",
                "detail": (
                    f"Expect about {on_track:,.0f} {o.unit} on the books by then. If pickup is short of that, "
                    f"keep {min(a, keep):,} of the {a:,} allotment and hand back the rest."
                ),
            }
        )
    if o.held:
        unsold = float(np.maximum(o.held - d, 0).mean())
        share = unsold / o.held
        if share >= 0.05:
            cut = min(0.15, share / abs(ELASTICITY))
            out.append(
                {
                    "kind": "reprice",
                    "option_id": o.id,
                    "date": TODAY.isoformat(),
                    "severity": "warning",
                    "title": f"Re-price {o.name}: {o.held:,} {o.unit} held",
                    "detail": (
                        f"About {unsold:,.0f} of them are expected to go unsold at today's price. "
                        f"A cut of about {cut:.0%} should lift demand enough to clear them "
                        f"(assumes a price elasticity of {ELASTICITY:g})."
                    ),
                    "suggested_cut": round(cut, 3),
                }
            )
    if o.supply_cap == 0 and f["p50"] > 0:
        out.append(
            {
                "kind": "supplier",
                "option_id": o.id,
                "date": TODAY.isoformat(),
                "severity": "warning",
                "title": f"Add a supplier for {o.name}",
                "detail": (
                    f"Only {o.suppliers} suppliers are connected and none has stock left, "
                    f"against demand of about {f['p50']:,.0f} {o.unit}."
                ),
            }
        )
    if sig["rate_change"] >= 0.08 and (h or a):
        out.append(
            {
                "kind": "buy_now",
                "option_id": o.id,
                "date": TODAY.isoformat(),
                "severity": "info",
                "title": f"Supplier rates for {o.name} are rising",
                "detail": f"Rates are up about {np.expm1(sig['rate_change']):.0%} on last year: confirm this buy within a week.",
            }
        )
    return out
