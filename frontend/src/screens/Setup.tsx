import { useRef, useState } from "react";
import { type Agent, type Doc, type Health, type Run, api } from "../api";
import { useLive } from "../hooks";

type Light = "ok" | "busy" | "down" | "off";
const kindName: Record<string, string> = { workbook: "Bid model", tender: "Tender (RfS)", history: "Auction history" };
const fmtSize = (n: number) => (n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : `${Math.round(n / 1000)} KB`);

function summarize(run: Run): string {
  if (run.status === "failed") return (run.error ?? "Failed").split("\n")[0];
  if (run.status !== "succeeded") return run.message ?? "Waiting for the worker";
  const r = run.result ?? {};
  if (run.kind === "reader" && r.kind === "workbook") {
    const totals = r.totals as { sheets: number; formulas: number };
    return `${totals.sheets} sheets, ${totals.formulas} formulas`;
  }
  if (run.kind === "reader" && r.kind === "tender") return `${r.pages} pages, ${(r.facts as unknown[] | undefined)?.length ?? 0} facts`;
  if (run.kind === "reader" && r.kind === "history") return `${r.bids} bids cleaned`;
  if (run.kind === "auditor") return `${(r.findings as unknown[]).length} findings, corrected ₹${(r.corrected_breakeven as number).toFixed(4)}`;
  if (run.kind === "rival") return `${r.rivals} rivals, three snapshots`;
  if (run.kind === "engine") return (r.ladder as unknown[])?.length ? `ladder of ${(r.ladder as unknown[]).length} prices` : `breakeven ₹${(r.breakeven_tariff as number).toFixed(4)}`;
  if (run.kind === "copilot") return String((r.answer as string) ?? "").slice(0, 80);
  return "Done";
}

export function Setup({
  health,
  docs,
  workbook,
  agents,
  runs,
  onUploaded,
}: {
  health: Health | null;
  docs: Doc[];
  workbook: Doc | undefined;
  agents: Agent[];
  runs: Run[];
  onUploaded: (id: string) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState<string | null>(null);
  const runsLive = useLive(() => api.runs("limit=40"), 1500);
  const list = runsLive.data ?? runs;
  const pending = list.filter((r) => r.status === "queued" || r.status === "running").length;
  const apiLight: Light = health ? "ok" : "busy";
  const history = docs.find((d) => d.kind === "history");

  async function upload(file: File) {
    setNote(`Uploading ${file.name}`);
    try {
      const res = await api.upload(file);
      setNote(res.created ? `${file.name} added. It is being read, audited and priced; the Bid Brief fills in as runs finish.` : `${file.name} was already loaded.`);
      if (res.document?.id) onUploaded(res.document.id);
    } catch (e) {
      setNote((e as Error).message);
    }
  }
  async function runAll() {
    if (!workbook || !history) return setNote("Need a bid model and an auction history first.");
    setNote(`Queued for ${workbook.filename}: Auditor, Rival model, Engine. The Engine runs after the rivals.`);
    await api.startRun("auditor", workbook.id);
    await api.startRun("rival", history.id);
    await api.startRun("engine", workbook.id);
    runsLive.refresh();
  }

  return (
    <>
      <section className="strip" aria-label="System status">
        <Status light={apiLight} title="API" detail={health ? `Running v${health.version}` : "Checking"} />
        <Status light={health?.database === "ok" ? "ok" : "busy"} title="Database" detail={health?.database === "ok" ? "Connected" : "Waiting"} />
        <Status light={pending ? "busy" : "ok"} title="Worker" detail={pending ? `${pending} job${pending > 1 ? "s" : ""} in progress` : "Idle, queue empty"} />
        <Status light={health?.llm_mode === "live" ? "ok" : "off"} title="AI" detail={health?.llm_mode === "live" ? "Live (API key set)" : "Offline: rules and cache"} />
      </section>
      <section>
        <div className="section-head">
          <h2>Files</h2>
          <button className="ghost" onClick={() => fileInput.current?.click()}>Upload a file</button>
          <button onClick={runAll}>Run the agents again</button>
          <input ref={fileInput} type="file" accept=".xlsx,.xlsm,.pdf" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </div>
        {note && <p className="note">{note}</p>}
        <table>
          <thead><tr><th>File</th><th>Type</th><th className="num">Size</th></tr></thead>
          <tbody>
            {docs.map((d) => <tr key={d.id}><td>{d.filename}</td><td>{kindName[d.kind] ?? d.kind}</td><td className="num">{fmtSize(d.size_bytes)}</td></tr>)}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Timeline</h2>
        <table>
          <thead><tr><th>Agent</th><th>Status</th><th>What happened</th><th className="num">Time</th><th className="num">Cost</th></tr></thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.id}>
                <td>{r.kind}</td>
                <td><span className={`pill pill-${r.status}`}>{r.status}</span>{r.status === "running" && <span className="bar"><span style={{ width: `${Math.round(r.progress * 100)}%` }} /></span>}</td>
                <td className="what">{summarize(r)}</td>
                <td className="num">{r.result?.elapsed_ms != null ? `${((r.result.elapsed_ms as number) / 1000).toFixed(1)} s` : ""}</td>
                <td className="num">${r.cost_usd.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Agents</h2>
        <ul className="agents">
          {agents.map((a) => (
            <li key={a.kind} className={a.built ? "" : "agent-todo"}><strong>{a.title}</strong> {a.job}{!a.built && <span className="tag">Not built</span>}</li>
          ))}
        </ul>
      </section>
    </>
  );
}

function Status({ light, title, detail }: { light: Light; title: string; detail: string }) {
  return (
    <div className="status">
      <span className={`dot dot-${light}`} aria-hidden />
      <div><div className="status-title">{title}</div><div className="status-detail">{detail}</div></div>
    </div>
  );
}
