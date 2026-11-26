import { useEffect, useState } from "react";
import { type Doc, type EngineResult, type LadderPoint, type Replay, type RivalResult, type Run, type Scenario, api, inr, pct } from "../api";
import { Ladder } from "../charts";
import { useLive } from "../hooks";

const LEVERS = [
  { label: "Interest +50 bp", message: "What if the interest rate rises by 50 basis points?" },
  { label: "CUF 30%", message: "What if CUF is 30%?" },
  { label: "Capex -5%", message: "What if capex falls by 5%?" },
  { label: "Modules at INR 10/Wp", message: "What if modules cost INR 10/Wp?" },
  { label: "O&M +10%", message: "What if O&M rises by 10%?" },
];

export function WarRoom({ workbook }: { workbook: Doc }) {
  const engineRun = useLive(() => api.latestRun("engine", workbook.id), 5000, [workbook.id]);
  const rivalRun = useLive(() => api.latestRun("rival"), 15000);
  const scenarios = useLive(() => api.scenarios(), 5000);
  const [hover, setHover] = useState<LadderPoint | null>(null);
  const [ghostId, setGhostId] = useState<string | null>(null);
  const [ghost, setGhost] = useState<LadderPoint[] | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const base = (engineRun.data?.result ?? null) as EngineResult | null;
  const baseRun = engineRun.data as Run | null;
  const rival = (rivalRun.data?.result ?? null) as RivalResult | null;
  const regime = base?.regime ?? "almm_40";
  const field = rival?.snapshots?.[regime]?.profiles ?? [];

  useEffect(() => {
    if (!ghostId) return setGhost(null);
    api.runs(`kind=engine&status=succeeded&limit=50`).then((runs) => {
      const r = runs.find((x) => x.params?.scenario_id === ghostId);
      setGhost(((r?.result as EngineResult | undefined)?.ladder ?? null) as LadderPoint[] | null);
    });
  }, [ghostId, scenarios.data]);

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
  const playReplay = () => {
    setReplayError(null);
    api.replay(workbook.id, 0, rec?.entry_bid ?? 2.45, rec?.walk_away ?? 2.28, regime).then(setReplay).catch((e: Error) => setReplayError(e.message));
  };

  if (!base) return <p className="note">No engine run yet. Start one from the Setup screen, or ask the Copilot a what-if.</p>;
  if (!base.ladder?.length) return <p className="alert">{base.why_no_ladder ?? "No ladder in the latest engine run."} Run the Rival model, then the Engine again.</p>;

  const point = hover ?? base.ladder.find((p) => rec && Math.abs(p.tariff - rec.entry_bid) < 0.005) ?? base.ladder[0];
  return (
    <>
      <section className="cards" aria-label="Crosshair">
        <div className="card"><div className="card-title">At {inr(point.tariff)}</div><div className="card-value">{pct(point.p_win_any)}</div><div className="note">chance of winning anything · {pct(point.p_win_full)} all 200 MW</div></div>
        <div className="card"><div className="card-title">Expected</div><div className="card-value">{point.expected_mw.toFixed(0)} MW</div><div className="note">{pct(point.p_h1_eliminated, 1)} chance of going out as H1</div></div>
        <div className="card"><div className="card-title">Returns</div><div className="card-value">{pct(point.equity_irr, 1)}</div><div className="note">equity IRR · min DSCR {point.min_dscr?.toFixed(2) ?? "n/a"}</div></div>
      </section>
      <Ladder ladder={base.ladder} ghost={ghost} walkAway={rec?.walk_away} entry={rec?.entry_bid} target={rec ? [rec.target_low, rec.target_high] : null} hurdle={base.hurdle} onHover={setHover} />
      {rec && <ul className="reasons">{rec.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      <p className="note">Snapshot {base.snapshot_id} · regime {regime} · engine run {baseRun?.id.slice(0, 8)}. Win odds do not move with cost what-ifs: rivals do not see our costs.</p>

      <section>
        <div className="section-head">
          <h2>What-if levers</h2>
          <span className="note">Each saves a scenario and reruns the Engine; the ghost line is the scenario's equity IRR.</span>
        </div>
        <p className="levers">
          {LEVERS.map((l) => (
            <button key={l.label} className="ghost" onClick={() => askWhatIf(l.message)}>{l.label}</button>
          ))}
        </p>
        {note && <p className="note">{note}</p>}
        <label>
          Show scenario as ghost
          <select value={ghostId ?? ""} onChange={(e) => setGhostId(e.target.value || null)}>
            <option value="">none</option>
            {(scenarios.data ?? []).map((s: Scenario) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>
      </section>

      <section>
        <h2>The field</h2>
        <table>
          <thead><tr><th>Rival</th><th>Type</th><th className="num">Shows up</th><th className="num">Floor p10 / p50 / p90</th></tr></thead>
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
          <h2>Replay one auction</h2>
          <button className="ghost" onClick={playReplay}>Play draw 0 from {inr(rec?.entry_bid ?? 2.45)} down to {inr(rec?.walk_away ?? 2.28)}</button>
        </div>
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
