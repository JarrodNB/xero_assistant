/**
 * Purpose: Edit or void one invoice.
 *
 * Public API:
 * - EditInvoicePage
 */

"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { InvoiceForm } from "../../../../components/InvoiceForm";
import { ApiRequestError, apiRequest } from "../../../../lib/api";
import { Invoice, LineItem } from "../../../../lib/types";

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
 * Load one invoice and save changes or void it.
 */
export default function EditInvoicePage() {
  const params = useParams<{ invoiceNumber: string }>();
  const router = useRouter();
  const invoiceNumber = decodeURIComponent(params.invoiceNumber);
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [error, setError] = useState("");
  const [voiding, setVoiding] = useState(false);
  const voidingRef = useRef(false);

  useEffect(() => {
    /**
     * Load the invoice being edited.
     */
    async function load() {
      try {
        const body = await apiRequest<{ invoice: Invoice }>(`/api/backend/invoices/${encodeURIComponent(invoiceNumber)}`);
        setInvoice(body.invoice);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Invoice could not be loaded.");
      }
    }
    void load();
  }, [invoiceNumber]);

  /**
   * Save edits. Saving is the confirmation.
   */
  async function save(values: { contactName: string; reference: string; dueDate: string; lineItems: LineItem[] }) {
    const body = await apiRequest<{ invoice: Invoice }>(`/api/backend/invoices/${encodeURIComponent(invoiceNumber)}`, {
      method: "PUT",
      body: JSON.stringify({
        invoice_number: invoiceNumber,
        contact_name: values.contactName,
        reference: values.reference || null,
        due_date: values.dueDate || null,
        line_items: values.lineItems,
      }),
    });
    setInvoice(body.invoice);
  }

  /**
   * Void the invoice. The button is the confirmation.
   */
  async function voidInvoice() {
    if (voidingRef.current) {
      return;
    }
    voidingRef.current = true;
    setVoiding(true);
    setError("");
    try {
      const body = await apiRequest<{ invoice: Invoice }>(
        `/api/backend/invoices/${encodeURIComponent(invoiceNumber)}/void`,
        { method: "POST" },
      );
      setInvoice(body.invoice);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? `${caught.message}. ${caught.nextStep}` : "The invoice could not be voided.");
    } finally {
      voidingRef.current = false;
      setVoiding(false);
    }
  }

  if (!invoice) {
    return <p className="muted">{error || "Loading invoice…"}</p>;
  }

  return (
    <section>
      <div className="page-header">
        <h1>{invoice.invoice_number}</h1>
        <button className="danger" type="button" disabled={voiding} onClick={() => void voidInvoice()}>
          {voiding ? "Voiding…" : "Void invoice"}
        </button>
      </div>
      <p className="invoice-meta">
        <span className={statusClass(invoice.status)}>{statusLabel(invoice.status)}</span>
        <span className="muted">
          {invoice.total.toFixed(2)} {invoice.currency} · {invoice.amount_due.toFixed(2)} due
        </span>
      </p>
      {error ? <p className="error">{error}</p> : null}
      <InvoiceForm
        contactName={invoice.contact_name}
        reference={invoice.reference ?? ""}
        dueDate={invoice.due_date ?? ""}
        lineItems={invoice.line_items ?? []}
        submitLabel="Save changes"
        onSubmit={save}
      />
    </section>
  );
}
