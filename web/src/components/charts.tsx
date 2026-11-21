import { useId } from "react";
import type { Forecast, Hist } from "../api";
import { money, n0 } from "../format";

/** The P10 to P90 band on a shared scale, with the plan's hard and allotment units laid under it. */
export function RangeBar({ f, max, hard, allot }: { f: Forecast; max: number; hard: number; allot: number }) {
  const x = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <div className="range" aria-hidden="true">
      <div className="range__band" style={{ left: x(f.p10), width: `calc(${x(f.p90)} - ${x(f.p10)})` }} />
      <div className="range__mid" style={{ left: x(f.p50) }} />
      {hard > 0 && <div className="range__hard" style={{ width: x(hard) }} />}
      {allot > 0 && <div className="range__allot" style={{ left: x(hard), width: `calc(${x(hard + allot)} - ${x(hard)})` }} />}
    </div>
  );
}

const W = 560;

function scaleX(edges: number[]) {
  const lo = edges[0], hi = edges[edges.length - 1];
  return (v: number) => ((v - lo) / (hi - lo || 1)) * W;
}

/** Demand across 10,000 futures, with the forecast quantiles and the plan's cover. */
export function DemandChart({ hist, f, hard, allot, unit }: { hist: Hist; f: Forecast; hard: number; allot: number; unit: string }) {
  const H = 120, pad = 22;
  const counts = hist.counts[0];
  const top = Math.max(...counts, 1);
  const x = scaleX(hist.edges);
  const bw = W / counts.length;
  const clip = useId();
  const marks: [string, number][] = [["P10", f.p10], ["P50", f.p50], ["P90", f.p90]];
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H + pad}`} role="img"
      aria-label={`Demand forecast: ${n0(f.p10)} to ${n0(f.p90)} ${unit}, most likely ${n0(f.p50)}`}>
      <defs><clipPath id={clip}><rect x="0" y="0" width={W} height={H} /></clipPath></defs>
      {hard + allot > 0 && (
        <g clipPath={`url(#${clip})`}>
          <rect className="c-hard" x={0} y={0} width={Math.max(0, x(hard))} height={H} />
          <rect className="c-allot" x={x(hard)} y={0} width={Math.max(0, x(hard + allot) - x(hard))} height={H} />
        </g>
      )}
      {counts.map((c, i) => (
        <rect key={i} className="c-bar" x={i * bw + 1} y={H - (c / top) * (H - 8)} width={bw - 2} height={(c / top) * (H - 8)} />
      ))}
      {marks.map(([k, v]) => (
        <g key={k}>
          <line className="c-mark" x1={x(v)} x2={x(v)} y1={0} y2={H} />
          <text className="c-label" x={x(v)} y={k === "P50" ? 11 : H + 15} dx={k === "P50" ? 5 : 0}
            textAnchor={k === "P50" ? "start" : "middle"}>{k} {n0(v)}</text>
        </g>
      ))}
      <line className="c-axis" x1={0} x2={W} y1={H} y2={H} />
    </svg>
  );
}

/** Profit across the same futures: the plan (filled) against a baseline (outline). */
export function ProfitChart({ hist, names }: { hist: Hist; names: [string, string] }) {
  const H = 130, pad = 24;
  const [a, b] = hist.counts;
  const top = Math.max(...a, ...b, 1);
  const x = scaleX(hist.edges);
  const bw = W / a.length;
  const zero = hist.edges[0] < 0 && hist.edges[hist.edges.length - 1] > 0 ? x(0) : null;
  const y = (c: number) => H - (c / top) * (H - 10);
  const outline = b.map((c, i) => `${i === 0 ? "M" : "L"}${i * bw},${y(c)} L${(i + 1) * bw},${y(c)}`).join(" ");
  const ticks = [hist.edges[0], (hist.edges[0] + hist.edges[hist.edges.length - 1]) / 2, hist.edges[hist.edges.length - 1]];
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H + pad}`} role="img" aria-label={`Profit across futures: ${names[0]} against ${names[1]}`}>
      {a.map((c, i) => (
        <rect key={i} className="c-plan" x={i * bw + 1} y={y(c)} width={bw - 2} height={H - y(c)} />
      ))}
      <path className="c-base" d={outline} />
      {zero !== null && <line className="c-zero" x1={zero} x2={zero} y1={0} y2={H} />}
      <line className="c-axis" x1={0} x2={W} y1={H} y2={H} />
      {ticks.map((t, i) => (
        <text key={i} className="c-label" x={i === 0 ? 2 : i === 2 ? W - 2 : W / 2} y={H + 16}
          textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>{money(t)}</text>
      ))}
    </svg>
  );
}

export function Legend({ items }: { items: { label: string; kind: string }[] }) {
  return (
    <div className="legend">
      {items.map(it => <span key={it.label}><i className={`key key--${it.kind}`} />{it.label}</span>)}
    </div>
  );
}

/** Horizontal bars for a short list of values. */
export function Bars({ rows, format, max }: { rows: { label: string; value: number; ref?: number }[]; format: (v: number) => string; max?: number }) {
  const top = max ?? Math.max(...rows.map(r => Math.max(r.value, r.ref ?? 0)), 1e-9);
  return (
    <div className="bars">
      {rows.map(r => (
        <div className="bars__row" key={r.label}>
          <span className="bars__label">{r.label}</span>
          <span className="bars__track">
            {r.ref !== undefined && <span className="bars__ref" style={{ width: `${(r.ref / top) * 100}%` }} />}
            <span className="bars__fill" style={{ width: `${(r.value / top) * 100}%` }} />
          </span>
          <span className="bars__value">{format(r.value)}</span>
        </div>
      ))}
    </div>
  );
}

export function Heatmap({ ids, names, matrix }: { ids: string[]; names: Record<string, string>; matrix: number[][] }) {
  const n = ids.length, cell = 30, left = 120, topPad = 120;
  const colour = (v: number) => {
    const a = Math.min(1, Math.abs(v) / 0.4);
    return v >= 0 ? `rgba(196,165,140,${0.08 + 0.85 * a})` : `rgba(120,160,200,${0.08 + 0.85 * a})`;
  };
  return (
    <svg className="chart heat" viewBox={`0 0 ${left + n * cell + 4} ${topPad + n * cell + 4}`} role="img"
      aria-label="Correlation of forecast errors between options">
      {ids.map((id, i) => (
        <g key={id}>
          <text className="c-label" x={left - 8} y={topPad + i * cell + cell / 2 + 4} textAnchor="end">{names[id]}</text>
          <text className="c-label" transform={`translate(${left + i * cell + cell / 2 + 4},${topPad - 8}) rotate(-60)`}>{names[id]}</text>
          {ids.map((_, j) => (
            <g key={j}>
              <rect x={left + j * cell} y={topPad + i * cell} width={cell - 2} height={cell - 2} rx={3} fill={i === j ? "rgba(255,255,255,0.08)" : colour(matrix[i][j])} />
              {i !== j && Math.abs(matrix[i][j]) >= 0.1 && (
                <text className="c-cell" x={left + j * cell + cell / 2 - 1} y={topPad + i * cell + cell / 2 + 3} textAnchor="middle">
                  {matrix[i][j].toFixed(2).replace("0.", ".")}
                </text>
              )}
            </g>
          ))}
        </g>
      ))}
    </svg>
  );
}
