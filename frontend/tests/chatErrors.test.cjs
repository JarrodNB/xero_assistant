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
