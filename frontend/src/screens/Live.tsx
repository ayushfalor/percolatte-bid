import { useEffect, useState } from "react";
import { type Doc, type EngineResult, type LiveRead, type Observation, type RivalResult, api, inr, pct } from "../api";
import { Ladder } from "../charts";
import { useLive } from "../hooks";

// The auction day. The portal shows our price, our rank, the lowest price and the clock; market
// talk sometimes adds who is where. Type those in; the API conditions the rival draws on them and
// hands back the next move. Nothing is computed here, and nothing typed here changes a snapshot.

const L1 = "L1";
const OTHER = "other";
const ACTION: Record<string, { title: string; tone: "green" | "orange" | "red" }> = {
  hold: { title: "Hold", tone: "green" },
  cut: { title: "Cut", tone: "orange" },
  "walk away": { title: "Walk away", tone: "red" },
};

type Board = { observations: Observation[]; ourPrice: number | null; minutesLeft: number; ourRank: number | null; assumePace: boolean };
const EMPTY: Board = { observations: [], ourPrice: null, minutesLeft: 30, ourRank: null, assumePace: false };

function load(key: string): Board {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Board) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function Live({ workbook }: { workbook: Doc }) {
  const engineRun = useLive(() => api.latestRun("engine", workbook.id), 10000, [workbook.id]);
  const rivalRun = useLive(() => api.latestRun("rival"), 30000);
  const base = (engineRun.data?.result ?? null) as EngineResult | null;
  const rec = base?.recommendation ?? null;
  const rival = (rivalRun.data?.result ?? null) as RivalResult | null;
  const names = rival?.snapshots?.[base?.regime ?? "almm_40"]?.profiles.map((p) => p.name) ?? [];
  const storeKey = `live:${workbook.id}`;
  const [board, setBoard] = useState<Board>(() => load(storeKey));
  const [draft, setDraft] = useState({ minute: "0", bidder: L1, other: "", tariff: "" });
  const [read, setRead] = useState<LiveRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ourPrice = board.ourPrice ?? rec?.entry_bid ?? null;

  useEffect(() => {
    try {
      localStorage.setItem(storeKey, JSON.stringify(board));
    } catch {
      /* a private window forgets the board on reload; that is fine */
    }
  }, [board, storeKey]);

  useEffect(() => {
    if (ourPrice == null) return;
    const id = setTimeout(() => {
      api
        .live(workbook.id, {
          observations: board.observations,
          our_price: ourPrice,
          minutes_left: board.minutesLeft,
          our_rank: board.ourRank,
          assume_pace_holds: board.assumePace,
        })
        .then((r) => (setRead(r), setError(null)))
        .catch((e: Error) => setError(e.message));
    }, 250);
    return () => clearTimeout(id);
  }, [workbook.id, board, ourPrice]);

  const add = () => {
    const tariff = parseFloat(draft.tariff);
    const minute = parseInt(draft.minute, 10);
    const bidder = draft.bidder === OTHER ? draft.other.trim() : draft.bidder;
    if (!Number.isFinite(tariff) || !Number.isFinite(minute) || !bidder) return;
    setBoard((b) => ({ ...b, observations: [...b.observations, { minute, bidder, tariff }] }));
    setDraft((d) => ({ ...d, tariff: "" }));
  };
  const remove = (i: number) => setBoard((b) => ({ ...b, observations: b.observations.filter((_, j) => j !== i) }));
  const num = (v: string) => (v.trim() === "" ? null : Number(v));

  if (!base?.ladder?.length) return <p className="note">The Engine has not priced this model yet. Wait for the four ticks on <a href="#/setup">Setup</a>.</p>;
  const action = read ? ACTION[read.action] : null;

  return (
    <>
      <section>
        <h2>The board right now</h2>
        <div className="board">
          <label title="The price we are showing on the portal. Starts at the Brief's entry bid.">
            Our price (₹/kWh)
            <input type="number" step="0.01" value={ourPrice ?? ""} onChange={(e) => setBoard((b) => ({ ...b, ourPrice: num(e.target.value) }))} />
          </label>
          <label title="The portal's countdown. Extensions add eight minutes.">
            Minutes left
            <input type="number" min={0} max={240} value={board.minutesLeft} onChange={(e) => setBoard((b) => ({ ...b, minutesLeft: Number(e.target.value) || 0 }))} />
          </label>
          <label title="Our rank as the portal shows it. Leave empty if unsure.">
            Our rank (optional)
            <input type="number" min={1} value={board.ourRank ?? ""} onChange={(e) => setBoard((b) => ({ ...b, ourRank: num(e.target.value) }))} />
          </label>
          <label className="check" title="Also assume every rival that is cutting keeps cutting at the same pace until the clock runs out">
            <input type="checkbox" checked={board.assumePace} onChange={(e) => setBoard((b) => ({ ...b, assumePace: e.target.checked }))} /> Assume paces hold
          </label>
        </div>
      </section>

      <section>
        <h2>Add a bid you can see</h2>
        <p className="note">L1 is the lowest price on the board when it is not ours. Name a rival only if you know who is where; names are those on the Rivals screen.</p>
        <form
          className="board"
          onSubmit={(e) => {
            e.preventDefault();
            add();
          }}
        >
          <label>
            Minute
            <input type="number" min={0} max={240} value={draft.minute} onChange={(e) => setDraft((d) => ({ ...d, minute: e.target.value }))} />
          </label>
          <label>
            Who
            <select value={draft.bidder} onChange={(e) => setDraft((d) => ({ ...d, bidder: e.target.value }))} aria-label="Which bidder">
              <option value={L1}>L1, lowest price shown</option>
              {names.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
              <option value={OTHER}>Someone else</option>
            </select>
            {draft.bidder === OTHER && <input value={draft.other} onChange={(e) => setDraft((d) => ({ ...d, other: e.target.value }))} placeholder="name" aria-label="Bidder name" />}
          </label>
          <label>
            Their price (₹/kWh)
            <input type="number" step="0.01" value={draft.tariff} onChange={(e) => setDraft((d) => ({ ...d, tariff: e.target.value }))} />
          </label>
          <button>Add</button>
        </form>
        {board.observations.length > 0 && (
          <table>
            <thead><tr><th>Minute</th><th>Who</th><th className="num">Price</th><th /></tr></thead>
            <tbody>
              {board.observations.map((o, i) => (
                <tr key={`${o.minute}-${o.bidder}-${i}`}><td>{o.minute}</td><td>{o.bidder}</td><td className="num">{inr(o.tariff)}</td><td className="num"><button className="ghost" onClick={() => remove(i)}>remove</button></td></tr>
              ))}
            </tbody>
          </table>
        )}
        {board.observations.length > 0 && <p className="levers"><button className="ghost" onClick={() => setBoard(EMPTY)}>Clear the board</button></p>}
      </section>

      {error && <p className="alert">{error}</p>}
      {read && action && (
        <>
          <section className="cards" aria-label="The next move">
            <div className={`card card-${action.tone}`}>
              <div className="card-title">Do now</div>
              <div className="card-value">{action.title}{read.cut_to != null ? ` to ${inr(read.cut_to)}` : ""}</div>
              <div className="note">{read.why[read.l1 != null ? 1 : 0]}</div>
            </div>
            <div className="card">
              <div className="card-title">At {inr(read.at_our_price.tariff)}</div>
              <div className="card-value">{pct(read.at_our_price.p_win_any)}</div>
              <div className="note">chance of winning something · {read.at_our_price.expected_mw.toFixed(0)} MW expected</div>
            </div>
            <div className="card">
              <div className="card-title">The band</div>
              <div className="card-value">{read.band_ceiling != null ? inr(read.band_ceiling) : "n/a"}</div>
              <div className="note">{read.l1 != null ? `L1 ${inr(read.l1)} + 2%. We are ${read.in_band ? "inside" : "outside"} it.` : "Add the L1 to see the band."}</div>
            </div>
          </section>
          <ul className="reasons">{read.why.map((w) => <li key={w}>{w}</li>)}</ul>
          {read.caveats.map((c) => <p key={c} className="note">{c}</p>)}
          <p className="note">{read.survivors.toLocaleString()} of {read.of.toLocaleString()} simulated auctions agree with the board · walk-away {inr(read.recommendation.walk_away)} · snapshot {read.snapshot_id}</p>

          {read.pace.length > 0 && (
            <section>
              <h2>How hard each one is cutting</h2>
              <table>
                <thead><tr><th>Who</th><th className="num">Bids</th><th className="num">Last</th><th className="num">Paise / min</th><th className="num">At the close</th><th>Reading</th></tr></thead>
                <tbody>
                  {read.pace.map((p) => (
                    <tr key={p.bidder} className={p.below_record ? "warn" : ""}><td>{p.bidder}</td><td className="num">{p.bids}</td><td className="num">{inr(p.last_tariff)}</td><td className="num">{p.paise_per_minute.toFixed(1)}</td><td className="num">{p.projected_at_close != null ? inr(p.projected_at_close) : "–"}</td><td className="what">{p.note}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <section>
            <h2>Odds at every price, given the board</h2>
            <p className="help">Blue: chance of winning something at each price, in the simulated auctions that agree with the board. Dashed grey: the same before any bid was typed in. Red line: the walk-away. Hover to read a price.</p>
            <Ladder ladder={read.ladder} ghost={base.ladder} ghostLine="odds" walkAway={read.recommendation.walk_away} entry={ourPrice} target={[read.recommendation.target_low, read.recommendation.target_high]} hurdle={base.hurdle} />
          </section>
        </>
      )}
    </>
  );
}
