/**
 * Purpose: Exercise invoice form edits and server-response reconciliation without a browser.
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
const { InvoiceForm } = require("/tmp/ledger-frontend-tests/components/InvoiceForm.js");
const { buildInvoiceUpdate } = require("/tmp/ledger-frontend-tests/lib/invoiceEdits.js");

/** Remove rendered components and reset event handlers after each case. */
afterEach(() => cleanup());

/** Return a fixture with server-owned accounting information and stable line identities. */
function invoice() {
  return {
    invoice_number: "INV-1", contact_name: "Review", status: "AUTHORISED", reference: "Original",
    date: "2026-10-12", due_date: "2026-11-01", total: 100, amount_due: 100, currency: "AUD",
    line_editing_supported: true,
    line_items: [{ line_item_id: "line-a", description: "Work", quantity: 1, unit_amount: 100 }],
  };
}

/** Render the form using the same partial-payload builder as the invoice editor. */
function editor(original, capture) {
  return render(React.createElement(InvoiceForm, {
    editing: true,
    linesEditable: original.line_editing_supported,
    contactName: original.contact_name,
    reference: original.reference ?? "",
    dueDate: original.due_date ?? "",
    lineItems: original.line_items,
    submitLabel: "Save changes",
    onSubmit: async (values) => capture(buildInvoiceUpdate(original, values)),
  }));
}

/** Clear the reference through actual input events without resending the invoice lines. */
test("clearing the reference submits an empty string and no unchanged fields", async () => {
  const writes = [];
  editor(invoice(), (update) => writes.push(update));
  fireEvent.change(screen.getByLabelText("Reference"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => assert.equal(writes.length, 1));
  assert.deepEqual(writes[0], { invoice_number: "INV-1", reference: "" });
});

/** Preserve line identity when changing a description and omit server accounting metadata. */
test("description edits submit identity and editable values", async () => {
  const writes = [];
  editor(invoice(), (update) => writes.push(update));
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Updated work" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => assert.equal(writes.length, 1));
  assert.deepEqual(writes[0].line_items, [{ line_item_id: "line-a", description: "Updated work", quantity: 1, unit_amount: 100 }]);
  assert.deepEqual(writes[0].removed_line_item_ids, []);
});

/** Record deliberate removal rather than treating an unidentified existing line as a new one. */
test("removing a line sends an explicit removal id", async () => {
  const original = invoice();
  original.line_items.push({ line_item_id: "line-b", description: "Parts", quantity: 1, unit_amount: 20 });
  const writes = [];
  editor(original, (update) => writes.push(update));
  fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[1]);
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => assert.equal(writes.length, 1));
  assert.deepEqual(writes[0].removed_line_item_ids, ["line-b"]);
  assert.equal(writes[0].line_items[0].line_item_id, "line-a");
});

/** Reject an unsupported due-date clear before any API request is emitted. */
test("clearing a due date explains the limitation without writing", async () => {
  const writes = [];
  editor(invoice(), (update) => writes.push(update));
  fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText(/Clearing a due date is not supported/);
  assert.equal(writes.length, 0);
});

/** Let metadata updates proceed even when the invoice's existing lines are outside edit limits. */
test("unsupported existing lines are disabled but do not block reference editing", async () => {
  const original = invoice();
  original.line_editing_supported = false;
  original.line_items[0].quantity = 0;
  const writes = [];
  editor(original, (update) => writes.push(update));
  assert.equal(screen.getByLabelText("Quantity").disabled, true);
  fireEvent.change(screen.getByLabelText("Reference"), { target: { value: "Updated" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => assert.equal(writes.length, 1));
  assert.deepEqual(writes[0], { invoice_number: "INV-1", reference: "Updated" });
});

/** Keep explicit tax overrides stable by making amount changes unavailable in the form. */
test("explicit-tax lines allow descriptions but keep amounts read-only", () => {
  const original = invoice();
  original.line_items[0].has_explicit_tax = true;
  editor(original, () => {});
  assert.equal(screen.getByLabelText("Quantity").readOnly, true);
  assert.equal(screen.getByLabelText("Unit amount").readOnly, true);
  assert.equal(screen.getByLabelText("Description").disabled, false);
});

/** Remount with the saved response so inputs show normalized server values after saving. */
test("server response replaces the saved form draft", async () => {
  const original = invoice();

  /** Use the same keyed form remount as the invoice page after a successful save. */
  function SavedEditor() {
    const [saved, setSaved] = React.useState(original);
    return React.createElement(InvoiceForm, {
      key: JSON.stringify(saved), editing: true, contactName: saved.contact_name,
      reference: saved.reference, dueDate: saved.due_date, lineItems: saved.line_items,
      submitLabel: "Save changes",
      onSubmit: async () => setSaved({ ...saved, reference: "Normalized by Xero", total: 120 }),
    });
  }

  render(React.createElement(SavedEditor));
  fireEvent.change(screen.getByLabelText("Reference"), { target: { value: "Draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => assert.equal(screen.getByLabelText("Reference").value, "Normalized by Xero"));
});

/** An unchanged form is a useful validation error instead of an empty write proposal. */
test("saving unchanged values does not write", async () => {
  const writes = [];
  editor(invoice(), (update) => writes.push(update));
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText("No invoice fields have changed.");
  assert.equal(writes.length, 0);
});
