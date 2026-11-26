import { type Doc, type Finding, type TenderResult, api, paise } from "../api";
import { useLive } from "../hooks";

export function Tender({ tender, workbook }: { tender: Doc | undefined; workbook: Doc | undefined }) {
  const run = useLive(() => (tender ? api.latestRun("reader", tender.id) : Promise.resolve(null)), 10000, [tender?.id]);
  const audit = useLive(() => (workbook ? api.latestRun("auditor", workbook.id) : Promise.resolve(null)), 10000, [workbook?.id]);
  const result = (run.data?.result ?? null) as TenderResult | null;
  const mismatches = (((audit.data?.result ?? {}) as { findings?: Finding[] }).findings ?? []).filter((f) => f.id === "tender_mismatch");
  if (!tender) return <p className="note">Upload the RfS to see its facts.</p>;
  if (!result?.facts) return <p className="note">The Reader has not extracted this tender yet, or its run predates extraction. Start a reader run from Setup.</p>;
  return (
    <>
      <p className="note">{result.pages} pages · {result.facts.length} facts, {result.verified} verified on their page by code · sources {Object.entries(result.sources ?? {}).map(([k, v]) => `${k} ${v}`).join(", ")}</p>
      <section>
        <h2>Unusual clauses</h2>
        <div className="cards">
          {result.unusual_clauses.map((c) => (
            <div key={c.field} className="card">
              <div className="card-title">{c.field.replace(/_/g, " ")} <Badge ok={c.verified} /></div>
              <div className="note">clause {c.clause}, page {c.pdf_page}</div>
              <blockquote>{c.quote}</blockquote>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2>Where the model disagrees with the tender</h2>
        <table>
          <tbody>
            {mismatches.map((f) => (
              <tr key={f.where}><td><b>{f.title}</b><div className="evidence">{f.evidence}</div></td><td className="num">{f.impact_inr_per_kwh == null ? "" : paise(f.impact_inr_per_kwh)}</td></tr>
            ))}
            {mismatches.length === 0 && <tr><td className="note">None found, or the Auditor has not run.</td></tr>}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Every binding fact</h2>
        <table>
          <thead><tr><th>Fact</th><th className="num">Value</th><th>Clause</th><th>Quote</th></tr></thead>
          <tbody>
            {result.facts.map((f) => (
              <tr key={f.field}>
                <td>{f.field.replace(/_/g, " ")} <Badge ok={f.verified} /></td>
                <td className="num">{String(f.value)} <span className="note">{f.unit}</span></td>
                <td>{f.clause} <span className="note">p.{f.pdf_page}</span></td>
                <td className="what">{f.quote}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function Badge({ ok }: { ok: boolean }) {
  return <span className={`tag ${ok ? "tag-ok" : "tag-amber"}`}>{ok ? "verified" : "unverified"}</span>;
}
