import { useEffect, useMemo, useState } from "react";
import type { Decision, OptionInfo, Plan, PlanRow, Risk } from "../api";
import { inr, money, n0, pct, logPct } from "../format";
import { DemandChart, Legend, ProfitChart, RangeBar } from "./charts";

const RISKS: { id: Risk; label: string; hint: string }[] = [
  { id: "cautious", label: "Cautious", hint: "60% weight on the worst 5% of futures" },
  { id: "balanced", label: "Balanced", hint: "30% weight on the worst 5% of futures" },
  { id: "bold", label: "Bold", hint: "10% weight on the worst 5% of futures" },
];

export function Controls(props: {
  budget: number; setBudget: (v: number) => void; risk: Risk; setRisk: (r: Risk) => void;
  busy: boolean; onExact: () => void; plan: Plan | null;
}) {
  const { budget, setBudget, risk, setRisk, busy, onExact, plan } = props;
  const [draft, setDraft] = useState(budget);
  useEffect(() => setDraft(budget), [budget]);
  return (
    <div className="controls">
      <label className="budget">
        <span className="eyebrow">Budget</span>
        <input type="range" min={2_500_000} max={50_000_000} step={500_000} value={draft}
          onChange={e => setDraft(Number(e.target.value))}
          onPointerUp={() => setBudget(draft)} onKeyUp={() => setBudget(draft)} onBlur={() => setBudget(draft)}
          aria-label="Budget for pre-buys" />
        <output className="mono">{money(draft, false)}</output>
      </label>
      <div className="seg" role="radiogroup" aria-label="Risk profile">
        {RISKS.map(r => (
          <button key={r.id} type="button" role="radio" aria-checked={risk === r.id} title={r.hint}
            className={risk === r.id ? "on" : ""} onClick={() => setRisk(r.id)}>{r.label}</button>
        ))}
      </div>
      <div className="solver">
        <span className={`dot ${busy ? "dot--busy" : ""}`} />
        <span>{busy ? "Optimising…" : plan ? `${plan.solver.method} · ${plan.solver.seconds.toFixed(2)} s · ${plan.solver.candidates} candidate plans` : "Loading"}</span>
        {plan && plan.solver.exact_status !== "not run" && <span className="tag">SCIP: {plan.solver.exact_status}</span>}
        <button type="button" className="btn btn--ghost" disabled={busy} onClick={onExact}>Verify with exact solver</button>
      </div>
    </div>
  );
}

export function Kpis({ plan }: { plan: Plan }) {
  const s = plan.summary, b = plan.baseline;
  const items = [
    { k: "Cash committed", v: money(s.cash, false), sub: `of ${money(plan.budget, false)} · ${n0(s.hard_units)} hard, ${n0(s.allot_units)} allotment` },
    { k: "Expected profit", v: money(s.expected), sub: `${money(b.expected)} if you buy the P90 upfront`, good: true },
    { k: "Average of worst 5%", v: money(s.cvar), sub: `${money(b.cvar)} if you buy the P90 upfront`, good: s.cvar >= 0 },
    { k: "Hard units that sell", v: pct(s.hard_sell_through, 1), sub: `chance of a loss ${pct(s.p_loss, 1)} vs ${pct(b.p_loss, 1)}` },
  ];
  return (
    <div className="kpis">
      {items.map(it => (
        <div className="kpi" key={it.k}>
          <span className="eyebrow">{it.k}</span>
          <strong className={`mono ${it.good ? "pos" : ""}`}>{it.v}</strong>
          <span className="sub">{it.sub}</span>
        </div>
      ))}
    </div>
  );
}

function Thumb({ o }: { o: OptionInfo }) {
  return o.image
    ? <img className="thumb" src={`/img/${o.image}`} alt="" loading="lazy" />
    : <span className="thumb thumb--icon" aria-hidden="true">{o.kind === "flight" ? "✈" : "⌂"}</span>;
}

