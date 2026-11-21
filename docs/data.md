# Data

## Why synthetic

TBO's booking history is not public. To build and test the full pipeline honestly, InventIQ ships a
generator that produces data with the same shape and the same statistical traps as a real distributor's
feeds: seasonality, moving festivals, growth, correlated shocks, censored demand and noisy early signals.
Every model is evaluated only on data it never trained on.

## How demand is generated

For each option, a weekly series of stay windows (same weekday and length as the option) runs from
January 2021 to the option's window in the coming season.

```
expected(t) = peak × (1 + growth)^years(t) × shape(t) / shape(option window)
shape(t)    = base + Σ_events height · exp(−½ · (days to event / width)²)
demand(t)   = expected(t) · exp(shock(t) − ½σ²)
shock(t)    = market(week) + region(week) + cluster(week) + own noise
```

* **Events** include New Year, Christmas, Diwali and Chinese New Year (on their real, moving dates),
  wedding seasons, Republic Day, the Dubai Shopping Festival, snow seasons and school holidays.
* **Shocks** are shared by ISO week of the stay's midpoint: one for the whole market, one per region
  (India or overseas) and one per cluster (for example Goa hotels with Delhi to Goa seats). This creates
  the cross-market correlation the copula then has to learn.

## Signals, as a buyer would see them

At each lead time (28, 42, 56, 70 and 84 days before arrival, and the real lead for the coming season):

| Column | How it is generated |
|---|---|
| `on_books` | Poisson draw from demand × booking-curve share `exp(−lead / pace_days)` |
| `searches` | 9 × expected level × `exp(0.45 · shock + noise)`: intent shows early, but only part of the shock |
| `ly_demand` | the same window 52 weeks earlier |
| `on_books_ly`, `searches_ly` | the same signals for last year's window at the same lead |
| `soldout_nights_ly` | nights last year when demand exceeded 85% of market capacity |
| `rate_change` | supplier rate change on last year, following expected demand, capped at −15% to +20% |
| `event_strength` | the calendar's bump at the window midpoint |

## Data dictionary

**`history`**: one row per option, stay window and lead time, for stays finished before the planning date.

| Column | Type | Description |
|---|---|---|
| `option_id` | str | option key, for example `goa` |
| `start` | date | first night of the stay window |
| `nights` | int | window length |
| `lead_days` | int | days before arrival the signals were read |
| `month`, `doy` | int | month and day of year at the window midpoint |
| `region`, `kind` | str | `india` or `international`; `hotel` or `flight` |
| `event_strength` | float | calendar intensity |
| `ly_demand` | float | last year's demand for the window |
| `on_books`, `on_books_ly` | float | units booked at this lead, this year and last |
| `searches`, `searches_ly` | float | searches in the weeks before the lead date |
| `soldout_nights_ly` | int | sold-out nights last year |
| `rate_change` | float | supplier rate change on last year (log scale) |
| `demand` | float | realised unconstrained demand (the target) |

**`current`**: one row per option for the coming season, with the same columns except `demand`.

## Plugging in real data

Replace `inventiq/data/synth.py::generate` with a loader that returns the same two tables:

* **Demand** = confirmed bookings + estimated demand lost on sold-out nights (from searches that ended
  on "no availability").
* **Signals** come from the booking ledger (on the books at a lead), search logs, the supplier contract
  store and a holiday calendar.
* The economics in `catalog.py` come from supplier contracts (hard and allotment rates, caps and release
  terms) and the pricing system.

The back-test then reports the real accuracy before any plan is trusted.
