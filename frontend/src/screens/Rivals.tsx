import { useState } from "react";
import { type RivalResult, api, inr, pct } from "../api";
import { useLive } from "../hooks";

const REGIMES: Record<string, string> = {
  history: "Like the last 13 solar auctions",
  almm_40: "Rivals pass on 40% of the imported-panel saving",
  almm_100: "Rivals pass on all of it",
};

export function Rivals() {
  const run = useLive(() => api.latestRun("rival"), 15000);
  const [regime, setRegime] = useState("almm_40");
  const result = (run.data?.result ?? null) as RivalResult | null;
  if (run.error) return <p className="alert">{run.error}</p>;
  if (!result) return <p className="note">No rival run yet. Start one from the Setup screen.</p>;
  const snap = result.snapshots[regime];
  return (
    <>
      <p className="levers">
        {Object.keys(result.snapshots).map((r) => (
          <button key={r} className={r === regime ? "" : "ghost"} onClick={() => setRegime(r)}>{r}</button>
        ))}
        <span className="note">{REGIMES[regime]}. Shift {inr(result.shift_inr_per_kwh)} per kWh at full pass-through (A-16). Switching never edits a snapshot.</span>
      </p>
      <p className="note">Snapshot {snap.id} · seed {snap.seed} · {snap.n_draws.toLocaleString()} draws · sha256 {snap.sha256.slice(0, 12)}</p>
      <section className="rivals">
        {snap.profiles.map((p) => (
          <article key={p.name} className="rival">
            <h3>{p.name} <span className="tag">{p.archetype.replace("_", " ")}</span></h3>
            <p className="card-value small">{pct(p.p_participate)} <span className="note">chance of bidding</span></p>
            <p>Floor {inr(p.floor_p10)} / <b>{inr(p.floor_p50)}</b> / {inr(p.floor_p90)} <span className="note">(p10 / p50 / p90)</span></p>
            <p className="note">Capacity: {p.capacity_mw.map(([mw, pr]) => `${mw} MW (${pct(pr)})`).join(", ")}</p>
            <ul className="why">{p.why.map((w) => <li key={w}>{w}</li>)}</ul>
            <p className="note">{p.sources.join("; ")}</p>
          </article>
        ))}
      </section>
    </>
  );
}
