/**
 * Purpose: Invoice and action shapes returned by the API.
 *
 * Public API:
 * - LineItem
 * - Invoice
 * - Contact
 * - ProposedAction
 */

export type LineItem = {
  description: string;
  quantity: number;
  unit_amount: number;
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
};

export type Contact = {
  name: string;
  email: string | null;
};

export type ProposedAction = {
  kind: "proposed_action";
  action_id: string;
  action_type: string;
  status: string;
  summary: string;
  payload: Record<string, unknown>;
};
