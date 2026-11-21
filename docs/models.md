# Models and maths

This page explains every formula InventIQ uses, in the order the engines run, and why each choice was made.

## 1. Demand Radar: range forecasts

### What is forecast

For each option (a market and a stay window, such as *Goa, 28 Dec to 1 Jan*) the target is
**unconstrained demand**: units sold plus the demand turned away on sold-out nights. A forecast is made
at a **lead time**, a number of days before arrival, using only what is known on that day.

### Features

| Feature | Meaning |
|---|---|
| `log_ly_demand` | demand for the same window last year (the anchor) |
| `log_on_books`, `pace_yoy` | units already booked, and how that compares with the same lead last year |
| `log_searches`, `search_yoy`, `look_to_book` | search volume, its change on last year, searches per booking |
| `soldout_nights_ly` | nights that sold out last year: a sign that demand was capped |
| `rate_change` | the supplier rate change on last year |
| `event_strength`, `month_sin`, `month_cos` | the event calendar and the time of year |
| `lead_days`, `nights`, `is_flight`, `is_international`, `option` | the shape of the decision and the market |

### Model

Three LightGBM gradient-boosted tree models are trained with the **quantile (pinball) loss**, one each
for τ = 0.1, 0.5 and 0.9:

```
L_τ(y, q) = max(τ·(y − q), (τ − 1)·(y − q))
```

Minimising it makes `q` the τ-quantile of demand given the features. Two choices matter:

* **The target is a log ratio to last year:** `log(1 + demand) − log(1 + demand last year)`. Trees cannot
  extrapolate beyond the values they saw, so a model of raw demand under-forecasts a market that keeps
  growing. Modelling the ratio lets the anchor carry the level, and the trees learn what changed.
  Quantiles survive this shift and the log transform, so the demand quantile is
  `exp(anchor + q) − 1`.
* **Quantiles are sorted** after prediction, so P10 ≤ P50 ≤ P90 always holds.

### Calibration: conformalized quantile regression (CQR)

Quantile models are often too confident on new data. On a calibration season the models never trained
on, we measure the misses on each side:

```
s_lo = P10(x) − y          (positive when the actual fell below P10)
s_hi = y − P90(x)          (positive when the actual rose above P90)
```

The lower edge moves down by the 90th percentile of `s_lo`, and the upper edge up by the 90th percentile
of `s_hi` (with the finite-sample correction `⌈(n + 1)·0.9⌉ / n`). Done one side at a time, this targets
10% of outcomes below the band and 10% above it, which is what a buyer reading "P10" and "P90" expects.

### Back-test

* **Train:** stays before 1 Jul 2024. **Calibrate:** Jul 2024 to Jun 2025. **Test:** stays from 1 Jul 2025
  to the planning date, 4,330 forecasts at leads of 28 to 84 days.
* **Baseline:** seasonal naive (the same window last year), the planner's usual reference.
* **Metrics:** WAPE = Σ|y − P50| / Σy; band coverage; pinball loss per quantile.

Result: WAPE 16.0% against 32.8% for the baseline, coverage 80.1% (9.7% below, 10.2% above).

## 2. Joint futures

### Marginals: split log-normal

From P10, P50 and P90 of one option:

```
m = log(1 + P50)
s_down = (m − log(1 + P10)) / 1.2816
s_up   = (log(1 + P90) − m) / 1.2816
demand(z) = exp(m + z·s_down) − 1   if z < 0
          = exp(m + z·s_up)   − 1   if z ≥ 0
```

for a standard normal `z`. It reproduces the three quantiles exactly and keeps any skew in the forecast:
a peak week is usually more uncertain on the upside.

### Dependence: a Gaussian copula

Markets that share travellers move together. Goa hotels and Delhi to Goa seats peak on the same nights,
and a weak rupee hits every overseas market at once. Treating options as independent would understate
how bad the bad futures are. So:

1. On the calibration season, each forecast error is mapped back to its `z` (the inverse of the map above).
2. Errors are matched on the ISO week of the stay's midpoint, and pairwise correlations are measured.
3. Sample correlations from one season are noisy, so they are **shrunk halfway** towards a structured target:
   the average correlation of pairs in the same cluster, of pairs in the same region, and of all other pairs.
4. The result is repaired to the nearest valid correlation matrix (negative eigenvalues clipped, diagonal
   rescaled to 1).

Futures are then `Z = N(0, 1)^{10000×12} · Lᵀ`, with `L` the Cholesky factor, mapped through each
option's marginal. The seed is fixed, so every run sees the same 10,000 futures.

## 3. Portfolio Optimizer

### Payoff of one option

For `h` hard units and `a` allotment units, in a future with demand `d`:

