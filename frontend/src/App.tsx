import { useCallback, useState } from "react";
import { type Agent, type Doc, type Health, type Run, api } from "./api";
import { Copilot } from "./Copilot";
import { useLive, useScreen } from "./hooks";
import { Assumptions } from "./screens/Assumptions";
import { Audit } from "./screens/Audit";
import { Brief } from "./screens/Brief";
import { Rivals } from "./screens/Rivals";
import { Setup } from "./screens/Setup";
import { Tender } from "./screens/Tender";
import { WarRoom } from "./screens/WarRoom";

// The screens, in the order a bid manager reads them. Three seconds: the Bid Brief. Thirty seconds:
// the War Room. Three minutes: Audit, Tender, Rivals, Assumptions, each number a click from its source.
export const SCREENS: { key: string; title: string }[] = [
  { key: "brief", title: "Bid Brief" },
  { key: "war-room", title: "War Room" },
  { key: "rivals", title: "Rivals" },
  { key: "audit", title: "Audit" },
  { key: "tender", title: "Tender" },
  { key: "assumptions", title: "Assumptions" },
  { key: "setup", title: "Setup" },
];

export default function App() {
  const screen = useScreen("brief");
  const health = useLive(useCallback(api.health, []), 4000);
  const docs = useLive(useCallback(api.documents, []), 6000);
  const agents = useLive(useCallback(api.agents, []), 60000);
  const runs = useLive(useCallback(() => api.runs("limit=40"), []), 5000);
  const [copilotOpen, setCopilotOpen] = useState(false);

  const files: Doc[] = docs.data ?? [];
  const workbook = files.find((d) => d.kind === "workbook");
  const tender = files.find((d) => d.kind === "tender");
  const title = SCREENS.find((s) => s.key === screen)?.title ?? "Bid Brief";

  return (
    <main className={copilotOpen ? "with-drawer" : ""}>
      <header>
        <div className="section-head">
          <h1>Bid Workbench</h1>
          <button className="ghost" onClick={() => setCopilotOpen((o) => !o)}>{copilotOpen ? "Hide Copilot" : "Ask the Copilot"}</button>
        </div>
        <p className="lede">SECI 700 MW C&amp;I-1. Three numbers to act on, and every one of them a click from its source.</p>
        <nav className="tabs" aria-label="Screens">
          {SCREENS.map((s) => (
            <a key={s.key} href={`#/${s.key}`} className={s.key === screen ? "active" : ""}>{s.title}</a>
          ))}
        </nav>
      </header>
      {health.error && <p className="alert" role="alert">Can’t reach the API. Check <code>docker compose ps</code>, then <code>docker compose logs api</code>.</p>}

      <h2 className="screen-title">{title}</h2>
      {screen === "setup" && <Setup health={health.data as Health | null} docs={files} agents={(agents.data ?? []) as Agent[]} runs={(runs.data ?? []) as Run[]} />}
      {screen === "brief" && (workbook ? <Brief workbook={workbook} docs={files} /> : <NoModel />)}
      {screen === "war-room" && (workbook ? <WarRoom workbook={workbook} /> : <NoModel />)}
      {screen === "rivals" && <Rivals />}
      {screen === "audit" && (workbook ? <Audit workbook={workbook} /> : <NoModel />)}
      {screen === "tender" && <Tender tender={tender} workbook={workbook} />}
      {screen === "assumptions" && <Assumptions />}

      <Copilot workbookId={workbook?.id} open={copilotOpen} onClose={() => setCopilotOpen(false)} />
      <footer>
        API reference at <a href="/docs">/docs</a>. One-call self test at <a href="/api/selftest">/api/selftest</a>.
      </footer>
    </main>
  );
}

function NoModel() {
  return <p className="note">No bid model loaded. Upload one on the <a href="#/setup">Setup</a> screen.</p>;
}
