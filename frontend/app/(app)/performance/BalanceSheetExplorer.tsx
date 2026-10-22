/**
 * Purpose: Compare validated balance-sheet positions with distinct as-of controls.
 * Public API:
 * - BalanceSheetExplorer
 */
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest } from "../../../lib/api";
import { BalanceSheetComparison } from "../../../lib/reports";
import { ExplainReportChange } from "../../../components/ReportChat";
import { EvidenceLink, ReportSources } from "./ReportSources";

/** Inspect position changes without suggesting they are profit or cash-flow movements. */
export function BalanceSheetExplorer() {
  const [report, setReport] = useState<BalanceSheetComparison | null>(null);
  const [dates, setDates] = useState({ current: "", comparison: "" });
  const [preset, setPreset] = useState("previous_month");
  const [selection, setSelection] = useState({ query: "", revision: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [dateError, setDateError] = useState("");
  const draftRevision = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const draft = draftRevision.current;
    let active = true;
    setLoading(true); setError(null); setReport(null);
    /** Resolve dates on the server and ignore a superseded request or a newer draft edit. */
    async function load() {
      try {
        const result = await apiRequest<BalanceSheetComparison>("/api/backend/reports/balance-sheet/comparison" + selection.query, { signal: controller.signal });
        if (active) {
          setReport(result);
          if (draftRevision.current === draft) setDates({ current: result.current.as_of, comparison: result.comparison.as_of });
        }
      } catch (caught) {
        if (active) setError(caught instanceof ApiRequestError ? caught : new ApiRequestError("Report could not be loaded", "No validated positions are available.", "Try again later."));
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; controller.abort(); };
  }, [selection]);

  /** Update only the draft; applied figures keep their own explicit source dates. */
  function setDate(key: "current" | "comparison", value: string) {
    draftRevision.current += 1;
    setDates((current) => ({ ...current, [key]: value }));
  }

  /** Apply explicit point-in-time choices without passing P&L date-range arguments. */
  function applyDates(event: FormEvent) {
    event.preventDefault();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dates.current) || (preset === "custom" && (!/^\d{4}-\d{2}-\d{2}$/.test(dates.comparison) || dates.current === dates.comparison))) {
      setDateError("Choose distinct, complete as-of dates."); return;
    }
    setDateError("");
    const query = new URLSearchParams({ as_of: dates.current, preset });
    if (preset === "custom") query.set("comparison_as_of", dates.comparison);
    setSelection((current) => ({ query: "?" + query, revision: current.revision + 1 }));
  }

  const currency = report?.current.currency || "";
  return <section aria-labelledby="balance-sheet-heading">
    <div className="page-header"><h2 id="balance-sheet-heading">Balance sheet</h2>
      <button className="secondary" type="button" disabled={loading} onClick={() => setSelection((current) => ({ ...current, revision: current.revision + 1 }))}>Refresh report</button>
    </div>
    <p className="muted">Compare assets, liabilities, and equity at two dates. Position changes are not profit contributions or cash flows.</p>
    <form className="report-filters" onSubmit={applyDates}>
      <label>Current as-of date<input type="date" required value={dates.current} onChange={(event) => setDate("current", event.target.value)} /></label>
      <label>Compare with<select value={preset} onChange={(event) => setPreset(event.target.value)}>
        <option value="previous_month">Previous month</option><option value="previous_year">Previous year</option><option value="custom">Custom date</option>
      </select></label>
      {preset === "custom" ? <label>Comparison as-of date<input type="date" required value={dates.comparison} onChange={(event) => setDate("comparison", event.target.value)} /></label> : null}
      <button className="primary" type="submit">Apply comparison</button>
      <p className="muted report-filter-note">Defaults compare the last two month ends in organisation time.</p>
      {dateError ? <p role="alert">{dateError}</p> : null}
    </form>
    {loading ? <p role="status">Loading reports from Xero…</p> : null}
    {error ? <div className="report-error" role="alert"><h3>{error.message}</h3><p>{error.why}</p><p>{error.nextStep}</p>
      {error.statusCode === 403 ? <a className="primary" href="/api/xero/start">Reconnect Xero for reports</a> : null}
    </div> : null}
    {report ? <>
      <dl className="report-metadata">
        <div><dt>Current position</dt><dd>As at {report.current.as_of}</dd></div><div><dt>Comparison position</dt><dd>As at {report.comparison.as_of}</dd></div>
        <div><dt>Basis and currency</dt><dd>Accrual · {currency}</dd></div><div><dt>Organisation timezone</dt><dd>{report.current.timezone}</dd></div>
        <div><dt>Retrieved</dt><dd>Current: <time dateTime={report.current.retrieved_at}>{report.current.retrieved_at}</time><br />Comparison: <time dateTime={report.comparison.retrieved_at}>{report.comparison.retrieved_at}</time></dd></div>
      </dl>
      {report.warnings.map((warning) => <p className="report-warning" key={warning}>{warning}</p>)}
      {report.status === "empty" ? <p role="status">Xero returned no report data for at least one date. No position change has been inferred.</p> : <>
        <div className="report-table-scroll"><table className="report-comparison-table" aria-label="Balance sheet comparison">
          <thead><tr><th scope="col">Measure</th><th scope="col">Current</th><th scope="col">Comparison</th><th scope="col">Change</th></tr></thead>
          <tbody>{Object.entries(report.metrics).map(([name, amount]) => <tr key={name}><th scope="row">{name === "net_assets" ? "Net assets" : name[0].toUpperCase() + name.slice(1)}</th>
            <td className="money">{amount.current} {currency}</td><td className="money">{amount.comparison} {currency}</td><td className="money">{amount.change} {currency}</td>
          </tr>)}</tbody>
        </table></div>
        <h2>Largest position changes</h2>
        <p><ExplainReportChange token={report.explanation_context} /></p>
        <ol className="report-contributors">{report.top_movements.map((row) => <li key={row.key}><EvidenceLink source={row.current_source || row.comparison_source}>{row.label}</EvidenceLink>: <strong>{row.change} {currency}</strong> ({row.category}) <ExplainReportChange token={row.explanation_context} /></li>)}</ol>
        {report.top_movements.length === 0 ? <p>No changing account positions in these reports.</p> : null}
        <h2>Account positions</h2>
        <div className="report-table-scroll"><table className="report-comparison-table" aria-label="Account positions">
          <thead><tr><th scope="col">Account and section</th><th scope="col">Current</th><th scope="col">Comparison</th><th scope="col">Position change</th></tr></thead>
          <tbody>{report.movements.map((row) => <tr key={row.key}><th scope="row">{row.label} <ExplainReportChange token={row.explanation_context} /><span className="report-percentage">{row.section} · {row.category}</span>{row.previous_label ? <span className="report-percentage">Previously: {row.previous_label}</span> : null}</th>
            <td className="money"><EvidenceLink source={row.current_source}>{row.current} {currency}</EvidenceLink></td><td className="money"><EvidenceLink source={row.comparison_source}>{row.comparison} {currency}</EvidenceLink></td>
            <td className="money">{row.change} {currency}<span className="report-percentage">{row.percentage_change === null ? row.percentage_note : row.percentage_change + "%"}</span></td>
          </tr>)}</tbody>
        </table></div>
      </>}
      <ReportSources current={report.current} comparison={report.comparison} />
    </> : null}
  </section>;
}
