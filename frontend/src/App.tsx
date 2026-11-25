import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Agent, type Doc, type GoalSeek, type Run } from "./api";

// Scaffold screen: proves every moving part works (web, api, database, worker, agents)
// and runs one real calculation. The bid manager experience replaces this page.

type Light = "ok" | "busy" | "down" | "off";

function useLive<T>(load: () => Promise<T>, everyMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      load()
        .then((d) => alive && (setData(d), setError(null)))
        .catch((e: Error) => alive && setError(e.message));
    tick();
    const id = setInterval(tick, everyMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [load, everyMs]);
  return { data, error };
}

const fmtSize = (n: number) => (n > 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : `${Math.round(n / 1000)} KB`);
const kindName: Record<string, string> = { workbook: "Bid model", tender: "Tender (RfS)", history: "Auction history" };

function Status({ light, title, detail }: { light: Light; title: string; detail: string }) {
  return (
    <div className="status">
      <span className={`dot dot-${light}`} aria-hidden />
      <div>
        <div className="status-title">{title}</div>
        <div className="status-detail">{detail}</div>
      </div>
    </div>
  );
}

function summarize(run: Run): string {
  if (run.status === "failed") return (run.error ?? "Failed").split("\n")[0];
  if (run.status !== "succeeded") return run.message ?? "Waiting for the worker";
  const r = run.result ?? {};
  if (run.kind === "reader" && r.kind === "workbook") {
    const parity = r.parity as { status: string; matched: number; compared: number } | undefined;
    const totals = r.totals as { sheets: number; formulas: number };
    const check = !parity
      ? ""
      : parity.status === "no_cached_values"
        ? ", no saved Excel values to compare"
        : `, ${parity.matched}/${parity.compared} match Excel`;
    return `${totals.sheets} sheets, ${totals.formulas} formulas${check}`;
  }
  if (run.kind === "reader" && r.kind === "tender") return `${r.pages} pages read, ${(r.needs_ocr as number[]).length} need OCR`;
  if (run.kind === "reader" && r.kind === "history") return `${r.bids} bids, ${(r.fixes as string[]).length} data fixes logged`;
  if (run.kind === "engine" && typeof r.breakeven_tariff === "number") return `Breakeven ₹${r.breakeven_tariff.toFixed(4)}/kWh at ${((r.hurdle as number) * 100).toFixed(0)}% equity IRR`;
  return "Done";
}

