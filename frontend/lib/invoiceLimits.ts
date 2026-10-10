/**
 * Purpose: Browser-side invoice number limits mirrored from backend validation.
 *
 * Public API:
 * - MAX_INVOICE_LINES
 * - MAX_QUANTITY
 * - MAX_UNIT_AMOUNT
 * - MAX_INVOICE_SUBTOTAL
 * - validateInvoiceLines
 */

import { LineItem } from "./types";

export const MAX_INVOICE_LINES = 100;
export const MAX_QUANTITY = 99_999_999.9999;
export const MAX_UNIT_AMOUNT = 999_999_999_999.99;
export const MAX_INVOICE_SUBTOTAL = 999_999_999_999.99;

/**
 * Return a useful invoice-line error before the API performs authoritative validation.
 */
export function validateInvoiceLines(lines: LineItem[]): string {
  if (lines.length === 0) {
    return "Add at least one line item.";
  }
  if (lines.length > MAX_INVOICE_LINES) {
    return `An invoice can contain at most ${MAX_INVOICE_LINES} line items.`;
  }
  let subtotal = 0;
  for (const line of lines) {
    if (!Number.isFinite(line.quantity) || line.quantity <= 0 || line.quantity > MAX_QUANTITY) {
      return `Each quantity must be greater than 0 and at most ${MAX_QUANTITY}.`;
    }
    if (!Number.isFinite(line.unit_amount) || line.unit_amount <= 0 || line.unit_amount > MAX_UNIT_AMOUNT) {
      return `Each unit amount must be greater than 0 and at most ${MAX_UNIT_AMOUNT}.`;
    }
    subtotal += line.quantity * line.unit_amount;
    if (!Number.isFinite(subtotal) || subtotal > MAX_INVOICE_SUBTOTAL) {
      return `The invoice subtotal must be at most ${MAX_INVOICE_SUBTOTAL}.`;
    }
  }
  return "";
}
