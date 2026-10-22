/**
 * Purpose: Typed source-backed accounting report contracts returned by FastAPI.
 * Public API:
 * - ReportRow
 * - FinancialReport
 * - AmountComparison
 * - AccountMovement
 * - ReportComparison
 * - BalanceSheetReport
 * - PositionMovement
 * - BalanceSheetComparison
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

export type AmountComparison = {
  current: string;
  comparison: string;
  change: string;
  percentage_change: string | null;
  percentage_note: string | null;
};

export type AccountMovement = AmountComparison & {
  key: string;
  label: string;
  previous_label: string | null;
  category: "income" | "expenses";
  contribution: string;
  current_source: string | null;
  comparison_source: string | null;
};

export type ReportComparison = {
  schema_version: "1";
  report_type: "profit_and_loss";
  status: "ready" | "empty";
  complete: true;
  current: FinancialReport;
  comparison: FinancialReport;
  metrics: Record<string, AmountComparison>;
  movements: AccountMovement[];
  top_movements: AccountMovement[];
  other_movements: string | null;
  warnings: string[];
};

export type BalanceSheetReport = Omit<FinancialReport, "report_type" | "date_from" | "date_to"> & {
  report_type: "balance_sheet";
  as_of: string;
};

export type PositionMovement = Omit<AccountMovement, "category" | "contribution"> & {
  category: "assets" | "liabilities" | "equity";
  section: string;
};

export type BalanceSheetComparison = Omit<ReportComparison, "report_type" | "current" | "comparison" | "movements" | "top_movements" | "other_movements"> & {
  report_type: "balance_sheet";
  current: BalanceSheetReport;
  comparison: BalanceSheetReport;
  movements: PositionMovement[];
  top_movements: PositionMovement[];
};
