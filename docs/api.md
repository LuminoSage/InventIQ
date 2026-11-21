# API

Base URL: `http://127.0.0.1:8000`. Interactive docs (OpenAPI): `/docs`. All amounts are in rupees.

| Method | Path | What it returns |
|---|---|---|
| GET | `/api/health` | `{"status": "ok", "version": "1.0.0"}` |
| GET | `/api/meta` | season, planning date, default budget, number of futures, risk profiles |
| GET | `/api/options` | the 12 options: economics, P10/P50/P90 forecast, booking signals |
| GET | `/api/backtest` | out-of-sample accuracy: WAPE, coverage, pinball loss, by lead time and option, feature importance |
| GET | `/api/correlation` | the correlation matrix used to draw joint futures |
| POST | `/api/plan` | the optimised plan for a budget and risk profile |
| GET | `/api/plan?budget=&risk=` | the same, for quick checks in a browser |
| GET | `/api/decisions` | decisions in force per option, and the full log |
| POST | `/api/decisions` | record approve, edit, reject or undo |
| DELETE | `/api/decisions` | clear the log (demo reset) |

## Plan

```http
POST /api/plan
Content-Type: application/json

{ "budget": 20000000, "risk": "balanced", "exact": false }
```

`risk` is `cautious`, `balanced` or `bold`. `exact: true` also runs the SCIP mixed-integer solve.

Response (abridged):

```json
{
  "budget": 20000000,
  "risk": "balanced",
  "solver": { "method": "Lagrangian search", "seconds": 0.71, "candidates": 422, "exact_status": "not run" },
  "summary": { "cash": 19998200, "expected": 8200000, "cvar": 7110000, "p_loss": 0.0, "hard_units": 2964, "allot_units": 1550 },
  "baseline": { "name": "Buy the P90 forecast upfront", "expected": 3440000, "cvar": 340000, "p_loss": 0.01 },
  "histogram": { "edges": [], "counts": [[], []] },
  "rows": [
    {
      "id": "goa", "rank": 2, "action": "prebuy_allot", "label": "Buy + allot", "locked": false,
      "plan": { "hard": 493, "allot": 280, "cash": 2909600 },
      "forecast": { "p10": 546, "p50": 680, "p90": 951 },
      "stats": { "p_hard_all_sell": 0.97, "p_sold_out": 0.31 },
      "profit": { "expected": 1610000, "cvar": 1110000 },
      "baseline": { "hard": 900, "expected": 880000, "cvar": -810000 },
      "reasons": ["Demand is forecast at 546 to 951 room-nights, most likely 680.", "..."],
      "alerts": [{ "kind": "release", "date": "2026-12-07", "title": "Release check for Goa · New Year week on 07 Dec" }]
    }
  ],
  "alerts": []
}
```

Actions: `prebuy_allot`, `prebuy`, `allot_only`, `over_budget` (worth buying, but outranked at this
budget), `watch` (not worth the risk at this profile), `add_supplier`, `renegotiate`.

## Decisions

```http
POST /api/decisions
Content-Type: application/json

{ "option_id": "goa", "action": "edit", "hard": 450, "allot": 280, "budget": 20000000, "risk": "balanced" }
```

* `approve` and `edit` need `hard` and `allot`, within the supplier's supply and allotment caps (`422` otherwise).
* `reject` locks the option at zero.
* `undo` releases the option back to the optimiser.
* Unknown options return `404`.

Every later `POST /api/plan` keeps locked options as decided and re-optimises the rest with the budget
that is left.
