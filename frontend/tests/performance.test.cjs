/**
 * Purpose: Verify report rendering and recoverable reporting failures.
 * Public API:
 * - Node test runner cases
 */
const assert = require("node:assert/strict");
const { test, afterEach } = require("node:test");
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost" });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
const React = require("react");
const { render, screen, cleanup, fireEvent, act, within } = require("@testing-library/react");
const Page = require("/tmp/ledger-frontend-tests/app/(app)/performance/page.js").default;

/** Comparisons must surface account changes, not only a single report tree. */
test("performance presents comparison controls and account movements", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify(fixture()), { status: 200 });
  render(React.createElement(Page));
  await screen.findByRole("heading", { name: "Account movements" });
  assert.ok(screen.getByLabelText("Compare with"));
});

/** Restore isolated DOM and HTTP state. */
afterEach(() => { cleanup(); delete globalThis.fetch; });

/** Build a synthetic report response without private account identifiers. */
function fixture() {
  const current = { schema_version: "1", report_type: "profit_and_loss", status: "ready", complete: true,
    date_from: "2026-01-01", date_to: "2026-01-31", basis: "accrual", currency: "AUD", timezone: "UTC", retrieved_at: "2026-02-01T00:00:00Z",
    currency_decimal_places: 2,
    rows: [{ key: "current-source-1", kind: "section", label: "Trading Income", amount: null,
      children: [{ key: "current-source-1-1", kind: "account", label: "Consulting", amount: "1000.10", children: [] }] }] };
  const comparison = structuredClone(current);
  comparison.date_from = "2025-12-01"; comparison.date_to = "2025-12-31";
  comparison.rows[0].key = "comparison-source-1";
  comparison.rows[0].children[0].key = "comparison-source-1-1";
  comparison.rows[0].children[0].amount = "500.00";
  const amount = { current: "1000.10", comparison: "500.00", change: "500.10", percentage_change: "100.02", percentage_note: null };
  const movement = { ...amount, key: "movement-1", label: "Consulting", previous_label: null, category: "income", contribution: "500.10", current_source: "current-source-1-1", comparison_source: "comparison-source-1-1" };
  return { schema_version: "1", report_type: "profit_and_loss", status: "ready", complete: true, current, comparison,
    metrics: { income: amount, net_profit: amount }, movements: [movement], top_movements: [movement], other_movements: "0.00", warnings: [] };
}

/** Build a synthetic typed position response for the browser rendering seam. */
function positionFixture() {
  const position = fixture();
  position.report_type = "balance_sheet";
  position.current.report_type = position.comparison.report_type = "balance_sheet";
  position.current.as_of = "2026-02-28"; position.comparison.as_of = "2026-01-31";
  delete position.current.date_from; delete position.current.date_to;
  delete position.comparison.date_from; delete position.comparison.date_to;
  const amount = position.metrics.income;
  position.metrics = { assets: amount, liabilities: amount, equity: amount, net_assets: amount };
  const movement = { ...position.movements[0], category: "assets", section: "Bank", label: "Business Bank" };
  delete movement.contribution;
  position.movements = position.top_movements = [movement];
  return position;
}

/** Keep balance-sheet position semantics distinct from income and profit. */
test("balance-sheet tab compares as-of positions without profit columns", async () => {
  globalThis.fetch = async (url) => new Response(JSON.stringify(String(url).includes("balance-sheet") ? positionFixture() : fixture()), { status: 200 });
  render(React.createElement(Page));
  await screen.findByRole("heading", { name: "Account movements" });
  fireEvent.click(screen.getByRole("tab", { name: "Balance sheet" }));
  await screen.findByRole("table", { name: "Balance sheet comparison" });
  assert.ok(screen.getByLabelText("Current as-of date"));
  assert.ok(screen.getByRole("columnheader", { name: "Position change" }));
  assert.equal(screen.queryByRole("columnheader", { name: "Profit contribution" }), null);
  assert.ok(screen.getAllByText(/2026-02-28/).length);
  assert.ok(screen.getByText("Bank · assets"));
});

/** Report tabs must follow keyboard tab navigation rather than requiring a pointer. */
test("report tabs switch and focus with arrow keys", async () => {
  globalThis.fetch = async (url) => new Response(JSON.stringify(String(url).includes("balance-sheet") ? positionFixture() : fixture()), { status: 200 });
  render(React.createElement(Page));
  await screen.findByRole("heading", { name: "Account movements" });
  const profitTab = screen.getByRole("tab", { name: "Profit and loss" });
  profitTab.focus();
  fireEvent.keyDown(profitTab, { key: "ArrowRight" });
  const balanceTab = screen.getByRole("tab", { name: "Balance sheet" });
  assert.equal(balanceTab.getAttribute("aria-selected"), "true");
  assert.equal(document.activeElement, balanceTab);
  fireEvent.keyDown(balanceTab, { key: "Home" });
  assert.equal(profitTab.getAttribute("aria-selected"), "true");
});

