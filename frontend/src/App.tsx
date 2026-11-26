import { useCallback, useState } from "react";
import { type Agent, type Doc, type EngineResult, type Health, type Run, api } from "./api";
import { Copilot } from "./Copilot";
import { useLive, useScreen } from "./hooks";
import { Assumptions } from "./screens/Assumptions";
import { Audit } from "./screens/Audit";
import { Brief } from "./screens/Brief";
import { Live } from "./screens/Live";
import { Rivals } from "./screens/Rivals";
import { Setup } from "./screens/Setup";
import { Tender } from "./screens/Tender";
import { WarRoom } from "./screens/WarRoom";
import { progressFor, technologyOf } from "./status";

// The screens in the order a new user meets them. Every tab says what it is for and where its
// numbers come from; the same line sits under the screen title.
export const SCREENS: { key: string; title: string; hint: string }[] = [
  { key: "setup", title: "Setup", hint: "Start here. Load your files, wait for the four ticks, then read the Brief." },
  { key: "brief", title: "Bid Brief", hint: "The three numbers to act on, with the reason for each. From the Auditor, the Rival model and the Engine." },
  { key: "war-room", title: "War Room", hint: "Chance of winning against profit at every price. Change an input and watch it move." },
  { key: "live", title: "Live Auction", hint: "During the e-RA: type in what the portal shows and get the next move." },
  { key: "audit", title: "Audit", hint: "What is wrong in the bid model, priced in paise, with a fix for each. From the Auditor." },
  { key: "tender", title: "Tender", hint: "The tender in plain words, and the clauses a normal solar tender does not have. From the RfS PDF." },
  { key: "rivals", title: "Rivals", hint: "Who bids, how often, and where each one stops. From 13 past auctions." },
];
const ASSUMPTIONS = { key: "assumptions", title: "Assumptions", hint: "Every number the app assumes, with its source and where to change it." };

export default function App() {
  const screen = useScreen("setup");
  const health = useLive(useCallback(api.health, []), 4000);
  const docs = useLive(useCallback(api.documents, []), 6000);
  const agents = useLive(useCallback(api.agents, []), 60000);
  const runs = useLive(useCallback(() => api.runs("limit=60"), []), 5000);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);

  const files: Doc[] = docs.data ?? [];
  const workbooks = files.filter((d) => d.kind === "workbook");
  // The sample until you upload your own; an upload selects the new file.
  const workbook = workbooks.find((d) => d.id === chosen) ?? workbooks[0];
  const tender = files.find((d) => d.kind === "tender");
  const current = SCREENS.find((s) => s.key === screen) ?? ASSUMPTIONS;
  const runList = (runs.data ?? []) as Run[];
  const progress = progressFor(runList, workbook);
  const engine = runList.find((r) => r.kind === "engine" && r.status === "succeeded" && r.document_id === workbook?.id && !r.params?.scenario_id);
  const ourMw = (engine?.result as EngineResult | undefined)?.our_mw;

  return (
    <main className={copilotOpen ? "with-drawer" : ""}>
      <header>
        <div className="section-head">
          <h1>Bid Workbench</h1>
          {workbooks.length > 1 && (
            <label className="picker" title="Which bid model the screens show">
              Project
              <select value={workbook?.id ?? ""} onChange={(e) => setChosen(e.target.value)} aria-label="Which bid model to show">
                {workbooks.map((d) => (
                  <option key={d.id} value={d.id}>{d.filename}{d.meta?.sample ? " (sample)" : ""}</option>
                ))}
              </select>
            </label>
          )}
          <button className="ghost" onClick={() => setCopilotOpen((o) => !o)} title="Ask a question or a what-if in plain words">{copilotOpen ? "Hide Copilot" : "Ask the Copilot"}</button>
        </div>
        <p className="lede">Reads your bid model, the tender and past auctions. Tells you what to bid, and why.</p>
        <div className="project" aria-label="Project">
          <span className={`dot dot-${progress.tone}`} aria-hidden />
          <b>{technologyOf(workbook)}</b>
          <span>{tender ? "SECI 700 MW C&I-1" : "No tender loaded"}</span>
          {ourMw != null && <span>Our bid {ourMw} MW</span>}
          <span>{workbook ? `${workbook.filename}${workbook.meta?.sample ? " (sample project)" : ""}` : "No bid model"}</span>
          <span className="project-status">{progress.status}</span>
        </div>
        <nav className="tabs" aria-label="Screens">
          {SCREENS.map((s) => (
            <a key={s.key} href={`#/${s.key}`} className={s.key === screen ? "active" : ""} title={s.hint}>{s.title}</a>
          ))}
        </nav>
      </header>
      {health.error && <p className="alert" role="alert">Can’t reach the app’s API. In a terminal: <code>docker compose ps</code>, then <code>docker compose logs api</code>.</p>}

      <h2 className="screen-title">{current.title}</h2>
      <p className="hint">{current.hint}</p>
      {screen === "setup" && (
        <Setup
          health={health.data as Health | null}
          docs={files}
          workbook={workbook}
          agents={(agents.data ?? []) as Agent[]}
          runs={runList}
          progress={progress}
          onUploaded={(id) => {
            setChosen(id);
            docs.refresh();
          }}
        />
      )}
      {screen === "brief" && (workbook ? <Brief workbook={workbook} docs={files} /> : <NoModel />)}
      {screen === "war-room" && (workbook ? <WarRoom workbook={workbook} /> : <NoModel />)}
      {screen === "live" && (workbook ? <Live workbook={workbook} /> : <NoModel />)}
      {screen === "rivals" && <Rivals />}
      {screen === "audit" && (workbook ? <Audit workbook={workbook} /> : <NoModel />)}
      {screen === "tender" && <Tender tender={tender} workbook={workbook} />}
      {screen === "assumptions" && <Assumptions />}

      <Copilot workbookId={workbook?.id} open={copilotOpen} onClose={() => setCopilotOpen(false)} />
      <footer>
        <a href="#/assumptions">Every assumed number</a> · <a href="/docs">API reference</a> · <a href="/api/selftest">self test</a>
      </footer>
    </main>
  );
}

function NoModel() {
  return <p className="note">No bid model loaded. Upload one on the <a href="#/setup">Setup</a> screen.</p>;
}
