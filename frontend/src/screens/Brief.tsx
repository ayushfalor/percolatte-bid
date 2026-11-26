import { type Brief as BriefT, type Doc, api, inr, paise } from "../api";
import { useLive } from "../hooks";

const AGENT_DOC: Record<string, "workbook" | "history"> = { auditor: "workbook", engine: "workbook", rival: "history" };
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
        <Card title="Entry bid" value={inr(b.entry_bid)} note="Sealed envelope. Leaves room for the usual cut." />
        <Card title="Target range" value={b.target_low == null ? "n/a" : `${inr(b.target_low)} to ${inr(b.target_high)}`} note="Where chance of winning times profit is highest." />
        <Card title="Walk-away" value={inr(b.walk_away)} note="Never go below this in the auction." tone="red" />
      </section>
      {b.pending.length > 0 && (
        <p className="alert">
          Waiting on: {b.pending.join(", ")}.{" "}
          {b.pending.map((k) => (
            <button key={k} className="ghost" onClick={() => start(k)}>Run {k}</button>
          ))}
        </p>
      )}

      <section>
        <h2>The bridge</h2>
        <p className="note">From the model as received to the corrected breakeven. Each step is one fix the Auditor is sure about, priced by applying it.</p>
        <table>
          <tbody>
            <tr><td>Model as received</td><td className="num">{inr(b.as_received, 4)}</td><td /></tr>
            {sure.map((s) => (
              <tr key={s.label}><td>{s.label}{s.where && <span className="note"> · {s.where}</span>}</td><td className="num">{paise(s.delta)}</td><td className="num">{inr(s.after, 4)}</td></tr>
            ))}
            <tr className="total"><td>Corrected breakeven</td><td /><td className="num">{inr(b.corrected, 4)}</td></tr>
            {levers.map((s) => (
              <tr key={s.label} className="lever"><td>Lever, not in the total: {s.label}</td><td className="num">{paise(s.delta)}</td><td className="num">{inr(s.after, 4)}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Depends most on</h2>
        <p className="chips">
          {b.depends_most_on.map((d) => (
            <span key={d.cell} className="chip" title={`${d.cell}: ${inr(d.low)} to ${inr(d.high)}`}>{d.label} <b>{inr(d.swing)}</b></span>
          ))}
          {b.depends_most_on.length === 0 && <span className="note">Run the Auditor to rank the inputs.</span>}
        </p>
      </section>

      <section>
        <h2>Must-dos</h2>
        <table>
          <thead><tr><th>Item</th><th className="num">Amount</th><th>Basis</th></tr></thead>
          <tbody>
            {Object.entries(b.must_dos).map(([k, m]) => (
              <tr key={k}><td>{MUST_DO_NAMES[k] ?? k}</td><td className="num">₹{m.cr.toFixed(1)} Cr</td><td className="what">₹{m.per_mw_inr.toLocaleString("en-IN")}/MW on {m.our_mw} MW, clause {m.clause}, page {m.pdf_page}</td></tr>
            ))}
            {Object.keys(b.must_dos).length === 0 && <tr><td colSpan={3} className="note">No tender facts yet. The Reader fills these from the RfS.</td></tr>}
          </tbody>
        </table>
      </section>

      <p className="note">
        Sources: {Object.entries(b.sources).map(([k, v]) => `${k} run ${v.slice(0, 8)}`).join(", ") || "none yet"}
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