/** Position controls submit point-in-time arguments and stale responses cannot change the active tab. */
test("balance-sheet custom dates and late tab responses stay distinct", async () => {
  const calls = [];
  let finishPosition;
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    if (String(url).includes("preset=custom")) return new Promise((resolve) => { finishPosition = resolve; });
    return new Response(JSON.stringify(String(url).includes("balance-sheet") ? positionFixture() : fixture()), { status: 200 });
  };
  render(React.createElement(Page));
  await screen.findByRole("heading", { name: "Account movements" });
  fireEvent.click(screen.getByRole("tab", { name: "Balance sheet" }));
  await screen.findByRole("table", { name: "Account positions" });
  fireEvent.change(screen.getByLabelText("Compare with"), { target: { value: "custom" } });
  fireEvent.change(screen.getByLabelText("Current as-of date"), { target: { value: "2025-10-31" } });
  fireEvent.change(screen.getByLabelText("Comparison as-of date"), { target: { value: "2025-06-30" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply comparison" }));
  assert.match(calls.at(-1), /as_of=2025-10-31/);
  assert.match(calls.at(-1), /comparison_as_of=2025-06-30/);
  assert.doesNotMatch(calls.at(-1), /date_from|date_to/);
  fireEvent.click(screen.getByRole("tab", { name: "Profit and loss" }));
  await screen.findByRole("table", { name: "Account movements" });
  await act(async () => finishPosition(new Response(JSON.stringify(positionFixture()), { status: 200 })));
  assert.ok(screen.getByRole("table", { name: "Account movements" }));
  assert.equal(screen.queryByRole("table", { name: "Account positions" }), null);
});

/** Display returned dates and exact source amounts in an accessible disclosure. */
test("P&L source rows retain exact values and metadata", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify(fixture()), { status: 200 });
  render(React.createElement(Page));
  await screen.findAllByText("1000.10 AUD");
  assert.ok(screen.getAllByText("Consulting").length);
  assert.ok(screen.getAllByText(/2026-01-01/).length);
  assert.ok(screen.getAllByText(/2026-01-31/).length);
  assert.ok(screen.getByText(/Accrual/));
  assert.ok(screen.getAllByText("Trading Income")[0].closest("summary"));
  assert.ok(document.getElementById("current-source-1-1"));
  const summary = screen.getAllByText("Trading Income")[0];
  fireEvent.click(summary);
  assert.equal(summary.closest("details").open, true);
});

/** An empty report is an absence of source data, not a zero-profit claim. */
test("empty reports do not invent amounts", async () => {
  const empty = fixture();
  empty.status = "empty";
  empty.current.status = "empty"; empty.current.rows = [];
  empty.comparison.status = "empty"; empty.comparison.rows = [];
  globalThis.fetch = async () => new Response(JSON.stringify(empty), { status: 200 });
  render(React.createElement(Page));
  await screen.findByText(/Xero returned no report data/);
  assert.equal(screen.queryByText(/0\.00 AUD/), null);
});

/** Missing report consent is distinct from ordinary connectivity and can be retried. */
test("report permissions show reconnect guidance and refresh recovers", async () => {
  let count = 0;
  globalThis.fetch = async (url) => {
    assert.equal(url, "/api/backend/reports/profit-and-loss/comparison");
    count += 1;
    return count === 1 ? new Response(JSON.stringify({ what: "Report access required", why: "Missing report scope", next_step: "Reconnect Xero." }), { status: 403 })
      : new Response(JSON.stringify(fixture()), { status: 200 });
  };
  render(React.createElement(Page));
  assert.equal((await screen.findByRole("link", { name: "Reconnect Xero for reports" })).getAttribute("href"), "/api/xero/start");
  fireEvent.click(screen.getByRole("button", { name: "Refresh report" }));
  await screen.findAllByText("1000.10 AUD");
  assert.equal(screen.queryByRole("alert"), null);
});

