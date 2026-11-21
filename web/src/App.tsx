import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Backtest, type Correlation, type Decision, type Decisions, type Meta, type OptionInfo, type Plan, type Risk } from "./api";
import { Controls, Kpis, OptionDetail, OptionList, PortfolioPanel } from "./components/PlanView";
import { AccuracyView, AlertsView, LogView } from "./components/OtherViews";

type Tab = "plan" | "alerts" | "accuracy" | "log";
const TABS: { id: Tab; label: string }[] = [
  { id: "plan", label: "Plan" }, { id: "alerts", label: "Alerts" },
  { id: "accuracy", label: "Forecast accuracy" }, { id: "log", label: "Decision log" },
];

function readHash(): Tab {
  const h = location.hash.replace("#", "") as Tab;
  return TABS.some(t => t.id === h) ? h : "plan";
}

export default function App() {
  const [tab, setTab] = useState<Tab>(readHash);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [options, setOptions] = useState<Record<string, OptionInfo>>({});
  const [plan, setPlan] = useState<Plan | null>(null);
  const [bt, setBt] = useState<Backtest | null>(null);
  const [corr, setCorr] = useState<Correlation | null>(null);
  const [decisions, setDecisions] = useState<Decisions>({ current: {}, log: [] });
  const [budget, setBudget] = useState(20_000_000);
  const [risk, setRisk] = useState<Risk>("balanced");
  const [selected, setSelected] = useState("goa");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const on = () => setTab(readHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    Promise.all([api.meta(), api.options(), api.backtest(), api.correlation(), api.decisions()])
      .then(([m, o, b, c, d]) => {
        setMeta(m); setOptions(Object.fromEntries(o.map(x => [x.id, x]))); setBt(b); setCorr(c); setDecisions(d);
        setBudget(m.default_budget);
      })
      .catch(e => setError(String(e.message ?? e)));
  }, []);

  const replan = useCallback(async (exact = false) => {
    setBusy(true);
    try {
      setPlan(await api.plan(budget, risk, exact));
      setError(null);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }, [budget, risk]);

  useEffect(() => { if (meta) replan(); }, [meta, replan]);

  const decide = async (action: Decision["action"], hard?: number, allot?: number) => {
    setBusy(true);
    try {
      await api.decide({ option_id: selected, action, hard, allot, budget, risk });
      setDecisions(await api.decisions());
      await replan();
    } catch (e) {
      setError(String((e as Error).message));
      setBusy(false);
    }
  };

  const reset = async () => {
    await api.resetDecisions();
    setDecisions(await api.decisions());
    await replan();
  };

  const row = useMemo(() => plan?.rows.find(r => r.id === selected), [plan, selected]);
  const go = (t: Tab) => { location.hash = t; setTab(t); };
  const open = (id: string) => { setSelected(id); go("plan"); };

  return (
    <div className="app">
      <header className="top">
        <a className="brand" href="#plan" onClick={() => go("plan")}>
          <svg viewBox="0 0 64 64" aria-hidden="true"><path d="M20 46V18M32 46V28M44 46V22" /></svg>
          InventIQ
        </a>
        <nav aria-label="Sections">
          {TABS.map(t => (
            <a key={t.id} href={`#${t.id}`} className={tab === t.id ? "on" : ""} aria-current={tab === t.id ? "page" : undefined}>
              {t.label}{t.id === "alerts" && plan ? <span className="count">{plan.alerts.length}</span> : null}
            </a>
          ))}
        </nav>
        <div className="top__meta">
          {meta && <span>{meta.season} · planning date {new Date(meta.today).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</span>}
          <a href="/docs" target="_blank" rel="noreferrer">API</a>
        </div>
      </header>

      {error && <div className="error" role="alert">Could not reach the planning API: {error}. Start it with <code>python -m inventiq serve</code>.</div>}

      {tab === "plan" && (
        <main className="planview">
          <Controls budget={budget} setBudget={setBudget} risk={risk} setRisk={setRisk} busy={busy} onExact={() => replan(true)} plan={plan} />
          {plan && <Kpis plan={plan} />}
          {plan && row && options[selected] ? (
            <div className={`desk ${busy ? "desk--busy" : ""}`}>
              <OptionList plan={plan} options={options} selected={selected} onSelect={setSelected} decisions={decisions.current} />
              <OptionDetail row={row} o={options[selected]} decision={decisions.current[selected]} onDecide={decide} busy={busy} />
            </div>
          ) : <div className="loading">Training the forecast and drawing 10,000 futures…</div>}
          {plan && <PortfolioPanel plan={plan} />}
        </main>
      )}
      {tab === "alerts" && plan && <AlertsView alerts={plan.alerts} options={options} onOpen={open} />}
      {tab === "accuracy" && bt && corr && <AccuracyView bt={bt} corr={corr} options={options} />}
      {tab === "log" && <LogView log={decisions.log} options={options} onReset={reset} />}

      <footer className="foot">
        <span>InventIQ {meta?.version} · synthetic data shaped like a B2B travel distributor's feeds</span>
        <span>Photographs via Wikimedia Commons, see CREDITS.md</span>
      </footer>
    </div>
  );
}
