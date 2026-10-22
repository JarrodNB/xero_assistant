/**
 * Purpose: Compare source-backed accounting performance with explicit dates and evidence.
 * Public API:
 * - PerformancePage
 */
"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest } from "../../../lib/api";
import { AmountComparison, ReportComparison } from "../../../lib/reports";
import { EvidenceLink, ReportSources } from "./ReportSources";
import { BalanceSheetExplorer } from "./BalanceSheetExplorer";

type Preset = "previous_period" | "previous_year" | "custom";
type Dates = { from: string; to: string; comparisonFrom: string; comparisonTo: string };
const EMPTY_DATES: Dates = { from: "", to: "", comparisonFrom: "", comparisonTo: "" };

/** Render monetary changes without converting precise decimal strings to browser numbers. */
function Change({ amount, currency }: { amount: AmountComparison; currency: string }) {
  return <>{amount.change} {currency}<span className="report-percentage">
    {amount.percentage_change === null ? amount.percentage_note || "Percentage unavailable" : amount.percentage_change + "%"}
  </span></>;
}

/** Inspect comparative financial figures and their source rows without model or write calls. */
function ProfitAndLossExplorer() {
  const [report, setReport] = useState<ReportComparison | null>(null);
  const [dates, setDates] = useState<Dates>(EMPTY_DATES);
  const [preset, setPreset] = useState<Preset>("previous_period");
  const [selection, setSelection] = useState({ query: "", revision: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiRequestError | null>(null);
  const [dateError, setDateError] = useState("");
  const draftRevision = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestedDraftRevision = draftRevision.current;
    let active = true;
    setLoading(true); setError(null); setReport(null);
    /** Resolve defaults on the server and ignore responses from superseded selections. */
    async function load() {
      try {
        const result = await apiRequest<ReportComparison>("/api/backend/reports/profit-and-loss/comparison" + selection.query, { signal: controller.signal });
        if (active) {
          setReport(result);
          if (draftRevision.current === requestedDraftRevision) {
            setDates({ from: result.current.date_from, to: result.current.date_to,
              comparisonFrom: result.comparison.date_from, comparisonTo: result.comparison.date_to });
          }
        }
      } catch (caught) {
        if (active) setError(caught instanceof ApiRequestError ? caught : new ApiRequestError("Report could not be loaded", "No validated figures are available.", "Try again later."));
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; controller.abort(); };
  }, [selection]);

  /** Apply complete ranges; the server validates future dates using organisation time. */
  function applyDates(event: FormEvent) {
    event.preventDefault();
    const required = preset === "custom" ? Object.values(dates) : [dates.from, dates.to];
    if (required.some((value) => !/^\d{4}-\d{2}-\d{2}$/.test(value)) || dates.from > dates.to ||
        (preset === "custom" && dates.comparisonFrom > dates.comparisonTo)) {
      setDateError("Choose complete date ranges with each start on or before its end."); return;
    }
    setDateError("");
    const query = new URLSearchParams({ date_from: dates.from, date_to: dates.to, preset });
    if (preset === "custom") { query.set("comparison_from", dates.comparisonFrom); query.set("comparison_to", dates.comparisonTo); }
    setSelection((current) => ({ query: "?" + query, revision: current.revision + 1 }));
  }

  /** Update one draft date without mislabelling the displayed report as already refreshed. */
  function setDate(key: keyof Dates, value: string) {
    draftRevision.current += 1;
    setDates((current) => ({ ...current, [key]: value }));
  }

  const currency = report?.current.currency || "";
  return <section aria-labelledby="profit-loss-heading">
    <div className="page-header"><h2 id="profit-loss-heading">Profit and loss</h2>
      <button type="button" className="secondary" disabled={loading} onClick={() => setSelection((current) => ({ ...current, revision: current.revision + 1 }))}>Refresh report</button>
    </div>
    <p className="muted">Compare income, costs, and profit. Changes describe reported amounts; their business causes require further evidence.</p>
    <form className="report-filters" onSubmit={applyDates}>
      <label>Current period start<input type="date" required value={dates.from} onChange={(event) => setDate("from", event.target.value)} /></label>
      <label>Current period end<input type="date" required value={dates.to} onChange={(event) => setDate("to", event.target.value)} /></label>
      <label>Compare with<select value={preset} onChange={(event) => setPreset(event.target.value as Preset)}>
        <option value="previous_period">Previous period</option><option value="previous_year">Previous year</option><option value="custom">Custom dates</option>
      </select></label>
      {preset === "custom" ? <>
        <label>Comparison period start<input type="date" required value={dates.comparisonFrom} onChange={(event) => setDate("comparisonFrom", event.target.value)} /></label>
        <label>Comparison period end<input type="date" required value={dates.comparisonTo} onChange={(event) => setDate("comparisonTo", event.target.value)} /></label>
      </> : null}
      <button className="primary" type="submit">Apply comparison</button>
      <p className="muted report-filter-note">Apply dates to update the report. Defaults use the last two completed months in organisation time.</p>
      {dateError ? <p role="alert">{dateError}</p> : null}
    </form>
    {loading ? <p role="status">Loading reports from Xero…</p> : null}
    {error ? <div className="report-error" role="alert">
      <h3>{error.message}</h3><p>{error.why}</p><p>{error.nextStep}</p>
      {error.statusCode === 403 ? <a className="primary" href="/api/xero/start">Reconnect Xero for reports</a> : null}
    </div> : null}
    {report ? <>
      <dl className="report-metadata">
        <div><dt>Current period</dt><dd>{report.current.date_from} to {report.current.date_to}</dd></div>
        <div><dt>Comparison period</dt><dd>{report.comparison.date_from} to {report.comparison.date_to}</dd></div>
        <div><dt>Basis and currency</dt><dd>Accrual · {currency}</dd></div>
        <div><dt>Organisation timezone</dt><dd>{report.current.timezone}</dd></div>
        <div><dt>Retrieved</dt><dd>Current: <time dateTime={report.current.retrieved_at}>{report.current.retrieved_at}</time><br />Comparison: <time dateTime={report.comparison.retrieved_at}>{report.comparison.retrieved_at}</time></dd></div>
      </dl>
      {report.warnings.map((warning) => <p className="report-warning" key={warning}>{warning}</p>)}
      {report.status === "empty" ? <p role="status">Xero returned no report data for at least one period. No profit change has been inferred.</p> : <>
        <div className="report-table-scroll"><table className="report-comparison-table" aria-label="Profit and loss comparison">
          <thead><tr><th scope="col">Measure</th><th scope="col">Current</th><th scope="col">Comparison</th><th scope="col">Change</th></tr></thead>
          <tbody>{Object.entries(report.metrics).map(([name, amount]) => <tr key={name}>
            <th scope="row">{name === "net_profit" ? "Net profit" : name === "income" ? "Income" : "Expenses"}</th>
            <td className="money">{amount.current} {currency}</td><td className="money">{amount.comparison} {currency}</td><td className="money"><Change amount={amount} currency={currency} /></td>
          </tr>)}</tbody>
        </table></div>
        <h2>Largest profit contributors</h2>
        <p>Account movements contributing most to the profit change. Increased expenses reduce profit; expense credits can increase it.</p>
        <ol className="report-contributors">{report.top_movements.map((movement) => <li key={movement.key}>
          <EvidenceLink source={movement.current_source || movement.comparison_source}>{movement.label}</EvidenceLink>: <strong>{movement.contribution} {currency}</strong>
        </li>)}</ol>
        {report.top_movements.length === 0 ? <p>No changing accounts in these reports.</p> : null}
        <p>Other movements and rounding remainder: {report.other_movements} {currency}</p>
        <h2>Account movements</h2>
        <div className="report-table-scroll"><table className="report-comparison-table" aria-label="Account movements">
          <thead><tr><th scope="col">Account</th><th scope="col">Current</th><th scope="col">Comparison</th><th scope="col">Amount change</th><th scope="col">Profit contribution</th></tr></thead>
          <tbody>{report.movements.map((movement) => <tr key={movement.key}>
            <th scope="row">{movement.label}{movement.previous_label ? <span className="report-percentage">Previously: {movement.previous_label}</span> : null}</th>
            <td className="money"><EvidenceLink source={movement.current_source}>{movement.current} {currency}</EvidenceLink></td>
            <td className="money"><EvidenceLink source={movement.comparison_source}>{movement.comparison} {currency}</EvidenceLink></td>
            <td className="money"><Change amount={movement} currency={currency} /></td><td className="money">{movement.contribution} {currency}</td>
          </tr>)}</tbody>
        </table></div>
      </>}
      <ReportSources current={report.current} comparison={report.comparison} />
    </> : null}
  </section>;
}

/** Switch between activity over ranges and positions at dates without mixing their state. */
export default function PerformancePage() {
  const [tab, setTab] = useState<"profit_and_loss" | "balance_sheet">("profit_and_loss");
  /** Apply roving focus and standard arrow/Home/End navigation to the native tab buttons. */
  function navigateTabs(event: KeyboardEvent<HTMLDivElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? "profit_and_loss" : event.key === "End" ? "balance_sheet" : tab === "profit_and_loss" ? "balance_sheet" : "profit_and_loss";
    setTab(next);
    document.getElementById(next === "profit_and_loss" ? "profit-loss-tab" : "balance-sheet-tab")?.focus();
  }
  return <section className="performance-page"><h1>Performance</h1>
    <div className="report-tabs" role="tablist" aria-label="Financial reports" onKeyDown={navigateTabs}>
      <button type="button" id="profit-loss-tab" role="tab" tabIndex={tab === "profit_and_loss" ? 0 : -1} aria-selected={tab === "profit_and_loss"} aria-controls="report-panel" className={tab === "profit_and_loss" ? "primary" : "secondary"} onClick={() => setTab("profit_and_loss")}>Profit and loss</button>
      <button type="button" id="balance-sheet-tab" role="tab" tabIndex={tab === "balance_sheet" ? 0 : -1} aria-selected={tab === "balance_sheet"} aria-controls="report-panel" className={tab === "balance_sheet" ? "primary" : "secondary"} onClick={() => setTab("balance_sheet")}>Balance sheet</button>
    </div>
    <div id="report-panel" role="tabpanel" aria-labelledby={tab === "profit_and_loss" ? "profit-loss-tab" : "balance-sheet-tab"}>
      {tab === "profit_and_loss" ? <ProfitAndLossExplorer /> : <BalanceSheetExplorer />}
    </div>
  </section>;
}
