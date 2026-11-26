import { useRef, useState } from "react";
import { type Agent, type Doc, type Health, type LlmSetting, type Run, type UploadRefusal, UploadRefused, api } from "../api";
import { useLive } from "../hooks";
import type { Progress } from "../status";

type Light = "ok" | "busy" | "down" | "off";
const kindName: Record<string, string> = { workbook: "Bid model", tender: "Tender (RfS)", history: "Auction history" };
const fmtSize = (n: number) => (n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : `${Math.round(n / 1000)} KB`);
const MARK: Record<string, string> = { done: "✓", busy: "…", failed: "✕", todo: "○" };

const money = (v: unknown, digits = 4) => (typeof v === "number" ? `₹${v.toFixed(digits)}` : "n/a");
const count = (v: unknown) => (Array.isArray(v) ? v.length : 0);

// One line per stored run. A result from an older version may lack a field; that is a "n/a", never a crash.
function summarize(run: Run): string {
  if (run.status === "failed") return (run.error ?? "Failed").split("\n")[0];
  if (run.status !== "succeeded") return run.message ?? "Waiting for the worker";
  const r = run.result ?? {};
  if (run.kind === "reader" && r.kind === "workbook") {
    const totals = (r.totals ?? {}) as { sheets?: number; formulas?: number };
    return `${totals.sheets ?? "?"} sheets, ${totals.formulas ?? "?"} formulas`;
  }
  if (run.kind === "reader" && r.kind === "tender") return `${r.pages ?? "?"} pages, ${count(r.facts)} facts`;
  if (run.kind === "reader" && r.kind === "history") return `${r.bids ?? "?"} bids cleaned`;
  if (run.kind === "auditor") return `${count(r.findings)} findings, corrected ${money(r.corrected_breakeven)}`;
  if (run.kind === "rival") return `${r.rivals ?? "?"} rivals, three snapshots`;
  if (run.kind === "engine") return count(r.ladder) ? `ladder of ${count(r.ladder)} prices` : `breakeven ${money(r.breakeven_tariff)}`;
  if (run.kind === "copilot") return String(r.answer ?? "").slice(0, 80);
  return "Done";
}

