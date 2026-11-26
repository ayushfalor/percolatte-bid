import { useEffect, useState } from "react";
import { type Doc, type Driver, type EngineResult, type LadderPoint, type Replay, type RivalResult, type Run, type Scenario, api, inr, pct } from "../api";
import { Ladder } from "../charts";
import { useLive } from "../hooks";

const LEVERS = [
  { label: "Interest +50 bp", message: "What if the interest rate rises by 50 basis points?" },
  { label: "CUF 30%", message: "What if CUF is 30%?" },
  { label: "Capex -5%", message: "What if capex falls by 5%?" },
  { label: "Modules at INR 10/Wp", message: "What if modules cost INR 10/Wp?" },
  { label: "O&M +10%", message: "What if O&M rises by 10%?" },
];
const POLL_MS = 2000;
const MAX_POLLS = 60;

type AuditorResult = { drivers?: Driver[] };

export function WarRoom({ workbook }: { workbook: Doc }) {
  const engineRun = useLive(() => api.latestRun("engine", workbook.id), 5000, [workbook.id]);
  const auditRun = useLive(() => api.latestRun("auditor", workbook.id), 15000, [workbook.id]);
  const rivalRun = useLive(() => api.latestRun("rival"), 15000);
  const scenarios = useLive(() => api.scenarios(), 5000);
  const [hover, setHover] = useState<LadderPoint | null>(null);
  const [ghostId, setGhostId] = useState<string | null>(null);
  const [ghost, setGhost] = useState<EngineResult | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [pick, setPick] = useState("");
  const [value, setValue] = useState("");

  const base = (engineRun.data?.result ?? null) as EngineResult | null;
  const baseRun = engineRun.data as Run | null;
  const rival = (rivalRun.data?.result ?? null) as RivalResult | null;
  const drivers = ((auditRun.data?.result ?? {}) as AuditorResult).drivers ?? [];
  const regime = base?.regime ?? "almm_40";
  const field = rival?.snapshots?.[regime]?.profiles ?? [];

  // The ghost is the scenario's own Engine run. It may still be queued, so keep looking for a while.
  useEffect(() => {
    if (!ghostId) return setGhost(null);
    let tries = 0;
    let alive = true;
    const look = () => {
      api.runs("kind=engine&limit=80").then((runs) => {
        if (!alive) return;
        const mine = runs.filter((x) => x.params?.scenario_id === ghostId);
        const done = mine.find((x) => x.status === "succeeded");
        if (done) return setGhost(done.result as EngineResult);
        if (mine.some((x) => x.status === "failed")) return setNote("The Engine could not price that scenario; see Setup for the error.");
        if (++tries < MAX_POLLS) setTimeout(look, POLL_MS);
      });
    };
    look();
    return () => {
      alive = false;
    };
  }, [ghostId]);

  const rec = base?.recommendation ?? null;
  const askWhatIf = (message: string) => {
    setNote("Saving the scenario and rerunning the Engine.");
    api
      .chat(message, workbook.id)
      .then((r) => {
        setNote(r.answer);
        if (r.scenario_id) setGhostId(r.scenario_id);
        scenarios.refresh();
      })
      .catch((e: Error) => setNote(e.message));
  };
  const priceIt = async () => {
    const d = drivers.find((x) => x.cell === pick);
    const v = parseFloat(value);
    if (!d || !Number.isFinite(v)) return setNote("Pick an input and type a number.");
    setNote(`Pricing ${d.label} at ${v} on a copy of the model. The sheet itself is never changed.`);
    try {
      const sc = await api.createScenario(`${d.label}: ${d.value} to ${v}`, workbook.id, { [d.cell]: v });
      await api.runScenario(sc.id);
      setGhostId(sc.id);
      scenarios.refresh();
    } catch (e) {
      setNote((e as Error).message);
    }
  };
  const playReplay = () => {
    setReplayError(null);
    api.replay(workbook.id, 0, rec?.entry_bid ?? 2.45, rec?.walk_away ?? 2.28, regime).then(setReplay).catch((e: Error) => setReplayError(e.message));
  };

  if (!base) return <p className="note">The Engine has not run yet. Wait for the ticks on <a href="#/setup">Setup</a>, or ask the Copilot a what-if.</p>;
  if (!base.ladder?.length) return <p className="alert">{base.why_no_ladder ?? "No ladder in the latest engine run."} Run the Rival model, then the Engine again.</p>;

  const point = hover ?? base.ladder.find((p) => rec && Math.abs(p.tariff - rec.entry_bid) < 0.005) ?? base.ladder[0];
  const picked = drivers.find((x) => x.cell === pick);
  const ghostRec = ghost?.recommendation ?? null;
  const atEntry = (r: EngineResult | null) => {
    const e = r?.recommendation?.entry_bid;
    return e == null ? null : (r?.ladder.find((p) => Math.abs(p.tariff - e) < 0.005) ?? null);
  };
  return (
    <>
      <section className="cards" aria-label="At the price under the cursor">
        <div className="card"><div className="card-title">At {inr(point.tariff)}</div><div className="card-value">{pct(point.p_win_any)}</div><div className="note">chance of winning something · {pct(point.p_win_full)} all 200 MW</div></div>
        <div className="card"><div className="card-title">Expected</div><div className="card-value">{point.expected_mw.toFixed(0)} MW</div><div className="note">{pct(point.p_h1_eliminated, 1)} chance of being knocked out before the auction</div></div>
        <div className="card"><div className="card-title">Return at that price</div><div className="card-value">{pct(point.equity_irr, 1)}</div><div className="note">equity IRR · lowest DSCR {point.min_dscr?.toFixed(2) ?? "n/a"}</div></div>
      </section>
      <p className="help">How to read it: blue is the chance of winning something at each price (left axis). Green is the return at that price (right axis); the dotted green line is the board's {pct(base.hurdle)} hurdle. Light bars are the MW we expect to win. The red line is the walk-away and the shaded band is where to aim. Hover to read any price.</p>
      <Ladder ladder={base.ladder} ghost={ghost?.ladder ?? null} walkAway={rec?.walk_away} entry={rec?.entry_bid} target={rec ? [rec.target_low, rec.target_high] : null} hurdle={base.hurdle} onHover={setHover} />
      {rec && <ul className="reasons">{rec.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      <p className="note">Rival snapshot {base.snapshot_id} · engine run {baseRun?.id.slice(0, 8)}. Changing our costs moves the green line, not the blue one: rivals do not see our costs.</p>

      <section>
        <h2>Change an input and price it</h2>
        <p className="note">Pick any input the Auditor ranked, type a new value, and the Engine reprices the whole model on a copy. The result shows as the dashed line and in the table below.</p>
        <div className="board">
          <label>
            Input
            <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Which input to change">
              <option value="">choose</option>
              {drivers.map((d) => (
                <option key={d.cell} value={d.cell}>{d.label}</option>
              ))}
            </select>
          </label>
          <label>
            Now
            <input value={picked ? String(picked.value) : ""} readOnly aria-label="Current value" />
          </label>
          <label>
            New value
            <input type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} placeholder={picked ? String(picked.value) : ""} />
          </label>
          <button onClick={priceIt} disabled={!picked || !value.trim()}>Price it</button>
        </div>
        <p className="levers">
          <span className="note">Or one click:</span>
          {LEVERS.map((l) => (
            <button key={l.label} className="ghost" onClick={() => askWhatIf(l.message)}>{l.label}</button>
          ))}
        </p>
        {note && <p className="note">{note}</p>}
        <label>
          Compare with a saved scenario
          <select value={ghostId ?? ""} onChange={(e) => setGhostId(e.target.value || null)}>
            <option value="">none</option>
            {(scenarios.data ?? []).map((s: Scenario) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>
        {ghostId && !ghost && <p className="note">Waiting for the Engine to price that scenario.</p>}
        {ghost && (
          <table className="compare">
            <thead><tr><th>Number</th><th className="num">Base</th><th className="num">Scenario</th></tr></thead>
            <tbody>
              <tr><td>Price the model needs (breakeven)</td><td className="num">{inr(base.breakeven_tariff, 4)}</td><td className="num"><b>{inr(ghost.breakeven_tariff, 4)}</b></td></tr>
              <tr><td>Walk-away</td><td className="num">{inr(rec?.walk_away)}</td><td className="num"><b>{inr(ghostRec?.walk_away)}</b></td></tr>
              <tr><td>Entry bid</td><td className="num">{inr(rec?.entry_bid)}</td><td className="num"><b>{inr(ghostRec?.entry_bid)}</b></td></tr>
              <tr><td>Target range</td><td className="num">{rec ? `${inr(rec.target_low)} to ${inr(rec.target_high)}` : "n/a"}</td><td className="num"><b>{ghostRec ? `${inr(ghostRec.target_low)} to ${inr(ghostRec.target_high)}` : "n/a"}</b></td></tr>
              <tr><td>Chance of winning at the entry bid</td><td className="num">{pct(atEntry(base)?.p_win_any)}</td><td className="num"><b>{pct(atEntry(ghost)?.p_win_any)}</b></td></tr>
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>The field</h2>
        <p className="note">Each rival's chance of turning up and the price it is likely to stop at (10th, 50th and 90th percentile), from past auctions.</p>
        <table>
          <thead><tr><th>Rival</th><th>Type</th><th className="num">Turns up</th><th className="num">Stops at (p10 / p50 / p90)</th></tr></thead>
          <tbody>
            {field.map((p) => (
              <tr key={p.name}><td>{p.name}</td><td>{p.archetype.replace("_", " ")}</td><td className="num">{pct(p.p_participate)}</td><td className="num">{inr(p.floor_p10)} / {inr(p.floor_p50)} / {inr(p.floor_p90)}</td></tr>
            ))}
            {field.length === 0 && <tr><td colSpan={4} className="note">Run the Rival model to see the field.</td></tr>}
          </tbody>
        </table>
      </section>

      <section>
        <div className="section-head">
          <h2>Watch one auction play out</h2>
          <button className="ghost" onClick={playReplay}>Play one, from {inr(rec?.entry_bid ?? 2.45)} down to {inr(rec?.walk_away ?? 2.28)}</button>
        </div>
        <p className="note">One of the 5,000 simulated auctions, minute by minute, with us cutting one paisa at a time and never under the walk-away. For the real thing, use the Live Auction screen.</p>
        {replayError && <p className="alert">{replayError}</p>}
        {replay && (
          <ol className="replay">
            {replay.events.slice(0, 80).map((e, i) => (
              <li key={i}>
                <span className="minute">min {e.minute}</span>{" "}
                {e.type === "bid" && <>{String(e.bidder)} cuts {inr(e.old as number)} to {inr(e.new as number)}</>}
                {e.type === "extension" && <>extension to minute {String(e.until)}</>}
                {e.type === "open" && <>opens: {String(e.bidders)} bidders, {String(e.eligible_mw)} MW eligible</>}
                {e.type === "end" && <>ends. L1 {inr(e.l1 as number)}, band to {inr(e.band_ceiling as number)}</>}
              </li>
            ))}
            {replay.events.length > 80 && <li className="note">{replay.events.length - 80} more events</li>}
          </ol>
        )}
      </section>
    </>
  );
}
