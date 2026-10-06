/**
 * Purpose: Create an invoice from the standard editor.
 *
 * Public API:
 * - NewInvoicePage
 */

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { InvoiceForm } from "../../../../components/InvoiceForm";
import { ApiRequestError, apiRequest } from "../../../../lib/api";
import { Invoice, LineItem } from "../../../../lib/types";

/**
 * Save a new authorised invoice after the person clicks Save.
 */
export default function NewInvoicePage() {
  const router = useRouter();
  const [contactName, setContactName] = useState("");
  const [notice, setNotice] = useState("");

  /**
   * Create only the contact. The invoice save is a separate confirmation.
   */
  async function createContact() {
    setNotice("");
    try {
      await apiRequest("/api/backend/contacts", {
        method: "POST",
        body: JSON.stringify({ name: contactName }),
      });
      setNotice(`Created contact ${contactName}.`);
    } catch (caught) {
      setNotice(caught instanceof ApiRequestError ? `${caught.message}. ${caught.nextStep}` : "The contact could not be created.");
    }
  }

  /**
   * Create only the invoice. The contact must already exist.
   */
  async function save(values: { contactName: string; reference: string; dueDate: string; lineItems: LineItem[] }) {
    const created = await apiRequest<{ invoice: Invoice }>("/api/backend/invoices", {
      method: "POST",
      body: JSON.stringify({
        contact_name: values.contactName,
        reference: values.reference || null,
        due_date: values.dueDate || null,
        line_items: values.lineItems,
      }),
    });
    router.push(`/invoices/${encodeURIComponent(created.invoice.invoice_number)}`);
  }

  return (
    <section>
      <div className="page-header">
        <h1>New invoice</h1>
      </div>
      <form
        className="panel filters"
        onSubmit={(event) => {
          event.preventDefault();
          void createContact();
        }}
      >
        <label className="field">
          New contact
          <input value={contactName} onChange={(event) => setContactName(event.target.value)} required />
        </label>
        <button className="secondary" type="submit">
          Create contact
        </button>
      </form>
      {notice ? <p className="muted">{notice}</p> : null}
      <InvoiceForm
        contactName=""
        reference=""
        dueDate=""
        lineItems={[{ description: "", quantity: 1, unit_amount: 1 }]}
        submitLabel="Save invoice"
        onSubmit={save}
      />
    </section>
  );
}
