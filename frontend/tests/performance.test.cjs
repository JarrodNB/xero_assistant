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
const { render, screen, cleanup, fireEvent, act } = require("@testing-library/react");
const Page = require("/tmp/ledger-frontend-tests/app/(app)/performance/page.js").default;

/** Restore isolated DOM and HTTP state. */
afterEach(() => { cleanup(); delete globalThis.fetch; });

/** Build a synthetic report response without private account identifiers. */
function fixture() {
  return { schema_version: "1", report_type: "profit_and_loss", status: "ready", complete: true,
    date_from: "2026-01-01", date_to: "2026-01-31", basis: "accrual", currency: "AUD", timezone: "UTC", retrieved_at: "2026-02-01T00:00:00Z",
    currency_decimal_places: 2,
    rows: [{ key: "source-1", kind: "section", label: "Trading Income", amount: null,
      children: [{ key: "source-1-1", kind: "account", label: "Consulting", amount: "1000.10", children: [] }] }] };
}

/** Display returned dates and exact source amounts in an accessible disclosure. */
test("P&L source rows retain exact values and metadata", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify(fixture()), { status: 200 });
  render(React.createElement(Page));
  await screen.findByText("1000.10 AUD");
  assert.ok(screen.getByText("Consulting"));
  assert.ok(screen.getByText(/2026-01-01/));
  assert.ok(screen.getByText(/2026-01-31/));
  assert.ok(screen.getByText(/Accrual/));
  assert.ok(screen.getByText("Trading Income").closest("summary"));
  assert.ok(document.getElementById("source-1-1"));
  const summary = screen.getByText("Trading Income");
  fireEvent.click(summary);
  assert.equal(summary.closest("details").open, false);
});

/** An empty report is an absence of source data, not a zero-profit claim. */
test("empty reports do not invent amounts", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ ...fixture(), status: "empty", rows: [] }), { status: 200 });
  render(React.createElement(Page));
  await screen.findByText(/Xero returned no report data/);
  assert.equal(screen.queryByText(/0\.00 AUD/), null);
});

/** Missing report consent is distinct from ordinary connectivity and can be retried. */
test("report permissions show reconnect guidance and refresh recovers", async () => {
  let count = 0;
  globalThis.fetch = async (url) => {
    assert.equal(url, "/api/backend/reports/profit-and-loss");
    count += 1;
    return count === 1 ? new Response(JSON.stringify({ what: "Report access required", why: "Missing report scope", next_step: "Reconnect Xero." }), { status: 403 })
      : new Response(JSON.stringify(fixture()), { status: 200 });
  };
  render(React.createElement(Page));
  assert.equal((await screen.findByRole("link", { name: "Reconnect Xero for reports" })).getAttribute("href"), "/api/xero/start");
  fireEvent.click(screen.getByRole("button", { name: "Refresh report" }));
  await screen.findByText("1000.10 AUD");
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
    newer.rows[0].children[0].amount = "2000.20";
    return new Response(JSON.stringify(newer), { status: 200 });
  };
  const first = render(React.createElement(Page));
  first.unmount();
  render(React.createElement(Page));
  await screen.findByText("2000.20 AUD");
  await act(async () => finish(new Response(JSON.stringify(fixture()), { status: 200 })));
  assert.ok(screen.getByText("2000.20 AUD"));
  assert.equal(screen.queryByText("1000.10 AUD"), null);
});
