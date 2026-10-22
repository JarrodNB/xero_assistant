# Performance page

Read-only accounting reports through the shared API helper. Native disclosures expose source rows and exact decimal strings. Never calculate financial amounts in the browser or invent empty totals. Cancel or ignore stale requests when selections change. Follow frontend purpose/public API headers and function descriptions.

`page.tsx` owns applied comparison selections and separate draft dates. Report responses must not overwrite newer date edits. `ReportSources.tsx` owns original report trees and source links: open all closed ancestor disclosures and focus the target row. A missing account source still displays its validated zero amount and explains absence. Use report-prefixed source keys; never assume an indexed movement remains the same account after refetching. Percentage limitation text is visible, not hover-only. Native date/select controls and scrollable tables preserve keyboard and narrow-screen use.

`BalanceSheetExplorer.tsx` uses distinct as-of dates and position changes, not period ranges or profit contributions. The page's native tab buttons implement roving focus and arrow/Home/End keys. Unmounting an explorer cancels/ignores its late responses; switching reports cannot mix their results. Source disclosures accept either typed report and label positions with “As at”.

`ExplanationSource.tsx` handles signed evidence navigation: refetch the same account identity before showing fresh rows, metadata and source links. Ignore/abort late responses. Expired/changed/deleted selection requires reopening Performance. ExplainReportChange links on overview/top movements prepare an editable session-storage draft without submitting it. Account selectors are opaque server-signed contexts, never the request-local movement key or any browser amount.
