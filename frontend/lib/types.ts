/**
 * Purpose: Invoice and action shapes returned by the API.
 *
 * Public API:
 * - LineItem
 * - Invoice
 * - Contact
 * - ProposedAction
 * - ConversationSummary
 * - StoredMessage
 * - CurrencySummary, InvoiceSummary, InvoiceReadResult, PeriodComparison
 */

export type LineItem = {
  description: string;
  quantity: number;
  unit_amount: number;
  line_item_id?: string | null;
  has_explicit_tax?: boolean;
};

export type Invoice = {
  invoice_number: string;
  contact_name: string;
  status: string;
  date: string | null;
  due_date: string | null;
  total: number;
  amount_due: number;
  currency: string;
  reference: string | null;
  line_items?: LineItem[];
  line_editing_supported?: boolean;
};

export type Contact = {
  name: string;
  email: string | null;
};

export type CurrencySummary = {
  currency: string;
  invoice_count: number;
  unpaid_count: number;
  overdue_count: number;
  unpaid_total: number;
  overdue_total: number;
  invoice_total: number;
};

export type InvoiceSummary = {
  schema_version: "2";
  complete: true;
  invoice_count: number;
  unpaid_count: number;
  overdue_count: number;
  currencies: CurrencySummary[];
};

export type InvoiceReadResult = {
  schema_version: "2";
  invoices: Invoice[];
  complete: boolean;
  scanned_count: number;
  limit: number;
  next_step: string | null;
};

export type PeriodComparison = {
  schema_version: "2";
  complete: true;
  currencies: { currency: string; period_a_total: number; period_b_total: number; difference: number }[];
};

export type ProposedAction = {
  kind: "proposed_action";
  action_id: string;
  action_type: string;
  status: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at?: string;
};

export type ConversationSummary = {
  id: string;
  updated_at: string;
  preview: string;
};

export type StoredMessage = {
  id: string;
  role: string;
  content: string;
  created_at: string;
};
