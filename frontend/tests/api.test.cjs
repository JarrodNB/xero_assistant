/**
 * Purpose: Verify editor write receipts using mocked browser storage and HTTP responses.
 *
 * Public API:
 * - Node test runner cases
 */

const assert = require("node:assert/strict");
const { test, beforeEach, afterEach } = require("node:test");
const { webcrypto } = require("node:crypto");
const { apiRequest, ApiRequestError } = require("/tmp/ledger-frontend-tests/api.js");

const originalFetch = globalThis.fetch;
const originalStorage = globalThis.sessionStorage;
const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
let stored;

/** Install a fresh browser-like storage implementation for each case. */
beforeEach(() => {
  stored = new Map();
  globalThis.sessionStorage = {
    /** Read one saved receipt identifier. */
    getItem(key) { return stored.get(key) ?? null; },
    /** Save an identifier without retaining submitted personal values. */
    setItem(key, value) { stored.set(key, value); },
    /** Release the receipt after a reliable result. */
    removeItem(key) { stored.delete(key); },
  };
  Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true });
});

/** Restore globals so tests cannot contaminate other suites. */
afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.sessionStorage = originalStorage;
  if (originalCrypto) Object.defineProperty(globalThis, "crypto", originalCrypto);
  else delete globalThis.crypto;
});

/** Return a JSON response without any network access. */
function response(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Keep one retry id across a lost response and release it after confirmed success. */
test("lost response retains a private receipt and retry reuses its id", async () => {
  const ids = [];
  globalThis.fetch = async (_path, init) => {
    ids.push(init.headers.get("X-Write-Id"));
    if (ids.length === 1) throw new Error("private transport details");
    return response({ contact: { name: "Sensitive Contact" } });
  };
  const init = { method: "POST", body: JSON.stringify({ name: "Sensitive Contact" }) };
  await assert.rejects(apiRequest("/api/backend/contacts", init), (error) => error instanceof ApiRequestError && error.outcomeUnknown && !error.message.includes("private"));
  assert.equal(stored.size, 1);
  assert.ok(!JSON.stringify([...stored]).includes("Sensitive Contact"));
  await apiRequest("/api/backend/contacts", init);
  assert.equal(ids[0], ids[1]);
  assert.equal(stored.size, 0);
  await apiRequest("/api/backend/contacts", init);
  assert.notEqual(ids[1], ids[2]);
});

/** Give overlapping submissions the same backend deduplication identifier. */
test("concurrent identical writes share one receipt", async () => {
  let resolveBoth;
  const both = new Promise((resolve) => { resolveBoth = resolve; });
  const ids = [];
  globalThis.fetch = async (_path, init) => {
    ids.push(init.headers.get("X-Write-Id"));
    if (ids.length === 2) resolveBoth();
    await both;
    return response({ invoice: {} });
  };
  const init = { method: "POST", body: "{}" };
  await Promise.all([apiRequest("/api/backend/invoices", init), apiRequest("/api/backend/invoices", init)]);
  assert.equal(ids.length, 2);
  assert.equal(ids[0], ids[1]);
});

/** Preserve receipt identity when the server cannot establish the write outcome. */
test("unknown outcome and executing status retain the retry receipt", async () => {
  const ids = [];
  globalThis.fetch = async (_path, init) => {
    ids.push(init.headers.get("X-Write-Id"));
    return ids.length === 1
      ? response({ what: "Execution outcome is unknown", outcome_unknown: true }, 502)
      : response({ what: "Write is still executing" }, 409);
  };
  const init = { method: "POST", body: "{}" };
  await assert.rejects(apiRequest("/api/backend/invoices", init));
  await assert.rejects(apiRequest("/api/backend/invoices", init));
  assert.equal(stored.size, 1);
  assert.equal(ids[0], ids[1]);
});

/** Allow a fresh intentional attempt after a definite validation rejection. */
test("known rejection releases the receipt", async () => {
  globalThis.fetch = async () => response({ what: "Invalid request" }, 422);
  await assert.rejects(apiRequest("/api/backend/invoices", { method: "POST", body: "{}" }));
  assert.equal(stored.size, 0);
});

/** Treat a malformed successful response as uncertainty rather than success. */
test("malformed response retains the receipt without leaking response data", async () => {
  globalThis.fetch = async () => new Response("private response detail", { status: 200 });
  await assert.rejects(apiRequest("/api/backend/invoices", { method: "POST", body: "{}" }), (error) => error.outcomeUnknown && !error.message.includes("private"));
  assert.equal(stored.size, 1);
});

/** Avoid adding write identifiers to read and authentication calls. */
test("read and login requests do not store editor receipts", async () => {
  globalThis.fetch = async (_path, init) => {
    assert.equal(init.headers.get("X-Write-Id"), null);
    return response({});
  };
  await apiRequest("/api/backend/invoices");
  await apiRequest("/api/backend/auth/login", { method: "POST", body: "{}" });
  assert.equal(stored.size, 0);
});
