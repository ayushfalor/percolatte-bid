import { api } from "../api";
import { useLive } from "../hooks";

export function Assumptions() {
  const reg = useLive(() => api.assumptions(), 0);
  if (reg.error) return <p className="alert">{reg.error}</p>;
  if (!reg.data) return <p className="note">Loading the register.</p>;
  return (
    <>
      <p className="note">For the curious: every number the app uses that does not come straight from the tender or the bid model, where it came from and where to change it. {reg.data.count} rows, from ASSUMPTIONS.md in the repo.</p>
      <table>
        <thead><tr><th>ID</th><th>Assumption</th><th>Value</th><th>Source</th><th>Used by</th><th>Change it in</th></tr></thead>
        <tbody>
          {reg.data.rows.map((r) => (
            <tr key={r.id}><td>{r.id}</td><td>{r.assumption}</td><td>{r.value}</td><td>{r.source}</td><td>{r.used_by}</td><td className="what">{r.change_in}</td></tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
