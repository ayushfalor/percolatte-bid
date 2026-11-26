import { useState } from "react";
import { type ChatReply, api } from "./api";

type Turn = { who: "you" | "copilot"; text: string; reply?: ChatReply };

export function Copilot({ workbookId, open, onClose }: { workbookId?: string; open: boolean; onClose: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const message = text.trim();
    if (!message) return;
    setText("");
    setTurns((t) => [...t, { who: "you", text: message }]);
    setBusy(true);
    try {
      const reply = await api.chat(message, workbookId);
      setTurns((t) => [...t, { who: "copilot", text: reply.answer, reply }]);
    } catch (e) {
      setTurns((t) => [...t, { who: "copilot", text: (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  return (
    <aside className="drawer" aria-label="Copilot">
      <div className="section-head">
        <h2>Copilot</h2>
        <button className="ghost" onClick={onClose}>Close</button>
      </div>
      <p className="note">Ask in plain words: a what-if ("what if CUF is 30%?"), a price ("should we bid at 2.40?"), or what is wrong with the model. Every number in an answer comes from the app’s own tools, never from the model’s imagination.</p>
      <div className="turns">
        {turns.map((t, i) => (
          <div key={i} className={`turn turn-${t.who}`}>
            <p>{t.text}</p>
            {t.reply?.scenario_id && (
              <p className="note">
                Scenario saved. <a href="#/war-room">Open the War Room</a>
                {t.reply.run_id && <> · engine run {t.reply.run_id.slice(0, 8)}</>}
              </p>
            )}
            {t.reply && t.reply.grounded.length > 0 && <p className="note">numbers checked against: {t.reply.grounded.slice(0, 6).join(", ")}</p>}
          </div>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="What if the interest rate rises by 50 bp?" aria-label="Ask the Copilot" />
        <button disabled={busy}>{busy ? "Thinking" : "Ask"}</button>
      </form>
    </aside>
  );
}