/** Rollout is visibly disabled without presenting a connect action as the remedy. */
test("disabled reporting remains an explicit unavailable state", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ what: "Performance reports are disabled", why: "Not enabled", next_step: "Enable reporting after the demo access check." }), { status: 503 });
  render(React.createElement(Page));
  await screen.findByRole("heading", { name: "Performance reports are disabled" });
  assert.equal(screen.queryByRole("link", { name: "Reconnect Xero for reports" }), null);
  assert.equal(screen.queryByText("1000.10 AUD"), null);
});

/** A report that resolves after navigation cannot populate a newly mounted report view. */
test("late report responses cannot replace current data after remount", async () => {
  let finish;
  let count = 0;
  globalThis.fetch = async () => {
    count += 1;
    if (count === 1) return new Promise((resolve) => { finish = resolve; });
    const newer = fixture();
    newer.current.rows[0].children[0].amount = "2000.20";
    return new Response(JSON.stringify(newer), { status: 200 });
  };
  const first = render(React.createElement(Page));
  first.unmount();
  render(React.createElement(Page));
  await screen.findByText("2000.20 AUD");
  await act(async () => finish(new Response(JSON.stringify(fixture()), { status: 200 })));
  assert.ok(screen.getByText("2000.20 AUD"));
  assert.equal(document.getElementById("current-source-1-1").textContent.includes("1000.10"), false);
});

/** Selecting source evidence must reveal its complete disclosure path and keyboard target. */
test("account evidence opens closed source sections and focuses the exact row", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify(fixture()), { status: 200 });
  render(React.createElement(Page));
  const link = await screen.findByRole("link", { name: "Consulting" });
  const row = document.getElementById("current-source-1-1");
  assert.equal(row.closest("details").open, false);
  fireEvent.click(link);
  for (let parent = row.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === "DETAILS") assert.equal(parent.open, true);
  }
  assert.equal(document.activeElement, row);
});

/** New report defaults cannot discard draft dates typed while the read was pending. */
test("late defaults preserve date edits made while loading", async () => {
  let finish;
  globalThis.fetch = () => new Promise((resolve) => { finish = resolve; });
  render(React.createElement(Page));
  fireEvent.change(screen.getByLabelText("Current period start"), { target: { value: "2025-10-01" } });
  await act(async () => finish(new Response(JSON.stringify(fixture()), { status: 200 })));
  assert.equal(screen.getByLabelText("Current period start").value, "2025-10-01");
});

/** Submitted custom ranges use all four dates and later requests supersede earlier results. */
test("custom comparisons submit typed dates and ignore superseded responses", async () => {
  const calls = [];
  let finishOld;
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (calls.length === 2) return new Promise((resolve) => { finishOld = resolve; });
    const value = fixture();
    if (calls.length === 3) value.current.rows[0].children[0].amount = "3333.33";
    return new Response(JSON.stringify(value), { status: 200 });
  };
  render(React.createElement(Page));
  await screen.findByRole("heading", { name: "Account movements" });
  fireEvent.change(screen.getByLabelText("Compare with"), { target: { value: "custom" } });
  fireEvent.change(screen.getByLabelText("Current period start"), { target: { value: "2025-10-01" } });
  fireEvent.change(screen.getByLabelText("Current period end"), { target: { value: "2025-10-31" } });
  fireEvent.change(screen.getByLabelText("Comparison period start"), { target: { value: "2025-09-01" } });
  fireEvent.change(screen.getByLabelText("Comparison period end"), { target: { value: "2025-09-30" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply comparison" }));
  assert.match(calls[1], /preset=custom/);
  assert.match(calls[1], /comparison_from=2025-09-01/);
  fireEvent.change(screen.getByLabelText("Current period start"), { target: { value: "2025-08-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply comparison" }));
  await screen.findByText("3333.33 AUD");
  await act(async () => finishOld(new Response(JSON.stringify(fixture()), { status: 200 })));
  assert.ok(screen.getByText("3333.33 AUD"));
});

/** Absent account evidence must still expose its validated zero comparison amount. */
test("new accounts show zero baseline and a visible percentage explanation", async () => {
  const value = fixture();
  value.movements[0].comparison = "0.00";
  value.movements[0].comparison_source = null;
  value.movements[0].percentage_change = null;
  value.movements[0].percentage_note = "Percentage change is unavailable because the comparison amount is zero or negative.";
  globalThis.fetch = async () => new Response(JSON.stringify(value), { status: 200 });
  render(React.createElement(Page));
  const table = await screen.findByRole("table", { name: "Account movements" });
  assert.ok(within(table).queryByText("0.00 AUD"), "The validated zero baseline should remain visible.");
  assert.ok(within(table).queryByText(/comparison amount is zero or negative/), "The percentage limitation should be readable without hovering.");
});
