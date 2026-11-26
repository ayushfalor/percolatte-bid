import { type Doc, type Finding, type TenderFact, type TenderResult, api, paise } from "../api";
import { useLive } from "../hooks";

export function Tender({ tender, workbook }: { tender: Doc | undefined; workbook: Doc | undefined }) {
  const run = useLive(() => (tender ? api.latestRun("reader", tender.id) : Promise.resolve(null)), 10000, [tender?.id]);
  const plain = useLive(() => (tender ? api.tenderPlain() : Promise.resolve(null)), 15000, [tender?.id]);
  const audit = useLive(() => (workbook ? api.latestRun("auditor", workbook.id) : Promise.resolve(null)), 10000, [workbook?.id]);
  const result = (run.data?.result ?? null) as TenderResult | null;
  const mismatches = (((audit.data?.result ?? {}) as { findings?: Finding[] }).findings ?? []).filter((f) => f.id === "tender_mismatch");
  if (!tender) return <p className="note">Upload the tender (the RfS PDF) on <a href="#/setup">Setup</a> to see it here.</p>;
  const sections = plain.data?.sections ?? [];
  const unusual: TenderFact[] = plain.data?.unusual ?? result?.unusual_clauses ?? [];
  if (!result?.facts && sections.length === 0) return <p className="note">The tender is still being read. This fills in when the Reader finishes.</p>;
  return (
    <>
      <section>
        <h2>In plain words</h2>
        <p className="note">Every number below is one the Reader found on a page of the RfS and checked there; the clause is beside it.</p>
        {sections.map((s) => (
          <div key={s.heading} className="plain-item"><h3>{s.heading}</h3><p>{s.text}</p></div>
        ))}
      </section>

      <section>
        <h2>What is different about this tender</h2>
        <p className="note">Clauses a normal solar tender does not have, and what each one means for our bid.</p>
        <div className="cards">
          {unusual.map((c) => (
            <div key={c.field} className="card meaning">
              <h3>{c.meaning?.title ?? c.field.replace(/_/g, " ")} <Badge ok={c.verified} /></h3>
              <p><b>What it says.</b> {c.meaning?.what ?? "See the quote below."}</p>
              <p><b>For our bid.</b> {c.meaning?.for_us ?? "Read it with the legal team before bidding."}</p>
              <details>
                <summary className="note">{c.clause ? `Clause ${c.clause}, page ${c.pdf_page}` : `Page ${c.pdf_page}`}: the words on the page</summary>
                <blockquote>{c.quote}</blockquote>
              </details>
            </div>
          ))}
          {unusual.length === 0 && <p className="note">None flagged.</p>}
        </div>
      </section>

      <section>
        <h2>Where the bid model disagrees with the tender</h2>
        <table>
          <tbody>
            {mismatches.map((f) => (
              <tr key={f.where}><td><b>{f.title}</b><div className="evidence">{f.evidence}</div></td><td className="num">{f.impact_inr_per_kwh == null ? "" : paise(f.impact_inr_per_kwh)}</td></tr>
            ))}
            {mismatches.length === 0 && <tr><td className="note">None found, or the Auditor has not run.</td></tr>}
          </tbody>
        </table>
      </section>

      {result?.facts && (
        <details className="engineer">
          <summary>Every fact the Reader pulled, with its quote ({result.facts.length} facts, {result.verified} checked on their page, {result.pages} pages)</summary>
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
        </details>
      )}
    </>
  );
}

function Badge({ ok }: { ok: boolean }) {
  return <span className={`tag ${ok ? "tag-ok" : "tag-amber"}`} title={ok ? "The quote was found on the cited page by code" : "The quote could not be matched on the page"}>{ok ? "checked" : "unchecked"}</span>;
}
