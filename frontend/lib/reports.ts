/**
 * Purpose: Typed source-backed accounting report contracts returned by FastAPI.
 * Public API:
 * - ReportRow
 * - FinancialReport
 */

export type ReportRow = {
  key: string;
  kind: "section" | "account" | "summary";
  label: string;
  amount: string | null;
  children: ReportRow[];
};

export type FinancialReport = {
  schema_version: "1";
  report_type: "profit_and_loss";
  status: "ready" | "empty";
  complete: true;
  date_from: string;
  date_to: string;
  basis: "accrual";
  currency: string;
  currency_decimal_places: number;
  timezone: string;
  retrieved_at: string;
  rows: ReportRow[];
};
