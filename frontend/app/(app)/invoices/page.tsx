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
import { Invoice, InvoiceSummary, InvoiceReadResult } from "../../../lib/types";

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
  const [summary, setSummary] = useState<InvoiceSummary | null>(null);
  const [complete, setComplete] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [partialMessage, setPartialMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoaded(false);
    setSummary(null);
    setInvoices([]);
    setPartialMessage("");
    setError("");
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
        const [invoiceResult, summaryResult] = await Promise.allSettled([
          apiRequest<InvoiceReadResult>(`/api/backend/invoices${query ? `?${query}` : ""}`),
          apiRequest<InvoiceSummary>(`/api/backend/invoice-summary${query ? `?${query}` : ""}`),
        ]);
        if (cancelled) return;
        if (invoiceResult.status === "rejected") throw invoiceResult.reason;
        setInvoices(invoiceResult.value.invoices);
        setComplete(invoiceResult.value.complete);
        setLoaded(true);
        if (!invoiceResult.value.complete) {
          setPartialMessage(invoiceResult.value.next_step ?? "Results are partial. Narrow the filters.");
        }
        if (summaryResult.status === "rejected") throw summaryResult.reason;
        setSummary(summaryResult.value);
      } catch (caught) {
        if (cancelled) return;
        const message = caught instanceof ApiRequestError ? `${caught.message}. ${caught.nextStep}` : "Invoices could not be loaded.";
        setError(message);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [status, contactName]);

  return (
    <section>
      <div className="page-header">
        <h1>Invoices</h1>
        <Link className="primary" href="/invoices/new">
          New invoice
        </Link>
      </div>
      {summary ? <div className="summary-row">
        <div className="panel summary-card">
          <span>Unpaid</span>
          {summary.currencies.map((group) => <strong key={group.currency}>{group.unpaid_total.toFixed(2)} {group.currency}</strong>)}
          {summary.currencies.length === 0 ? <strong>No matching invoices</strong> : null}
        </div>
        <div className={summary.currencies.some((group) => group.overdue_total > 0) ? "panel summary-card warning" : "panel summary-card"}>
          <span>Overdue</span>
          {summary.currencies.map((group) => <strong key={group.currency}>{group.overdue_total.toFixed(2)} {group.currency}</strong>)}
          {summary.currencies.length === 0 ? <strong>No matching invoices</strong> : null}
        </div>
        <div className="panel summary-card">
          <span>Listed total</span>
          {summary.currencies.map((group) => <strong key={group.currency}>{group.invoice_total.toFixed(2)} {group.currency}</strong>)}
          {summary.currencies.length === 0 ? <strong>No matching invoices</strong> : null}
        </div>
      </div> : <p>Totals unavailable until complete results load.</p>}
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
      {partialMessage ? <p role="status">{partialMessage}</p> : null}
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
                  {loaded && complete ? "No invoices match these filters." : loaded ? "No matches in the partial results. Narrow the filters." : "Invoices have not loaded."}
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
                  <td className="money">{invoice.amount_due.toFixed(2)} {invoice.currency}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