export default function App() {
  const health = useLive(useCallback(api.health, []), 3000);
  const runs = useLive(useCallback(api.runs, []), 1500);
  const docs = useLive(useCallback(api.documents, []), 5000);
  const agents = useLive(useCallback(api.agents, []), 30000);

  const workbook = docs.data?.find((d: Doc) => d.kind === "workbook");
  const [target, setTarget] = useState("0.14");
  const [seek, setSeek] = useState<GoalSeek | null>(null);
  const [seekError, setSeekError] = useState<string | null>(null);
  const [seeking, setSeeking] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploadNote, setUploadNote] = useState<string | null>(null);

  const apiLight: Light = health.error ? "down" : health.data ? "ok" : "busy";
  const pending = (runs.data ?? []).filter((r) => r.status === "queued" || r.status === "running").length;

  async function findBreakeven() {
    if (!workbook) return;
    setSeeking(true);
    setSeekError(null);
    try {
      setSeek(await api.goalSeek(workbook.id, "Tariff", "Returns!C8", Number(target)));
    } catch (e) {
      setSeekError((e as Error).message);
    } finally {
      setSeeking(false);
    }
  }

  async function upload(file: File) {
    setUploadNote(`Uploading ${file.name}`);
    try {
      const res = await api.upload(file);
      setUploadNote(res.created ? `${file.name} added. The Reader is on it.` : `${file.name} was already loaded.`);
    } catch (e) {
      setUploadNote((e as Error).message);
    }
  }

  return (
    <main>
      <header>
        <h1>Bid Workbench</h1>
        <p className="lede">System check for the SECI C&amp;I-1 bid workspace. Every part below should show green before you start.</p>
      </header>

      {health.error && (
        <p className="alert" role="alert">
          Can’t reach the API. Check that the containers are up with <code>docker compose ps</code>, then look at{" "}
          <code>docker compose logs api</code>.
        </p>
      )}

      <section className="strip" aria-label="System status">
        <Status light={apiLight} title="API" detail={health.data ? `Running v${health.data.version}` : health.error ? "Not reachable" : "Checking"} />
        <Status light={health.data?.database === "ok" ? "ok" : apiLight === "down" ? "down" : "busy"} title="Database" detail={health.data?.database === "ok" ? "Connected" : "Waiting"} />
        <Status light={pending ? "busy" : apiLight === "ok" ? "ok" : "off"} title="Worker" detail={pending ? `${pending} job${pending > 1 ? "s" : ""} in progress` : "Idle, queue empty"} />
        <Status
          light={health.data?.llm_mode === "live" ? "ok" : "off"}
          title="AI"
          detail={health.data?.llm_mode === "live" ? "Live (API key set)" : "Offline mode: cached results"}
        />
      </section>

      <section>
        <div className="section-head">
          <h2>Files</h2>
          <button className="ghost" onClick={() => fileInput.current?.click()}>Upload a file</button>
          <input ref={fileInput} type="file" accept=".xlsx,.xlsm,.pdf" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </div>
        {uploadNote && <p className="note">{uploadNote}</p>}
        <table>
          <thead>
            <tr><th>File</th><th>Type</th><th className="num">Size</th></tr>
          </thead>
          <tbody>
            {(docs.data ?? []).map((d) => (
              <tr key={d.id}><td>{d.filename}</td><td>{kindName[d.kind] ?? d.kind}</td><td className="num">{fmtSize(d.size_bytes)}</td></tr>
            ))}
            {docs.data?.length === 0 && <tr><td colSpan={3}>No files yet. Upload a bid model, tender PDF or auction history.</td></tr>}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Agents</h2>
        <ul className="agents">
          {(agents.data ?? []).map((a: Agent) => (
            <li key={a.kind} className={a.built ? "" : "agent-todo"}>
              <strong>{a.title}</strong> {a.job}
              {!a.built && <span className="tag">Not built yet</span>}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Recent runs</h2>
        <table>
          <thead>
            <tr><th>Agent</th><th>Status</th><th>What happened</th></tr>
          </thead>
          <tbody>
            {(runs.data ?? []).map((r) => (
              <tr key={r.id}>
                <td>{r.kind}</td>
                <td>
                  <span className={`pill pill-${r.status}`}>{r.status}</span>
                  {r.status === "running" && <span className="bar"><span style={{ width: `${Math.round(r.progress * 100)}%` }} /></span>}
                </td>
                <td className="what">{summarize(r)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="try">
        <h2>Find the breakeven tariff</h2>
        <p>Runs the sample bid model’s own formulas and solves for the tariff that hits your target equity IRR.</p>
        <div className="try-row">
          <label>
            Target equity IRR
            <input value={target} onChange={(e) => setTarget(e.target.value)} inputMode="decimal" aria-describedby="irr-help" />
          </label>
          <button onClick={findBreakeven} disabled={!workbook || seeking}>{seeking ? "Solving" : "Find breakeven"}</button>
        </div>
        <p id="irr-help" className="note">Enter as a fraction: 0.14 means 14%.</p>
        {seek && seek.converged && seek.value !== null && (
          <p className="answer">
            <span className="answer-number">₹{seek.value.toFixed(4)}</span> per kWh gives {(Number(target) * 100).toFixed(1)}% equity IRR
            <span className="note"> ({seek.iterations} recalculations, {(seek.elapsed_ms / 1000).toFixed(1)} s)</span>
          </p>
        )}
        {seek && !seek.converged && <p className="alert">{seek.message}</p>}
        {seekError && <p className="alert">{seekError}</p>}
      </section>

      <footer>
        API reference at <a href="/docs">/docs</a>. One-call self test at <a href="/api/selftest">/api/selftest</a>.
      </footer>
    </main>
  );
}
