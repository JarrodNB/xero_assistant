/**
 * Purpose: Accessible original report trees with evidence links that reveal their targets.
 * Public API:
 * - ReportSources
 * - EvidenceLink
 */

import { FinancialReport, ReportRow } from "../../../lib/reports";

/** Reveal every closed source ancestor and move keyboard focus to the referenced row. */
function revealSource(key: string) {
  const target = document.getElementById(key);
  if (!target) return;
  for (let parent = target.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") (parent as HTMLDetailsElement).open = true;
  }
  target.focus();
  target.scrollIntoView?.({ block: "nearest" });
}

/** Link a calculation to a public source key, including sources in closed disclosures. */
export function EvidenceLink({ source, children }: { source: string | null; children: React.ReactNode }) {
  return source ? <a className="table-link" href={`#${source}`} onClick={(event) => { event.preventDefault(); revealSource(source); }}>{children}</a> : <>
    <span>{children}</span><span className="report-percentage">Not present in this report</span>
  </>;
}

/** Keep source labels and exact reported values grouped without making subtotals contributors. */
function SourceRows({ rows, currency }: { rows: ReportRow[]; currency: string }) {
  const groups: ReportRow[][] = [];
  for (const row of rows) {
    const preceding = groups[groups.length - 1];
    if (row.kind !== "section" && preceding?.[0].kind !== "section") preceding ? preceding.push(row) : groups.push([row]);
    else groups.push([row]);
  }
  return <>{groups.map((group) => {
    const row = group[0];
    return row.kind === "section" ? <details className="report-section" key={row.key}>
      <summary id={row.key}>{row.label || "Report totals"}</summary>
      <SourceRows rows={row.children} currency={currency} />
      {row.children.length === 0 ? <p className="muted">No rows in this section.</p> : null}
    </details> : <table className="report-source-table" key={row.key}><tbody>
      {group.map((item) => <tr tabIndex={-1} id={item.key} key={item.key} className={item.kind === "summary" ? "report-total" : undefined}>
        <th scope="row">{item.label}</th><td className="money">{item.amount} {currency}</td>
      </tr>)}
    </tbody></table>;
  })}</>;
}

/** Expose each original report independently of the aligned comparison table. */
export function ReportSources({ current, comparison }: { current: FinancialReport; comparison: FinancialReport }) {
  return <section className="report-sources" aria-label="Report source evidence">
    <h2>Source reports</h2>
    {[{ report: current, label: "Current source report" }, { report: comparison, label: "Comparison source report" }].map(({ report, label }) =>
      <details className="panel report-source" key={label}>
        <summary>{label}: {report.date_from} to {report.date_to}</summary>
        {report.status === "empty" ? <p>No report data returned.</p> : <SourceRows rows={report.rows} currency={report.currency} />}
      </details>)}
  </section>;
}
