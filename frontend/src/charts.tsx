import { useState } from "react";
import { type Driver, type LadderPoint, inr, pct } from "./api";

// Plain SVG, no chart library: the numbers on screen are the API's, pixel positions are the only arithmetic here.

const W = 880;
const H = 320;
const PAD = { l: 52, r: 52, t: 16, b: 36 };

function scale(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  return (v: number) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
}

export function Ladder({
  ladder,
  ghost,
  walkAway,
  entry,
  target,
  hurdle,
  onHover,
}: {
  ladder: LadderPoint[];
  ghost?: LadderPoint[] | null;
  walkAway?: number | null;
  entry?: number | null;
  target?: [number, number] | null;
  hurdle: number;
  onHover?: (p: LadderPoint | null) => void;
}) {
  const [hover, setHover] = useState<LadderPoint | null>(null);
  if (!ladder.length) return <p className="note">No ladder yet.</p>;
  const tariffs = ladder.map((p) => p.tariff);
  const x = scale([Math.min(...tariffs), Math.max(...tariffs)], [PAD.l, W - PAD.r]);
  const yOdds = scale([0, 1], [H - PAD.b, PAD.t]);
  const irrs = [...ladder, ...(ghost ?? [])].map((p) => p.equity_irr ?? 0);
  const yIrr = scale([Math.min(0, ...irrs), Math.max(0.2, ...irrs)], [H - PAD.b, PAD.t]);
  const path = (pts: LadderPoint[], y: (v: number) => number, key: (p: LadderPoint) => number | null) =>
    pts
      .filter((p) => key(p) != null)
      .map((p, i) => `${i ? "L" : "M"}${x(p.tariff).toFixed(1)},${y(key(p) as number).toFixed(1)}`)
      .join(" ");
  const barW = Math.max(2, (W - PAD.l - PAD.r) / ladder.length - 1);
  const pick = (clientX: number, el: SVGSVGElement) => {
    const rect = el.getBoundingClientRect();
    const px = ((clientX - rect.left) / rect.width) * W;
    const nearest = ladder.reduce((a, b) => (Math.abs(x(b.tariff) - px) < Math.abs(x(a.tariff) - px) ? b : a));
    setHover(nearest);
    onHover?.(nearest);
  };
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="chart"
      role="img"
      aria-label="Price ladder: win chance and equity IRR at every tariff"
      onMouseMove={(e) => pick(e.clientX, e.currentTarget)}
      onMouseLeave={() => (setHover(null), onHover?.(null))}
    >
      {target && <rect x={x(target[0])} y={PAD.t} width={Math.max(1, x(target[1]) - x(target[0]))} height={H - PAD.t - PAD.b} className="zone-target" />}
      {ladder.map((p) => (
        <rect key={p.tariff} x={x(p.tariff) - barW / 2} y={yOdds(p.expected_mw / 200)} width={barW} height={H - PAD.b - yOdds(p.expected_mw / 200)} className="bar-mw" />
      ))}
      <line x1={PAD.l} x2={W - PAD.r} y1={yIrr(hurdle)} y2={yIrr(hurdle)} className="line-hurdle" />
      <text x={W - PAD.r + 4} y={yIrr(hurdle) + 4} className="axis-label">hurdle {pct(hurdle)}</text>
      {walkAway != null && (
        <>
          <line x1={x(walkAway)} x2={x(walkAway)} y1={PAD.t} y2={H - PAD.b} className="line-walk" />
          <text x={x(walkAway) + 4} y={PAD.t + 12} className="axis-label">walk-away {inr(walkAway)}</text>
        </>
      )}
      {entry != null && <line x1={x(entry)} x2={x(entry)} y1={PAD.t} y2={H - PAD.b} className="line-entry" />}
      {ghost && <path d={path(ghost, yIrr, (p) => p.equity_irr)} className="line-irr ghost" />}
      <path d={path(ladder, yIrr, (p) => p.equity_irr)} className="line-irr" />
      <path d={path(ladder, yOdds, (p) => p.p_win_any)} className="line-odds" />
      {hover && (
        <>
          <line x1={x(hover.tariff)} x2={x(hover.tariff)} y1={PAD.t} y2={H - PAD.b} className="line-cross" />
          <circle cx={x(hover.tariff)} cy={yOdds(hover.p_win_any)} r={5} className="dot-odds" />
        </>
      )}
      {[0, 0.25, 0.5, 0.75, 1].map((v) => (
        <text key={v} x={PAD.l - 6} y={yOdds(v) + 4} className="axis-label right">{pct(v)}</text>
      ))}
      {ladder.filter((_, i) => i % 10 === 0).map((p) => (
        <text key={p.tariff} x={x(p.tariff)} y={H - PAD.b + 18} className="axis-label middle">{p.tariff.toFixed(2)}</text>
      ))}
      <text x={PAD.l} y={H - 4} className="axis-label">win chance (left), equity IRR (right), bars: expected MW of 200</text>
    </svg>
  );
}

export function Tornado({ drivers, base }: { drivers: Driver[]; base: number | null }) {
  if (!drivers.length) return <p className="note">No drivers yet.</p>;
  const lo = Math.min(...drivers.map((d) => d.low));
  const hi = Math.max(...drivers.map((d) => d.high));
  const x = scale([lo, hi], [200, W - 24]);
  const rowH = 30;
  const height = drivers.length * rowH + 40;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img" aria-label="Tornado: which inputs move the breakeven most">
      {base != null && <line x1={x(base)} x2={x(base)} y1={8} y2={height - 28} className="line-walk" />}
      {drivers.map((d, i) => (
        <g key={d.cell} transform={`translate(0 ${16 + i * rowH})`}>
          <text x={192} y={14} className="axis-label right">{d.label}</text>
          <rect x={x(d.low)} y={2} width={Math.max(1, x(d.high) - x(d.low))} height={18} className={d.exact ? "bar-swing exact" : "bar-swing"} />
          <text x={x(d.high) + 6} y={16} className="axis-label">{inr(d.low)} to {inr(d.high)}</text>
        </g>
      ))}
      <text x={200} y={height - 8} className="axis-label">breakeven tariff with each input moved 10% either way; solid bars are exact goal seeks</text>
    </svg>
  );
}
