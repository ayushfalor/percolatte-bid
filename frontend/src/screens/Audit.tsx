import { type Doc, type Driver, type Finding, api, inr, paise } from "../api";
import { Tornado } from "../charts";
import { useLive } from "../hooks";

type AuditorResult = { findings: Finding[]; drivers: Driver[]; breakeven_as_received: number; corrected_breakeven: number; tender_facts_used: number };

export function Audit({ workbook }: { workbook: Doc }) {
  const run = useLive(() => api.latestRun("auditor", workbook.id), 6000, [workbook.id]);
  const result = (run.data?.result ?? null) as AuditorResult | null;
  if (run.error) return <p className="alert">{run.error}</p>;
  if (!result) return <p className="note">No Auditor run yet. Start one from the Setup screen.</p>;
  const byImpact = [...result.findings].sort((a, b) => Math.abs(b.impact_inr_per_kwh ?? 0) - Math.abs(a.impact_inr_per_kwh ?? 0));
  return (
    <>
      <section className="cards">
        <div className="card"><div className="card-title">As received</div><div className="card-value">{inr(result.breakeven_as_received, 4)}</div><div className="note">price the model needs to earn 14%, as uploaded</div></div>
        <div className="card"><div className="card-title">Corrected</div><div className="card-value">{inr(result.corrected_breakeven, 4)}</div><div className="note">the same price with every certain error fixed, on a copy</div></div>
        <div className="card"><div className="card-title">Findings</div><div className="card-value">{result.findings.length}</div><div className="note">{result.tender_facts_used} tender facts used</div></div>
      </section>
      <section>
        <h2>What is wrong, biggest first</h2>
        <table>
          <thead><tr><th>Severity</th><th>Finding</th><th className="num">Effect on price</th><th>Fix</th></tr></thead>
          <tbody>
            {byImpact.map((f) => (
              <tr key={`${f.id}:${f.where}`}>
                <td><span className={`pill sev-${f.severity}`}>{f.severity}</span></td>
                <td>
                  <b>{f.title}</b> <span className="note">{f.where}</span>
                  <div className="evidence">{f.evidence}</div>
                  {f.assumptions.length > 0 && <div className="note">Rests on {f.assumptions.join(", ")}</div>}
                  {f.clauses.length > 0 && <div className="note">RfS clause {f.clauses.join(", ")}</div>}
                </td>
                <td className="num">{f.impact_inr_per_kwh == null ? "not priced" : paise(f.impact_inr_per_kwh)}</td>
                <td className="what">{f.fix ? f.fix.note || `${Object.keys(f.fix.overrides).length + Object.keys(f.fix.formula_patches).length} cells on a copy` : "none"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Which inputs matter most</h2>
        <p className="help">Each bar moves one input 10% either way and shows where the price the model needs ends up. Hover a bar for the numbers.</p>
        <Tornado drivers={result.drivers} base={result.breakeven_as_received} />
      </section>
    </>
  );
}
