/**
 * Purpose: Refetch signed report evidence without trusting stale positional movement keys.
 * Public API:
 * - ExplanationSource
 */

import { useEffect, useState } from "react";
import { apiRequest } from "../../../lib/api";
import { BalanceSheetComparison, ReportComparison } from "../../../lib/reports";
import { EvidenceLink, ReportSources } from "./ReportSources";
import { ExplainReportChange } from "../../../components/ReportChat";

/** Resolve a signed evidence link and show its current account and original source rows. */
export function ExplanationSource({ token }: { token: string }) {
  const [source, setSource] = useState<{ report: ReportComparison | BalanceSheetComparison; selected_key: string | null } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    apiRequest<{ report: ReportComparison | BalanceSheetComparison; selected_key: string | null }>("/api/backend/reports/explanation-source?context=" + encodeURIComponent(token), { signal: controller.signal })
      .then((value) => { if (active) setSource(value); })
      .catch(() => { if (active) setError("This report selection expired, changed, or is unavailable. Open Performance again and choose the account afresh."); });
    return () => { active = false; controller.abort(); };
  }, [token]);
  if (error) return <p role="alert">{error} <a href="/performance">Open Performance</a></p>;
  if (!source) return <p role="status">Refreshing source evidence…</p>;
  const report = source.report;
  const row = report.movements.find((movement) => movement.key === source.selected_key);
  return <section>
    <h2>Refreshed explanation evidence</h2>
    <p>{report.report_type === "profit_and_loss" ? "Profit and loss" : "Balance sheet"} · Accrual · {report.current.currency} · {report.current.timezone}</p>
    <p>Retrieved: {report.current.retrieved_at} and {report.comparison.retrieved_at}. Figures can change after a refresh.</p>
    {row ? <p>{row.label}: <EvidenceLink source={row.current_source}>{row.current} {report.current.currency}</EvidenceLink> compared with <EvidenceLink source={row.comparison_source}>{row.comparison} {report.current.currency}</EvidenceLink>. Change: {row.change} {report.current.currency}. <ExplainReportChange token={row.explanation_context} /></p> : <ExplainReportChange token={report.explanation_context} />}
    <ReportSources current={report.current} comparison={report.comparison} />
    <p><a href="/performance">Choose another report</a></p>
  </section>;
}