export function Setup({
  health,
  docs,
  workbook,
  agents,
  runs,
  progress,
  onUploaded,
}: {
  health: Health | null;
  docs: Doc[];
  workbook: Doc | undefined;
  agents: Agent[];
  runs: Run[];
  progress: Progress;
  onUploaded: (id: string) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<UploadRefusal | null>(null);
  const reqs = useLive(() => api.requirements(), 0);
  const runsLive = useLive(() => api.runs("limit=60"), 1500);
  const list = runsLive.data ?? runs;
  const pending = list.filter((r) => r.status === "queued" || r.status === "running").length;
  const apiLight: Light = health ? "ok" : "busy";
  const history = docs.find((d) => d.kind === "history");

  async function upload(file: File) {
    setNote(`Uploading ${file.name}`);
    try {
      const res = await api.upload(file);
      setNote(res.created ? `${file.name} added. It is being read, checked and priced; the ticks fill in as each step finishes.` : `${file.name} was already loaded.`);
      if (res.document?.id) onUploaded(res.document.id);
    } catch (e) {
      if (e instanceof UploadRefused) {
        setNote(null);
        setRefusal(e.refusal);
        return;
      }
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
        <Status light={apiLight} title="App" detail={health ? `Running v${health.version}` : "Starting"} />
        <Status light={health?.database === "ok" ? "ok" : "busy"} title="Database" detail={health?.database === "ok" ? "Connected" : "Waiting"} />
        <Status light={pending ? "busy" : "ok"} title="Agents" detail={pending ? `${pending} job${pending > 1 ? "s" : ""} running` : "Idle"} />
        <Status light={health?.llm_mode === "live" ? "ok" : "off"} title="Live AI" detail={health?.llm_mode === "live" ? "On" : "Off: rules and cached answers"} />
      </section>

      <section className="steps">
        <div className="step">
          <h2><span className="step-no">1</span> Load your files</h2>
          <p>A bid model (.xlsx), the tender (.pdf) and the auction history (.xlsx). A sample project is loaded so you can look around first; upload your own model and it becomes the project.</p>
          <p className="levers">
            <button onClick={() => fileInput.current?.click()}>Upload a file</button>
            <input ref={fileInput} type="file" accept=".xlsx,.xlsm,.pdf" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </p>
          {note && <p className="note">{note}</p>}
          <details className="needs">
            <summary>What a bid model needs, and the template</summary>
            <p>Any layout works: sheets, rows and names can be yours. The app finds its cells by their labels, so a model must have these next to the right cells. A file without the required ones is refused at upload and told what is missing.</p>
            <ul>
              {(reqs.data?.requirements ?? []).map((r) => (
                <li key={r.key}><b>{r.title}</b>{r.required ? "" : " (optional)"}: {r.how}.</li>
              ))}
            </ul>
            <p><a className="button" href="/api/template" download="bid_model_template.xlsx">Download the template (.xlsx)</a> <span className="note">It is the sample model: copy its labels, or fill it with your own numbers.</span></p>
          </details>
          <table>
            <thead><tr><th>File</th><th>What it is</th><th className="num">Size</th></tr></thead>
            <tbody>
              {docs.map((d) => <tr key={d.id}><td>{d.filename}{d.meta?.sample ? <span className="tag">sample</span> : null}</td><td>{kindName[d.kind] ?? d.kind}</td><td className="num">{fmtSize(d.size_bytes)}</td></tr>)}
            </tbody>
          </table>
        </div>

        <div className="step">
          <h2><span className="step-no">2</span> Let the agents work</h2>
          <p>Four steps run by themselves: the model is read, checked for errors, the rivals are modelled from history, then every price is tested.{workbook ? ` Now: ${progress.status.toLowerCase()}.` : ""}</p>
          <ol className="ticks">
            {progress.steps.map((s) => (
              <li key={s.key} className={`tick tick-${s.state}`} title={s.detail}>{MARK[s.state]} {s.title}</li>
            ))}
          </ol>
          <p className="levers"><button className="ghost" onClick={runAll} title="Queue the Auditor, the Rival model and the Engine again for the current model">Run again</button></p>
        </div>

        <div className="step">
          <h2><span className="step-no">3</span> Read the Brief</h2>
          <p>Three numbers: the sealed bid, where to aim to finish, and the price never to go under. Then the War Room to see how they move, and the Live Auction on the day.</p>
          <p className="levers"><a className="button" href="#/brief">Open the Bid Brief</a></p>
        </div>
      </section>

      <LiveAi health={health} />
      {refusal && (
        <div className="modal-backdrop" role="presentation" onClick={() => setRefusal(null)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="refused-title" onClick={(e) => e.stopPropagation()}>
            <h2 id="refused-title">This file was not accepted</h2>
            <p>{refusal.message}</p>
            {refusal.missing.length > 0 && (
              <ul>
                {refusal.missing.map((m) => <li key={m}>Missing: {m}</li>)}
              </ul>
            )}
            <p className="levers">
              <a className="button" href={refusal.template} download="bid_model_template.xlsx">Download the template</a>
              <button className="ghost" onClick={() => setRefusal(null)}>Close</button>
            </p>
          </div>
        </div>
      )}

      <details className="engineer">
        <summary>Details for engineers: every run and every agent</summary>
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
        <ul className="agents">
          {agents.map((a) => (
            <li key={a.kind} className={a.built ? "" : "agent-todo"}><strong>{a.title}</strong> {a.job}{!a.built && <span className="tag">Not built</span>}</li>
          ))}
        </ul>
      </details>
    </>
  );
}

function LiveAi({ health }: { health: Health | null }) {
  const setting = useLive(() => api.llmSetting(), 5000);
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const s: LlmSetting | null = setting.data;
  const live = (s?.mode ?? health?.llm_mode) === "live";

  async function turnOn() {
    setBusy(true);
    setNote("Checking the key with Anthropic.");
    try {
      await api.setLlm(secret);
      setSecret("");
      setNote("Live AI is on. The Copilot now answers free-form questions; new tenders get a model pass.");
      setting.refresh();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function turnOff() {
    await api.clearLlm();
    setNote("Key forgotten. Back to rules and cached answers.");
    setting.refresh();
  }

  return (
    <section className="ai-box">
      <h2>Live AI, optional</h2>
      {live ? (
        <>
          <p>On{s?.source === "env" ? ", from the .env file" : s?.source === "saved" ? ", key saved in this app" : ""}. Model: {s?.model}. The Copilot answers questions the rules cannot, and every number it writes is still checked against the tools.</p>
          {s?.source === "saved" && <p className="levers"><button className="ghost" onClick={turnOff}>Turn off and forget the key</button></p>}
        </>
      ) : (
        <>
          <p>Everything works without it. To turn it on, paste your own Anthropic key{s?.unlockable ? ", or the passphrase that came with the submission note" : ""}. It is checked once, then kept only in this app’s local database, never in the repo.</p>
          <form
            className="levers"
            onSubmit={(e) => {
              e.preventDefault();
              turnOn();
            }}
          >
            <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={s?.unlockable ? "passphrase or key" : "Anthropic key"} aria-label="Anthropic key or passphrase" style={{ width: "22em" }} />
            <button disabled={busy || !secret.trim()}>{busy ? "Checking" : "Turn on live AI"}</button>
          </form>
        </>
      )}
      {note && <p className="note">{note}</p>}
    </section>
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
