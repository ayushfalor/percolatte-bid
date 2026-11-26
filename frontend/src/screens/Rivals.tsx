import { useState } from "react";
import { type RivalResult, api, inr, pct } from "../api";
import { useLive } from "../hooks";

const REGIMES: Record<string, string> = {
  history: "Rivals bid like they did in the last 13 solar auctions",
  almm_40: "Rivals pass 40% of the cheaper-panel saving into their bids",
  almm_100: "Rivals pass all of the cheaper-panel saving into their bids",
};
const REGIME_NAME: Record<string, string> = { history: "Like past auctions", almm_40: "Cheaper panels, 40% passed on", almm_100: "Cheaper panels, all passed on" };

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
          <button key={r} className={r === regime ? "" : "ghost"} onClick={() => setRegime(r)} title={REGIMES[r]}>{REGIME_NAME[r] ?? r}</button>
        ))}
        <span className="note">{REGIMES[regime]}. Cheaper panels are worth {inr(result.shift_inr_per_kwh)} per kWh at most (A-16). Each view is a frozen set of beliefs; switching never edits one.</span>
      </p>
      <p className="note">{snap.n_draws.toLocaleString()} simulated auctions · snapshot {snap.id} · fingerprint {snap.sha256.slice(0, 12)}</p>
      <section className="rivals">
        {snap.profiles.map((p) => (
          <article key={p.name} className="rival">
            <h3>{p.name} <span className="tag">{p.archetype.replace("_", " ")}</span></h3>
            <p className="card-value small">{pct(p.p_participate)} <span className="note">chance of bidding</span></p>
            <p>Stops cutting at {inr(p.floor_p10)} / <b>{inr(p.floor_p50)}</b> / {inr(p.floor_p90)} <span className="note">(1 in 10 lower / typical / 1 in 10 higher)</span></p>
            <p className="note">Capacity: {p.capacity_mw.map(([mw, pr]) => `${mw} MW (${pct(pr)})`).join(", ")}</p>
            <ul className="why">{p.why.map((w) => <li key={w}>{w}</li>)}</ul>
            <p className="note">{p.sources.join("; ")}</p>
          </article>
        ))}
      </section>
    </>
  );
}
