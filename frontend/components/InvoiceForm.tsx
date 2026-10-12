/**
 * Purpose: Editable invoice form shared by create and update.
 *
 * Public API:
 * - InvoiceForm
 */

"use client";

import { FormEvent, useRef, useState } from "react";
import { ApiRequestError } from "../lib/api";
import {
  MAX_INVOICE_LINES,
  MAX_QUANTITY,
  MAX_UNIT_AMOUNT,
  validateInvoiceLines,
} from "../lib/invoiceLimits";
import { LineItem } from "../lib/types";
import { InvoiceFormValues, invoiceLinesChanged } from "../lib/invoiceEdits";

type InvoiceFormProps = {
  contactName: string;
  reference: string;
  dueDate: string;
  lineItems: LineItem[];
  submitLabel: string;
  editing?: boolean;
  linesEditable?: boolean;
  onSubmit: (values: InvoiceFormValues) => Promise<void>;
};

/**
 * Edit contact, dates, and line items, then save through the parent.
 */
export function InvoiceForm({
  contactName,
  reference,
  dueDate,
  lineItems,
  submitLabel,
  onSubmit,
  editing = false,
  linesEditable = true,
}: InvoiceFormProps) {
  const [name, setName] = useState(contactName);
  const [note, setNote] = useState(reference);
  const [due, setDue] = useState(dueDate);
  const [lines, setLines] = useState<LineItem[]>(lineItems);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);

  /**
   * Save the current form values.
   */
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (savingRef.current) {
      return;
    }
    setError("");
    const validationError = !editing || invoiceLinesChanged(lineItems, lines) ? validateInvoiceLines(lines) : "";
    if (validationError) {
      setError(validationError);
      return;
    }
    try {
      savingRef.current = true;
      setSaving(true);
      await onSubmit({ contactName: name, reference: note, dueDate: due, lineItems: lines });
    } catch (caught) {
      if (caught instanceof ApiRequestError) {
        setError(`${caught.message}. ${caught.nextStep}`);
      } else {
        setError(caught instanceof Error ? caught.message : "The invoice could not be saved.");
      }
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  /**
   * Replace one field on a line.
   */
  function updateLine(index: number, field: keyof LineItem, value: string) {
    setLines((current) =>
      current.map((line, lineIndex) => {
        if (lineIndex !== index) {
          return line;
        }
        if (field === "description") {
          return { ...line, description: value };
        }
        return { ...line, [field]: Number(value) };
      }),
    );
  }

  return (
    <form className="panel invoice-form" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label className="field">
          Contact
          <input value={name} disabled={saving} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label className="field">
          Reference
          <input value={note} disabled={saving} onChange={(event) => setNote(event.target.value)} />
        </label>
        <label className="field">
          Due date
          <input type="date" value={due} disabled={saving} onChange={(event) => setDue(event.target.value)} />
        </label>
      </div>
      <div className="lines">
        {lines.map((line, index) => (
          <div className="line-row" key={index}>
            <label className="field">
              Description
              <input value={line.description} disabled={!linesEditable || saving} onChange={(event) => updateLine(index, "description", event.target.value)} required />
            </label>
            <label className="field">
              Quantity
              <input
                type="number"
                min="0.0001"
                max={MAX_QUANTITY}
                step="0.0001"
                value={line.quantity}
                readOnly={line.has_explicit_tax === true}
                disabled={!linesEditable || saving}
                onChange={(event) => updateLine(index, "quantity", event.target.value)}
                required
              />
            </label>
            <label className="field">
              Unit amount
              <input
                type="number"
                min="0.01"
                max={MAX_UNIT_AMOUNT}
                step="0.01"
                value={line.unit_amount}
                readOnly={line.has_explicit_tax === true}
                disabled={!linesEditable || saving}
                onChange={(event) => updateLine(index, "unit_amount", event.target.value)}
                required
              />
            </label>
            <button
              className="secondary"
              type="button"
              disabled={!linesEditable || saving}
              onClick={() => setLines((current) => current.filter((_, lineIndex) => lineIndex !== index))}
            >
              Remove
            </button>
          </div>
        ))}
      </div>
      <div className="form-footer">
        <button
          className="secondary"
          type="button"
          onClick={() => setLines((current) => [...current, { description: "", quantity: 1, unit_amount: 1 }])}
          disabled={!linesEditable || saving || lines.length >= MAX_INVOICE_LINES}
        >
          Add line
        </button>
        {error ? <p className="error">{error}</p> : null}
        {!linesEditable ? <p className="muted">Edit these invoice lines in Xero; this editor can still change the contact, reference, or due date.</p> : null}
        {linesEditable && lines.some((line) => line.has_explicit_tax) ? <p className="muted">Change amounts on lines with explicit tax in Xero. Descriptions can still be edited here.</p> : null}
        <button className="primary" type="submit" disabled={saving}>
          {saving ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