export function OptionList({ plan, options, selected, onSelect, decisions }: {
  plan: Plan; options: Record<string, OptionInfo>; selected: string; onSelect: (id: string) => void;
  decisions: Record<string, Decision>;
}) {
  const max = useMemo(() => Math.max(...plan.rows.map(r => Math.max(r.forecast.p90, r.plan.hard + r.plan.allot))) * 1.05, [plan]);
  return (
    <ol className="list" aria-label="Options ranked by the plan">
      {plan.rows.map(r => {
        const o = options[r.id];
        const d = decisions[r.id];
        return (
          <li key={r.id}>
            <button type="button" className={`row ${selected === r.id ? "row--on" : ""}`} onClick={() => onSelect(r.id)}
              aria-current={selected === r.id}>
              <span className="row__rank mono">{r.rank}</span>
              <Thumb o={o} />
              <span className="row__name">
                <strong>{o.name}</strong>
                <span>{o.dates} · {o.product}</span>
              </span>
              <span className="row__range">
                <RangeBar f={r.forecast} max={max} hard={r.plan.hard} allot={r.plan.allot} />
                <span className="mono">{n0(r.forecast.p10)}–{n0(r.forecast.p90)}</span>
              </span>
              <span className="row__plan mono">{r.plan.hard || r.plan.allot ? `${n0(r.plan.hard)} + ${n0(r.plan.allot)}` : "–"}</span>
              <span className={`pill pill--${d ? d.action : r.action}`}>{d ? decisionLabel(d) : r.label}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function decisionLabel(d: Decision) {
  return d.action === "approve" ? "Approved" : d.action === "edit" ? "Edited" : d.action === "reject" ? "Rejected" : "";
}

export function OptionDetail({ row, o, decision, onDecide, busy }: {
  row: PlanRow; o: OptionInfo; decision?: Decision; busy: boolean;
  onDecide: (action: Decision["action"], hard?: number, allot?: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [hard, setHard] = useState(row.plan.hard);
  const [allot, setAllot] = useState(row.plan.allot);
  useEffect(() => { setEditing(false); setHard(row.plan.hard); setAllot(row.plan.allot); }, [row.id, row.plan.hard, row.plan.allot]);
  const e = o.economics, s = row.signals;
  const canBuy = row.action !== "add_supplier" && row.action !== "renegotiate";
  const chips = [
    `Searches ${logPct(s.search_yoy)} vs last year`,
    `On the books ${n0(s.on_books)} (${logPct(s.pace_yoy)})`,
    s.soldout_nights_ly ? `${s.soldout_nights_ly} sold-out night${s.soldout_nights_ly > 1 ? "s" : ""} last year` : null,
    `Supplier rate ${logPct(s.rate_change)}`,
    `${s.lead_days} days to arrival`,
  ].filter(Boolean) as string[];

  return (
    <section className="detail" aria-labelledby="detail-title">
      <header className="detail__head">
        <div>
          <span className="eyebrow">#{row.rank} · {o.region === "india" ? "India" : "Overseas"} · {o.kind === "flight" ? "Seats" : "Hotels"}</span>
          <h2 id="detail-title">{o.name}</h2>
          <p className="muted">{o.dates} · {o.product}</p>
        </div>
        <span className={`pill pill--${decision ? decision.action : row.action}`}>{decision ? decisionLabel(decision) : row.label}</span>
      </header>
      <ul className="chips">{chips.map(c => <li key={c}>{c}</li>)}</ul>

      <div className="detail__grid">
        <figure>
          <figcaption>Demand across 10,000 futures, {o.unit}</figcaption>
          <DemandChart hist={row.demand_hist} f={row.forecast} hard={row.plan.hard} allot={row.plan.allot} unit={o.unit} />
          <Legend items={[{ label: "Futures", kind: "bar" }, { label: `Hard ${n0(row.plan.hard)}`, kind: "hard" }, { label: `Allotment ${n0(row.plan.allot)}`, kind: "allot" }]} />
        </figure>
        <figure>
          <figcaption>Profit on this option across the same futures</figcaption>
          <ProfitChart hist={row.profit_hist} names={["InventIQ plan", "P90 upfront"]} />
          <Legend items={[{ label: "InventIQ plan", kind: "plan" }, { label: `Buy P90 upfront (${n0(row.baseline.hard)} hard)`, kind: "base" }]} />
        </figure>
      </div>

      <table className="compare">
        <thead><tr><th /><th>InventIQ plan</th><th>Buy P90 upfront</th></tr></thead>
        <tbody>
          <tr><th>Units</th><td className="mono">{n0(row.plan.hard)} hard + {n0(row.plan.allot)} allot</td><td className="mono">{n0(row.baseline.hard)} hard</td></tr>
          <tr><th>Expected profit</th><td className="mono pos">{money(row.profit.expected)}</td><td className="mono">{money(row.baseline.expected)}</td></tr>
          <tr><th>Average of worst 5%</th><td className={`mono ${row.profit.cvar >= 0 ? "pos" : "neg"}`}>{money(row.profit.cvar)}</td>
            <td className={`mono ${row.baseline.cvar >= 0 ? "" : "neg"}`}>{money(row.baseline.cvar)}</td></tr>
          <tr><th>Cash upfront</th><td className="mono">{money(row.plan.cash, false)}</td><td className="mono">{money(row.baseline.hard * e.hard_cost, false)}</td></tr>
        </tbody>
      </table>

      <ul className="reasons">{row.reasons.map(r => <li key={r}>{r}</li>)}</ul>

      <dl className="econ">
        <div><dt>Hard rate</dt><dd className="mono">{inr(e.hard_cost)}</dd></div>
        <div><dt>Allotment rate</dt><dd className="mono">{e.allot_cost ? inr(e.allot_cost) : "not offered"}</dd></div>
        <div><dt>Sell price</dt><dd className="mono">{inr(e.sell_price)}</dd></div>
        <div><dt>Break-even sure-to-sell</dt><dd className="mono">{pct(e.breakeven_sure)}</dd></div>
      </dl>

      {editing ? (
        <form className="actions" onSubmit={ev => { ev.preventDefault(); onDecide("edit", hard, allot); setEditing(false); }}>
          <label>Hard <input type="number" min={0} max={e.supply_cap} value={hard} onChange={ev => setHard(Number(ev.target.value))} /></label>
          <label>Allotment <input type="number" min={0} max={e.allot_cap} value={allot} onChange={ev => setAllot(Number(ev.target.value))} /></label>
          <button className="btn btn--primary" disabled={busy}>Save and re-plan</button>
          <button type="button" className="btn btn--ghost" onClick={() => setEditing(false)}>Cancel</button>
        </form>
      ) : (
        <div className="actions">
          {decision ? (
            <>
              <span className="muted">{decisionLabel(decision)} {new Date(decision.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}. The rest of the plan is re-optimised around it.</span>
              <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => onDecide("undo")}>Undo</button>
            </>
          ) : (
            <>
              <button type="button" className="btn btn--primary" disabled={busy || !canBuy || (!row.plan.hard && !row.plan.allot)}
                onClick={() => onDecide("approve", row.plan.hard, row.plan.allot)}>Approve</button>
              <button type="button" className="btn" disabled={busy || !canBuy} onClick={() => setEditing(true)}>Edit</button>
              <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => onDecide("reject")}>Reject</button>
            </>
          )}
        </div>
      )}
    </section>
  );
}

export function PortfolioPanel({ plan }: { plan: Plan }) {
  return (
    <section className="panel portfolio">
      <div>
        <span className="eyebrow">Whole plan</span>
        <h2>Profit across 10,000 joint futures</h2>
        <p className="muted">Markets that share travellers move together in these futures, so a bad week hits related buys at once. InventIQ's spread stays tight because allotment, not cash, covers the upside.</p>
        <table className="compare compare--tight">
          <thead><tr><th /><th>Expected</th><th>Worst 5%</th><th>Loss chance</th></tr></thead>
          <tbody>
            <tr><th>InventIQ plan</th><td className="mono pos">{money(plan.summary.expected)}</td><td className="mono pos">{money(plan.summary.cvar)}</td><td className="mono">{pct(plan.summary.p_loss, 1)}</td></tr>
            <tr><th>{plan.baseline.name}</th><td className="mono">{money(plan.baseline.expected)}</td><td className={`mono ${plan.baseline.cvar < 0 ? "neg" : ""}`}>{money(plan.baseline.cvar)}</td><td className="mono">{pct(plan.baseline.p_loss, 1)}</td></tr>
          </tbody>
        </table>
      </div>
      <figure>
        <ProfitChart hist={plan.histogram} names={["InventIQ plan", "P90 upfront"]} />
        <Legend items={[{ label: "InventIQ plan", kind: "plan" }, { label: "Buy P90 upfront", kind: "base" }]} />
      </figure>
    </section>
  );
}
