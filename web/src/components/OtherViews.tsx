import type { Alert, Backtest, Correlation, Decision, OptionInfo } from "../api";
import { n0, pct, shortDate } from "../format";
import { Bars, Heatmap } from "./charts";

const FEATURE: Record<string, string> = {
  pace_yoy: "Bookings vs last year", log_ly_demand: "Last year's demand", log_searches: "Searches",
  search_yoy: "Searches vs last year", rate_change: "Supplier rate change", event_strength: "Event calendar",
  month_cos: "Time of year", month_sin: "Time of year", option: "Market", log_on_books: "On the books",
  log_on_books_ly: "On the books last year", look_to_book: "Look-to-book", soldout_nights_ly: "Sold-out nights last year",
  lead_days: "Days to arrival", nights: "Length of stay", is_flight: "Flight or hotel", is_international: "Overseas",
};

const KIND: Record<Alert["kind"], string> = { reprice: "Re-price", supplier: "Supply gap", release: "Release date", buy_now: "Rates rising" };

export function AlertsView({ alerts, options, onOpen }: { alerts: Alert[]; options: Record<string, OptionInfo>; onOpen: (id: string) => void }) {
  return (
    <section className="page">
      <header className="page__head">
        <span className="eyebrow">Risk Shield</span>
        <h1>{alerts.length} things to act on this season</h1>
        <p className="muted">Re-pricing for blocks already held, supply gaps, rising supplier rates and the date each allotment must be handed back.</p>
      </header>
      <ul className="alerts">
        {alerts.map((a, i) => (
          <li key={i} className={`alert alert--${a.severity}`}>
            <span className="alert__kind">{KIND[a.kind]}</span>
            <div>
              <strong>{a.title}</strong>
              <p>{a.detail}</p>
            </div>
            <span className="alert__date mono">{shortDate(a.date)}</span>
            <button type="button" className="btn btn--ghost" onClick={() => onOpen(a.option_id)}>Open {options[a.option_id]?.name.split(" · ")[0]}</button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AccuracyView({ bt, corr, options }: { bt: Backtest; corr: Correlation; options: Record<string, OptionInfo> }) {
  const a = bt.all, pk = bt.peak_windows;
  const names = Object.fromEntries(Object.values(options).map(o => [o.id, o.name.split(" · ")[0]]));
  const cards = [
    { k: "Forecast error (WAPE)", v: pct(a.wape_p50, 1), sub: `${pct(a.wape_naive, 1)} for "same window last year"` },
    { k: "Error removed", v: pct(a.improvement), sub: "against the seasonal-naive forecast" },
    { k: "P10–P90 coverage", v: pct(a.coverage_p10_p90, 1), sub: `target 80% · ${pct(a.below_p10, 1)} below, ${pct(a.above_p90, 1)} above` },
    { k: "Peak windows", v: pct(pk.wape_p50, 1), sub: `vs ${pct(pk.wape_naive, 1)} naive · coverage ${pct(pk.coverage_p10_p90)}` },
  ];
  return (
    <section className="page">
      <header className="page__head">
        <span className="eyebrow">Demand Radar · back-test</span>
        <h1>Tested on a season the models never saw</h1>
        <p className="muted">Trained on stays before July 2024, calibrated on the next season, tested on {n0(a.rows)} forecasts for {bt.test_period}. Each forecast is made 28 to 84 days before arrival, with only the signals known on that day.</p>
      </header>
      <div className="kpis">
        {cards.map(c => (
          <div className="kpi" key={c.k}><span className="eyebrow">{c.k}</span><strong className="mono">{c.v}</strong><span className="sub">{c.sub}</span></div>
        ))}
      </div>
      <div className="grid2">
        <div className="panel">
          <h2>Error by lead time</h2>
          <p className="muted">Further out, less is on the books, so the range widens.</p>
          <Bars rows={Object.entries(bt.by_lead_wape).map(([k, v]) => ({ label: `${k} days`, value: v }))} format={v => pct(v, 1)} />
        </div>
        <div className="panel">
          <h2>What drives the forecast</h2>
          <p className="muted">Share of the median model's split gain.</p>
          <Bars rows={bt.importance.map(f => ({ label: FEATURE[f.feature] ?? f.feature, value: f.share }))} format={v => pct(v)} />
        </div>
        <div className="panel">
          <h2>By option</h2>
          <p className="muted">Bars: InventIQ error. Shadow: same window last year.</p>
          <Bars rows={Object.entries(bt.by_option).map(([id, v]) => ({ label: names[id], value: v.wape_p50, ref: v.wape_naive }))} format={v => pct(v, 1)} />
        </div>
        <div className="panel">
          <h2>Markets that move together</h2>
          <p className="muted">Correlation of forecast errors, used to draw joint futures. Bronze: move together.</p>
          <Heatmap ids={corr.ids} names={names} matrix={corr.matrix} />
        </div>
      </div>
    </section>
  );
}

const VERB: Record<Decision["action"], string> = { approve: "Approved", edit: "Edited", reject: "Rejected", undo: "Undid the decision on" };

export function LogView({ log, options, onReset }: { log: Decision[]; options: Record<string, OptionInfo>; onReset: () => void }) {
  return (
    <section className="page">
      <header className="page__head">
        <span className="eyebrow">Audit trail</span>
        <h1>Every decision, in order</h1>
        <p className="muted">Nothing is bought until a buyer approves. Decisions are appended, never overwritten.</p>
      </header>
      {log.length === 0 ? <p className="empty">No decisions yet. Approve, edit or reject an option on the plan.</p> : (
        <table className="log">
          <thead><tr><th>When</th><th>Decision</th><th>Option</th><th>Hard</th><th>Allotment</th><th>Context</th></tr></thead>
          <tbody>
            {log.map(d => (
              <tr key={d.id}>
                <td className="mono">{new Date(d.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</td>
                <td><span className={`pill pill--${d.action}`}>{VERB[d.action]}</span></td>
                <td>{options[d.option_id]?.name ?? d.option_id}</td>
                <td className="mono">{d.hard ?? "–"}</td>
                <td className="mono">{d.allot ?? "–"}</td>
                <td className="muted">{d.risk ? `${d.risk}, ` : ""}{d.budget ? `₹${(d.budget / 1e7).toFixed(2)} Cr` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {log.length > 0 && <button type="button" className="btn btn--ghost" onClick={onReset}>Clear all decisions</button>}
    </section>
  );
}
