/**
 * Purpose: Build partial invoice updates without resubmitting untouched accounting lines.
 *
 * Public API:
 * - InvoiceFormValues
 * - InvoiceUpdate
 * - buildInvoiceUpdate
 * - invoiceLinesChanged
 */

import { Invoice, LineItem } from "./types";

export type InvoiceFormValues = {
  contactName: string;
  reference: string;
  dueDate: string;
  lineItems: LineItem[];
};

export type InvoiceUpdate = {
  invoice_number: string;
  contact_name?: string;
  reference?: string;
  due_date?: string;
  line_items?: Array<Pick<LineItem, "description" | "quantity" | "unit_amount" | "line_item_id">>;
  removed_line_item_ids?: string[];
};

/** Compare only editable values and identity, leaving accounting metadata on the server. */
export function invoiceLinesChanged(original: LineItem[], current: LineItem[]): boolean {
  return original.length !== current.length || original.some((line, index) => {
    const changed = current[index];
    return line.line_item_id !== changed.line_item_id || line.description !== changed.description ||
      line.quantity !== changed.quantity || line.unit_amount !== changed.unit_amount;
  });
}

/** Emit intended changes and explicit removals; an empty reference clears the existing value. */
export function buildInvoiceUpdate(invoice: Invoice, values: InvoiceFormValues): InvoiceUpdate {
  const update: InvoiceUpdate = { invoice_number: invoice.invoice_number };
  if (values.contactName !== invoice.contact_name) update.contact_name = values.contactName;
  if (values.reference !== (invoice.reference ?? "")) update.reference = values.reference;
  if (values.dueDate !== (invoice.due_date ?? "")) {
    if (!values.dueDate) throw new Error("Clearing a due date is not supported by this editor. Set a date or edit it in Xero.");
    update.due_date = values.dueDate;
  }
  if (invoiceLinesChanged(invoice.line_items ?? [], values.lineItems)) {
    if (invoice.line_editing_supported === false) throw new Error("Edit these unsupported invoice lines in Xero.");
    update.line_items = values.lineItems.map(({ description, quantity, unit_amount, line_item_id }) => ({
      description, quantity, unit_amount, ...(line_item_id ? { line_item_id } : {}),
    }));
    const kept = new Set(values.lineItems.map((line) => line.line_item_id).filter(Boolean));
    update.removed_line_item_ids = (invoice.line_items ?? []).flatMap((line) =>
      line.line_item_id && !kept.has(line.line_item_id) ? [line.line_item_id] : []);
  }
  if (Object.keys(update).length === 1) throw new Error("No invoice fields have changed.");
  return update;
}
