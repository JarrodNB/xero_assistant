/**
 * Purpose: Safe report handoffs, editable chat drafts and internal evidence navigation.
 * Public API:
 * - ExplainReportChange
 * - ReportText
 * - ReportHandoff
 */

/** Prepare a bounded opaque selection without sending a question or browser figures. */
export function ExplainReportChange({ token }: { token?: string | null }) {
  if (!token) return null;
  return <a className="table-link" href="/chat" onClick={() => {
    window.sessionStorage.setItem("ledger-report-draft", JSON.stringify({ token, draft: "Explain this report change. What do the figures show, and what remains unknown?" }));
  }}>Explain this change</a>;
}

/** Convert only application-owned relative report evidence syntax into a working link. */
export function ReportText({ text }: { text: string }) {
  const pattern = /\[View source rows \(refreshes report\)\]\((\/performance\?context=[A-Za-z0-9_.%\-]+)\)/g;
  const parts: React.ReactNode[] = [];
  let previous = 0;
  for (const match of text.matchAll(pattern)) {
    parts.push(text.slice(previous, match.index));
    parts.push(<a key={match.index} className="table-link" href={match[1]}>View source rows (refreshes report)</a>);
    previous = match.index! + match[0].length;
  }
  parts.push(text.slice(previous));
  return <>{parts}</>;
}

/** Render a value-free MCP action using a fixed internal destination. */
export function ReportHandoff({ output }: { output: unknown }) {
  if (!output || typeof output !== "object" || !("action" in output) || output.action !== "open_performance" || !("href" in output) || output.href !== "/performance") return null;
  return <p><a className="table-link" href="/performance">Open Performance</a> to choose dates, then select Explain this change.</p>;
}
