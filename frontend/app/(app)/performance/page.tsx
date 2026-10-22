/**
 * Purpose: Read-only, source-backed accounting performance workspace.
 * Public API:
 * - PerformancePage
 */
"use client";

import { useEffect, useState } from "react";
import { ApiRequestError, apiRequest } from "../../../lib/api";
import { FinancialReport, ReportRow } from "../../../lib/reports";

/** Keep source labels, subtotals and exact amount strings in their reported sections. */
function SourceRows({ rows, currency }: { rows: ReportRow[]; currency: string }) {
  const groups: ReportRow[][] = [];
  for (const row of rows) {
    const preceding = groups[groups.length - 1];
    if (row.kind !== "section" && preceding?.[0].kind !== "section") preceding ? preceding.push(row) : groups.push([row]);
    else groups.push([row]);
  }
  return <>{groups.map((group) => {
    const row = group[0];
    return row.kind === "section" ? (
      <details className="report-section" key={row.key} open>
        <summary id={row.key}>{row.label || "Report totals"}</summary>
        <SourceRows rows={row.children} currency={currency} />
        {row.children.length === 0 ? <p className="muted">No rows in this section.</p> : null}
      </details>
    ) : (
      <table className="report-source-table" key={row.key}>
        <tbody>{group.map((item) => <tr id={item.key} key={item.key} className={item.kind === "summary" ? "report-total" : undefined}>
          <th scope="row"><a className="table-link" href={`#${item.key}`} aria-label={`Source row: ${item.label}`}>{item.label}</a></th>
          <td className="money">{item.amount} {currency}</td>
        </tr>)}</tbody>
      </table>
    );
  })}</>;
}

/** Show a validated report and recover explicitly from disabled or missing report access. */
export default function PerformancePage() {
  const [report, setReport] = useState<FinancialReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(null);
    setReport(null);
    /** Retrieve the organisation's last completed month without trusting the browser timezone. */
    async function load() {
      try {
        const result = await apiRequest<FinancialReport>("/api/backend/reports/profit-and-loss", { signal: controller.signal });
        if (active) setReport(result);
      } catch (caught) {
        if (active) setError(caught instanceof ApiRequestError ? caught : new ApiRequestError("Report could not be loaded", "No validated figures are available.", "Try again later."));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; controller.abort(); };
  }, [refresh]);

  return <section className="performance-page">
    <div className="page-header"><h1>Performance</h1>
      <button type="button" className="secondary" disabled={loading} onClick={() => setRefresh((value) => value + 1)}>Refresh report</button>
    </div>
    <h2>Profit and loss</h2>
    <p className="muted">Income, costs, and profit for the last completed month. Expand a section to inspect its source rows.</p>
    {loading ? <p role="status">Loading the report from Xero…</p> : null}
    {error ? <div className="report-error" role="alert">
      <h3>{error.message}</h3><p>{error.why}</p><p>{error.nextStep}</p>
      {error.statusCode === 403 ? <a className="primary" href="/api/xero/start">Reconnect Xero for reports</a> : null}
    </div> : null}
    {report ? <>
      <dl className="report-metadata">
        <div><dt>Period</dt><dd>{report.date_from} to {report.date_to}</dd></div>
        <div><dt>Basis and currency</dt><dd>Accrual · {report.currency}</dd></div>
        <div><dt>Organisation timezone</dt><dd>{report.timezone}</dd></div>
        <div><dt>Retrieved</dt><dd><time dateTime={report.retrieved_at}>{report.retrieved_at}</time></dd></div>
      </dl>
      {report.status === "empty" ? <p role="status">Xero returned no report data for this period. No profit amount has been inferred.</p> : (
        <div className="panel report-source" aria-label="Profit and loss source rows"><SourceRows rows={report.rows} currency={report.currency} /></div>
      )}
    </> : null}
  </section>;
}
