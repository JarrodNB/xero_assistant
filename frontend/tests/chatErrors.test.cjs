/**
 * Purpose: Exercise real chat SDK stream errors and cancellation without browser/provider requests.
 *
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
const { render, fireEvent, screen, waitFor, cleanup } = require("@testing-library/react");
const { ChatPanel } = require("/tmp/ledger-frontend-tests/components/ChatPanel.js");
const { actionNarration } = require("/tmp/ledger-frontend-tests/lib/actionNarration.js");
const originalFetch = globalThis.fetch;

/** Restore network and rendered state after every case. */
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

/** Render one chat and send a synthetic user request through the actual AI SDK. */
function send(historyActions = []) {
  render(React.createElement(ChatPanel, { conversation: "test-chat", transcript: [], historyActions, onActivity() {} }));
  fireEvent.change(screen.getByPlaceholderText("Ask Ledger about the connected Xero company"), { target: { value: "List invoices" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

/** Parse a real SSE error and release the composer and retained proposal cards. */
test("stream errors show safe guidance and preserve usable pending cards", async () => {
  globalThis.fetch = async () => new Response(
    'data: {"type":"start","messageId":"reply"}\n\n' +
    'data: {"type":"error","errorText":"private@example.com provider-secret"}\n\n' +
    'data: [DONE]\n\n',
    { headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" } },
  );
  send([{ kind: "proposed_action", action_id: "pending", action_type: "create_contact",
    status: "pending", summary: "Create contact Synthetic.", payload: { name: "Synthetic" } }]);
  await waitFor(() => assert.match(screen.getByRole("alert").textContent, /could not finish/));
  assert.doesNotMatch(document.body.textContent, /private@example.com|provider-secret/);
  await waitFor(() => assert.equal(screen.getByRole("button", { name: "Send" }).disabled, false));
  assert.equal(screen.getByRole("button", { name: "Confirm" }).disabled, false);
});

/** A failed fetch ends loading and permits another intentional message. */
test("network failures permit a new request without exposing error text", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    throw new Error("private@example.com unsafe network diagnostics");
  };
  send();
  await waitFor(() => assert.ok(screen.getByRole("alert")));
  await waitFor(() => assert.equal(screen.getByRole("button", { name: "Send" }).disabled, false));
  fireEvent.change(screen.getByPlaceholderText("Ask Ledger about the connected Xero company"), { target: { value: "Try again" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => assert.equal(calls, 2));
  assert.doesNotMatch(document.body.textContent, /private@example.com|unsafe network/);
});

/** Keep timeout guidance while ignoring arbitrary diagnostics appended to an otherwise known error. */
test("known backend failures display curated recovery guidance", async () => {
  globalThis.fetch = async () => new Response(
    'data: {"type":"error","errorText":"The assistant timed out. Try a shorter request. private@example.com"}\n\n' +
    'data: [DONE]\n\n',
    { headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" } },
  );
  send();
  await waitFor(() => assert.match(screen.getByRole("alert").textContent, /timed out/));
  assert.doesNotMatch(document.body.textContent, /private@example.com/);
});

/** Stop an unfinished transport stream and release the busy state. */
test("stopping a reply cancels transport and offers proposal recovery guidance", async () => {
  globalThis.fetch = async (_input, init) => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"start","messageId":"reply"}\n\n'));
        init.signal.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")), { once: true });
      },
    });
    return new Response(stream, { headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" } });
  };
  send();
  await waitFor(() => assert.ok(screen.getByRole("button", { name: "Stop reply" })));
  fireEvent.click(screen.getByRole("button", { name: "Stop reply" }));
  await waitFor(() => assert.equal(screen.getByRole("button", { name: "Send" }).disabled, false));
  assert.match(screen.getByRole("alert").textContent, /saved proposals/);
});

/** Large results keep narration below the smallest supported chat prompt budget. */
test("outcome narration is bounded and excludes private ids and invoice details", () => {
  const result = { status: "executed", action_id: "private-receipt", invoice: {
    invoice_number: "I".repeat(50), total: 999999999999.99, currency: "A".repeat(8),
    reference: "private-reference".repeat(4000), contact_name: "private-name",
    line_items: Array.from({ length: 100 }, () => ({ description: "secret line".repeat(4000), line_item_id: "private-line" })),
  } };
  const text = actionNarration("confirm", result);
  assert.ok(text.length <= 256);
  assert.match(text, /status executed/);
  assert.match(text, /999999999999.99/);
  assert.doesNotMatch(text, /private-|secret line/);
  for (const status of ["pending", "executing", "unknown", "failed", "denied"]) {
    const narration = actionNarration("deny", { ...result, status });
    assert.ok(narration.length <= 256);
    assert.match(narration, new RegExp(`status ${status}`));
    assert.doesNotMatch(narration, /Total|Invoice|private-/);
  }
});

/** Confirm a large saved action through the actual chat component and capture its transport body. */
test("confirmation sends bounded narration through the chat transport", async () => {
  let sent;
  globalThis.fetch = async (input, init) => {
    if (String(input).endsWith("/confirm")) {
      return Response.json({ status: "executed", action_id: "receipt-id", invoice: {
        invoice_number: "INV-42", total: 55, currency: "AUD", reference: "private-reference",
        line_items: Array.from({ length: 100 }, () => ({ description: "large private line".repeat(500) })),
      } });
    }
    sent = JSON.parse(init.body);
    return new Response('data: [DONE]\n\n', { headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" } });
  };
  render(React.createElement(ChatPanel, { conversation: "test-chat", transcript: [], onActivity() {}, historyActions: [
    { kind: "proposed_action", action_id: "receipt-id", action_type: "update_invoice", status: "pending", summary: "Update invoice INV-42.", payload: {} },
  ] }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
  await waitFor(() => assert.ok(sent));
  const text = sent.messages.at(-1).parts.find((part) => part.type === "text").text;
  assert.ok(text.length <= 256);
  assert.match(text, /INV-42/);
  assert.doesNotMatch(text, /receipt-id|private/);
});

/** Context handoff stays an editable draft until the person intentionally sends it. */
test("report handoff prepares an editable context-bound draft without submitting", async () => {
  window.sessionStorage.setItem("ledger-report-draft", JSON.stringify({ token: "signed-context", draft: "Explain this report change." }));
  let body = null;
  globalThis.fetch = async (_url, init) => {
    body = JSON.parse(init.body);
    return new Response('data: {"type":"start","messageId":"report"}\n\ndata: {"type":"finish"}\n\ndata: [DONE]\n\n', { headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" } });
  };
  render(React.createElement(ChatPanel, { conversation: "report-draft", transcript: [], historyActions: [], onActivity() {} }));
  const input = screen.getByPlaceholderText("Ask Ledger about the connected Xero company");
  assert.equal(input.value, "Explain this report change.");
  assert.equal(body, null);
  fireEvent.change(input, { target: { value: "Which expense changed most?" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => assert.equal(body.report_context, "signed-context"));
});
