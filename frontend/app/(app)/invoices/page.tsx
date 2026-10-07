/**
 * Purpose: Invoice list with unpaid totals and links into the editor.
 *
 * Public API:
 * - InvoiceListPage
 */

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiRequestError, apiRequest } from "../../../lib/api";
import { Invoice } from "../../../lib/types";

/**
 * Map a Xero status onto a pill class.
 */
function statusClass(status: string): string {
  return `status status-${status.toLowerCase()}`;
}

/**
 * Show a short label on a status pill.
 */
function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    DRAFT: "Draft",
    AUTHORISED: "Authorised",
    PAID: "Paid",
    VOIDED: "Voided",
  };
  return labels[status] ?? status;
}

/**
 * Show the demo company's invoices and a short unpaid summary.
 */
export default function InvoiceListPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [status, setStatus] = useState("");
  const [contactName, setContactName] = useState("");
  const [summary, setSummary] = useState({ unpaid_total: 0, overdue_total: 0, invoice_total: 0 });
  const [error, setError] = useState("");

  useEffect(() => {
    /**
     * Load invoices and totals for the current filters.
     */
    async function load() {
      const params = new URLSearchParams();
      if (status) {
        params.set("status", status);
      }
      if (contactName) {
        params.set("contact_name", contactName);
      }
      const query = params.toString();
      try {
        const [invoiceBody, summaryBody] = await Promise.all([
          apiRequest<{ invoices: Invoice[] }>(`/api/backend/invoices${query ? `?${query}` : ""}`),
          apiRequest<typeof summary>(`/api/backend/invoice-summary${query ? `?${query}` : ""}`),
        ]);
        setInvoices(invoiceBody.invoices);
        setSummary(summaryBody);
        setError("");
      } catch (caught) {
        const message = caught instanceof ApiRequestError ? `${caught.message}. ${caught.nextStep}` : "Invoices could not be loaded.";
        setError(message);
      }
    }
    void load();
  }, [status, contactName]);

  return (
    <section>
      <div className="page-header">
        <h1>Invoices</h1>
        <Link className="primary" href="/invoices/new">
          New invoice
        </Link>
      </div>
      <div className="summary-row">
        <div className="panel summary-card">
          <span>Unpaid</span>
          <strong>{summary.unpaid_total.toFixed(2)}</strong>
        </div>
        <div className={summary.overdue_total > 0 ? "panel summary-card warning" : "panel summary-card"}>
          <span>Overdue</span>
          <strong>{summary.overdue_total.toFixed(2)}</strong>
        </div>
        <div className="panel summary-card">
          <span>Listed total</span>
          <strong>{summary.invoice_total.toFixed(2)}</strong>
        </div>
      </div>
      <div className="filters panel">
        <label className="field">
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All</option>
            <option value="DRAFT">Draft</option>
            <option value="AUTHORISED">Authorised</option>
            <option value="PAID">Paid</option>
            <option value="VOIDED">Voided</option>
          </select>
        </label>
        <label className="field">
          Contact
          <input value={contactName} onChange={(event) => setContactName(event.target.value)} placeholder="Bob's Construction" />
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="panel table-panel">
        <table>
          <thead>
            <tr>
              <th>Number</th>
              <th>Contact</th>
              <th>Status</th>
              <th>Date</th>
              <th>Due</th>
              <th className="money">Total</th>
              <th className="money">Due amount</th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 ? (
              <tr>
                <td className="empty" colSpan={7}>
                  No invoices match these filters.
                </td>
              </tr>
            ) : (
              invoices.map((invoice, index) => (
                <tr key={`${invoice.invoice_number}-${invoice.contact_name}-${invoice.date ?? ""}-${index}`}>
                  <td>
                    <Link className="table-link" href={`/invoices/${encodeURIComponent(invoice.invoice_number)}`}>
                      {invoice.invoice_number}
                    </Link>
                  </td>
                  <td>{invoice.contact_name}</td>
                  <td>
                    <span className={statusClass(invoice.status)}>{statusLabel(invoice.status)}</span>
                  </td>
                  <td>{invoice.date}</td>
                  <td>{invoice.due_date}</td>
                  <td className="money">
                    {invoice.total.toFixed(2)} {invoice.currency}
                  </td>
                  <td className="money">{invoice.amount_due.toFixed(2)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
