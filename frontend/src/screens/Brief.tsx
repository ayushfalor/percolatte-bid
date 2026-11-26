import { type Brief as BriefT, type Doc, api, inr, paise } from "../api";
import { useLive } from "../hooks";

const AGENT_DOC: Record<string, "workbook" | "history"> = { auditor: "workbook", engine: "workbook", rival: "history" };
const AGENT_NAME: Record<string, string> = { auditor: "Auditor", rival: "Rival model", engine: "Engine" };
const MUST_DO_NAMES: Record<string, string> = { emd: "EMD", pbg: "PBG", success_charge: "Success charge", net_worth: "Net worth" };

export function Brief({ workbook, docs }: { workbook: Doc; docs: Doc[] }) {
  const brief = useLive(() => api.brief(workbook.id), 4000, [workbook.id]);
  const b: BriefT | null = brief.data;
  if (brief.error) return <p className="alert">{brief.error}</p>;
  if (!b) return <p className="note">Loading the brief.</p>;

  const start = (kind: string) => {
    const doc = docs.find((d) => d.kind === AGENT_DOC[kind]);
    if (doc) api.startRun(kind, doc.id).then(brief.refresh);
  };
  const sure = b.bridge.filter((s) => !s.assumed);
  const levers = b.bridge.filter((s) => s.assumed);

  return (
    <>
      <section className="cards" aria-label="The three numbers">
        <Card title="Entry bid" value={inr(b.entry_bid)} note="The price to write in the sealed bid. Leaves room to cut in the auction." />
        <Card title="Target range" value={b.target_low == null ? "n/a" : `${inr(b.target_low)} to ${inr(b.target_high)}`} note="Aim to finish here: the best balance of winning and profit." />
        <Card title="Walk-away" value={inr(b.walk_away)} note={b.basis.length ? "Never go under this in the auction. Computed on the corrected model." : "Never go under this in the auction."} tone="red" />
      </section>
      {b.basis.length > 0 && <p className="note">Floor computed on: {b.basis.join("; ")}.</p>}
      {b.reasons.length > 0 && <ul className="reasons">{b.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      {Object.entries(b.problems ?? {}).map(([k, why]) => (
        <p key={k} className="alert">The {AGENT_NAME[k] ?? k} could not work on this model: {why} <button className="ghost" onClick={() => start(k)}>Try again</button></p>
      ))}
      {b.pending.filter((k) => !(b.problems ?? {})[k]).length > 0 && (
        <p className="note">
          Still working: {b.pending.filter((k) => !(b.problems ?? {})[k]).map((k) => AGENT_NAME[k] ?? k).join(", ")}. This fills in by itself.{" "}
          {b.pending.filter((k) => !(b.problems ?? {})[k]).map((k) => (
            <button key={k} className="ghost" onClick={() => start(k)}>Run {AGENT_NAME[k] ?? k} now</button>
          ))}
        </p>
      )}

      <section>
        <h2>From the model as uploaded to the corrected price</h2>
        <p className="note">The first line is the price the model needs as uploaded. Each step is one error the Auditor is sure about, and what fixing it does to that price.</p>
        <table>
          <tbody>
            <tr><td>Price the model needs, as uploaded</td><td className="num">{inr(b.as_received, 4)}</td><td /></tr>
            {sure.map((s) => (
              <tr key={s.label}><td>{s.label}{s.where && <span className="note"> · {s.where}</span>}</td><td className="num">{paise(s.delta)}</td><td className="num">{inr(s.after, 4)}</td></tr>
            ))}
            <tr className="total"><td>Price the model needs, corrected</td><td /><td className="num">{inr(b.corrected, 4)}</td></tr>
            {levers.map((s) => (
              <tr key={s.label} className="lever"><td>Lever, not in the total: {s.label}</td><td className="num">{paise(s.delta)}</td><td className="num">{inr(s.after, 4)}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>What moves the price most</h2>
        <p className="chips">
          {b.depends_most_on.map((d) => (
            <span key={d.cell} className="chip" title={`${d.cell}: ${inr(d.low)} to ${inr(d.high)}`}>{d.label} <b>{inr(d.swing)}</b></span>
          ))}
          {b.depends_most_on.length === 0 && <span className="note">The Auditor ranks the inputs once it has run.</span>}
        </p>
      </section>

      <section>
        <h2>Money and paperwork to have ready</h2>
        <table>
          <thead><tr><th>Item</th><th className="num">Amount</th><th>Basis</th></tr></thead>
          <tbody>
            {Object.entries(b.must_dos).map(([k, m]) => (
              <tr key={k}><td>{MUST_DO_NAMES[k] ?? k}</td><td className="num">₹{m.cr.toFixed(1)} Cr</td><td className="what">₹{m.per_mw_inr.toLocaleString("en-IN")}/MW on {m.our_mw} MW, clause {m.clause}, page {m.pdf_page}</td></tr>
            ))}
            {Object.keys(b.must_dos).length === 0 && <tr><td colSpan={3} className="note">Filled in from the tender once the Reader has read it.</td></tr>}
          </tbody>
        </table>
      </section>

      <p className="note">
        Where this came from: {Object.entries(b.sources).map(([k, v]) => `${k} run ${v.slice(0, 8)}`).join(", ") || "none yet"}
        {b.snapshot_id && ` · rival snapshot ${b.snapshot_id}`}
      </p>
    </>
  );
}

function Card({ title, value, note, tone }: { title: string; value: string; note: string; tone?: "red" }) {
  return (
    <div className={`card${tone ? ` card-${tone}` : ""}`}>
      <div className="card-title">{title}</div>
      <div className="card-value">{value}</div>
      <div className="note">{note}</div>
    </div>
  );
}
