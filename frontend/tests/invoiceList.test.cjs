/**
 * Purpose: Verify invoice currency displays, partial results and stale-response isolation.
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
const { render, fireEvent, screen, waitFor, cleanup, act } = require("@testing-library/react");
const Module = require("node:module");
const originalLoad = Module._load;
/** Use an ordinary anchor for Next links inside this DOM-only interaction test. */
Module._load = function(request, ...args) {
  if (request === "next/link") return { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) };
  return originalLoad.call(this, request, ...args);
};
const Page = require("/tmp/ledger-frontend-tests/app/(app)/invoices/page.js").default;
Module._load = originalLoad;
/** Remove rendered state and mocked network calls after each case. */
afterEach(() => { cleanup(); delete globalThis.fetch; });
/** Return one per-currency summary group. */
function group(currency) {
  return { currency, invoice_count: 1, unpaid_count: 1, overdue_count: 1, unpaid_total: 100, overdue_total: 100, invoice_total: 100 };
}
/** Resolve a synthetic HTTP JSON response. */
function response(body, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}
/** Render both currencies without displaying a combined 200. */
test("invoice summary displays separate currency-labelled amounts", async () => {
  globalThis.fetch = async (url) => response(url.includes("invoice-summary")
    ? { schema_version: "2", complete: true, currencies: [group("AUD"), group("USD")] }
    : { schema_version: "2", complete: true, invoices: [] });
  render(React.createElement(Page));
  await waitFor(() => assert.equal(screen.getAllByText("100.00 AUD").length, 3));
  assert.equal(screen.getAllByText("100.00 USD").length, 3);
  assert.equal(screen.queryByText(/200\.00/), null);
});
/** Reject aggregate totals while still rendering explicitly partial emptiness. */
test("partial empty list never claims no invoices match", async () => {
  globalThis.fetch = async (url) => response(url.includes("invoice-summary")
    ? { error: { what: "Invoice results are incomplete", why: "Cap reached", retryable: false, next_step: "Narrow the filters." } }
    : { schema_version: "2", complete: false, invoices: [], next_step: "Results are partial. Narrow filters." }, url.includes("invoice-summary") ? 409 : 200);
  render(React.createElement(Page));
  await screen.findByText("No matches in the partial results. Narrow the filters.");
  assert.equal(screen.queryByText("No invoices match these filters."), null);
  assert.ok(screen.getByText("Totals unavailable until complete results load."));
  assert.ok(screen.getByRole("status"));
});
/** Empty complete totals must not invent an AUD or USD zero balance. */
test("empty complete summary shows no matching invoices without currency", async () => {
  globalThis.fetch = async (url) => response(url.includes("invoice-summary")
    ? { schema_version: "2", complete: true, currencies: [] }
    : { schema_version: "2", complete: true, invoices: [] });
  render(React.createElement(Page));
  await waitFor(() => assert.equal(screen.getAllByText("No matching invoices").length, 3));
  assert.equal(screen.queryByText(/0\.00/), null);
});
/** A delayed response for old filters cannot replace newer financial totals. */
test("late old-filter responses cannot overwrite current summary", async () => {
  const pending = [];
  globalThis.fetch = (url) => new Promise(resolve => pending.push({ url, resolve }));
  render(React.createElement(Page));
  await waitFor(() => assert.equal(pending.length, 2));
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "PAID" } });
  await waitFor(() => assert.equal(pending.length, 4));
  /** Complete one filter's two synthetic requests. */
  async function finish(items, currency) {
    await act(async () => {
      for (const item of items) item.resolve(await response(item.url.includes("invoice-summary")
        ? { schema_version: "2", complete: true, currencies: [group(currency)] }
        : { schema_version: "2", complete: true, invoices: [] }));
    });
  }
  await finish(pending.slice(2), "USD");
  await finish(pending.slice(0, 2), "AUD");
  assert.equal(screen.getAllByText("100.00 USD").length, 3);
  assert.equal(screen.queryByText("100.00 AUD"), null);
});
