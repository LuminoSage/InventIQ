# Roadmap

## Now: working prototype

* Range forecasts with calibrated P10 to P90 bands, back-tested against seasonal naive.
* 10,000 joint futures with learned cross-market correlation.
* A CVaR-aware budget optimiser, fast enough for a slider and checked against an exact solver.
* A buying desk with approve, edit, reject and undo, an append-only audit trail, and alerts.

## Next four weeks: pilot on real bookings

1. **Data.** Load two seasons of booking, search and supplier-rate history for three destinations; build
   unconstrained demand from bookings plus searches that hit "no availability".
2. **Back-test on last season.** Replay each pre-buy decision date with only the data known then, and
   compare InventIQ's plan with what was actually bought.
3. **Shadow mode.** Run beside the buying team for one booking window: InventIQ recommends, the team
   decides, and both are recorded.
4. **Measure:** sold-out nights on peak dates, sell-through of hard units, unsold units handed to
   distressed channels, and risk-adjusted return per rupee committed.

## Later

* **Re-optimise weekly** as pickup arrives, and recommend top-ups or early releases within a season.
* **Supplier negotiation support:** the price at which a hard block becomes worth buying, per option.
* **Learn price elasticity** from past re-pricing, instead of the assumed −2.
* **Group and corporate blocks** as a second demand stream with its own cancellation curve.
* **Authentication and roles** (buyer, approver, finance), with approval limits per role.