```
sold      = min(d, h + a)
sold_hard = min(d, h)
profit    = price · sold
          − hard_cost · h                       (paid upfront, sold or not)
          − allot_cost · (sold − sold_hard)     (paid only when an allotment unit sells)
          − allot_fee · a                       (non-refundable holding fee, 3% of the allotment rate)
          + salvage · (h − sold_hard)           (unsold hard units dumped at about 15% of cost)
```

### Objective

```
maximise   (1 − w) · E[profit] + w · CVaR₅%[profit]
subject to Σ cash(h_i, a_i) ≤ budget,  h_i ≤ supply_i,  a_i ≤ allotment cap_i
```

`CVaR₅%` is the average profit over the worst 5% of futures. Unlike value-at-risk it looks at the whole
bad tail, and unlike variance it does not penalise upside. The weight `w` is the risk profile: Cautious
0.6, Balanced 0.3, Bold 0.1.

### Candidates

For each option, hard levels are the demand quantiles at "sure to sell" levels of 99%, 97%, 95%, 92%,
90%, 85%, 80%, 75%, 70%, 60% and 50%, plus a ladder of smaller blocks (¼, ½, ¾ of the safest level) so
that a buy can grow in steps. These are crossed with 0, half or all of the allotment on offer: 422 candidate
plans across the 12 options at a ₹2 crore budget.

### Exact solve: a mixed-integer programme

With binary `x_ik` (option `i` takes candidate `k`) and the Rockafellar–Uryasev form of CVaR:

```
maximise   (1 − w) · (1/S) Σ_s Σ_ik P_iks x_ik  +  w · (η − (1 / (0.05·S)) Σ_s u_s)
subject to u_s ≥ η − Σ_ik P_iks x_ik,  u_s ≥ 0          for every future s
           Σ_k x_ik = 1                                  for every option i
           Σ_ik cash_ik x_ik ≤ budget
```

SCIP solves this through Google OR-Tools on 600 futures stratified across the profit range (so the tail
is represented), warm-started from the fast plan. It takes 7 to 12 seconds.

### Fast solve: Lagrangian search

The desk re-plans every time the budget slider moves, so it needs about a second:

1. **Price the budget.** For a price μ per rupee of cash, coordinate ascent maximises
   `objective − μ · cash`, evaluating all candidates of one option against all futures at once
   (vectorised: one partial sort per candidate for the CVaR).
2. **Bisection on μ** brackets the budget.
3. **Three routes to a plan that fits:**
   * climb from the best plans just under the budget;
   * step down from the plan just over it, dropping the units that cost the least objective per rupee;
   * grow a plan from nothing, always taking the upgrade with the most objective per rupee.
4. Each route ends with an ascent under the hard budget, and the best plan wins.

Against the exact programme the fast search is within 0.82% in every case tested (0.06% median), in
0.6 to 0.9 seconds.

### Baseline

"Buy the P90 forecast upfront": for options in order of margin, buy the P90 forecast as hard units until
the budget runs out. It is scored on the same futures.

## 4. Risk Shield

* **Newsvendor break-even.** A hard unit is worth buying when `P(demand ≥ h) · (price − salvage) ≥
  hard_cost − salvage`, so the break-even "sure to sell" level is
  `(hard_cost − salvage) / (price − salvage)`. Each pick reports how likely its hard units are to all sell
  against this line.
* **Release check.** Allotment goes back free up to 21 days before arrival. Under the booking curve
  `share booked at lead L = exp(−L / τ)`, the shield gives the pickup the buyer should see by the release
  date, and how much to keep (up to the 75th percentile of demand) if pickup is short.
* **Re-pricing.** For units already held, the expected unsold count is `E[(held − d)⁺]`. With an assumed
  price elasticity of −2, a price cut of `unsold share / 2` (capped at 15%) is suggested.
* **Supply gaps.** No connected supplier has stock left while demand is strong: add a supplier.
* **Renegotiate.** The supplier rate is above the selling price.
* **Rising rates.** Supplier rates up 8% or more on last year: confirm the buy within a week.

## References

* Koenker and Bassett, *Regression Quantiles*, Econometrica, 1978.
* Ke et al., *LightGBM: A Highly Efficient Gradient Boosting Decision Tree*, NeurIPS 2017.
* Romano, Patterson and Candès, *Conformalized Quantile Regression*, NeurIPS 2019.
* Rockafellar and Uryasev, *Optimization of Conditional Value-at-Risk*, Journal of Risk, 2000.
* Ledoit and Wolf, *Honey, I Shrunk the Sample Covariance Matrix*, Journal of Portfolio Management, 2004.
* Arrow, Harris and Marschak, *Optimal Inventory Policy*, Econometrica, 1951 (the newsvendor model).
