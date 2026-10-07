/**
 * Purpose: Editable invoice form shared by create and update.
 *
 * Public API:
 * - InvoiceForm
 */

"use client";

import { FormEvent, useState } from "react";
import { ApiRequestError } from "../lib/api";
import { LineItem } from "../lib/types";

type InvoiceFormProps = {
  contactName: string;
  reference: string;
  dueDate: string;
  lineItems: LineItem[];
  submitLabel: string;
  onSubmit: (values: {
    contactName: string;
    reference: string;
    dueDate: string;
    lineItems: LineItem[];
  }) => Promise<void>;
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
}: InvoiceFormProps) {
  const [name, setName] = useState(contactName);
  const [note, setNote] = useState(reference);
  const [due, setDue] = useState(dueDate);
  const [lines, setLines] = useState<LineItem[]>(lineItems);
  const [error, setError] = useState("");

  /**
   * Save the current form values.
   */
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await onSubmit({ contactName: name, reference: note, dueDate: due, lineItems: lines });
    } catch (caught) {
      if (caught instanceof ApiRequestError) {
        setError(`${caught.message}. ${caught.nextStep}`);
      } else {
        setError("The invoice could not be saved.");
      }
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
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label className="field">
          Reference
          <input value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <label className="field">
          Due date
          <input type="date" value={due} onChange={(event) => setDue(event.target.value)} />
        </label>
      </div>
      <div className="lines">
        {lines.map((line, index) => (
          <div className="line-row" key={index}>
            <label className="field">
              Description
              <input value={line.description} onChange={(event) => updateLine(index, "description", event.target.value)} required />
            </label>
            <label className="field">
              Quantity
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={line.quantity}
                onChange={(event) => updateLine(index, "quantity", event.target.value)}
                required
              />
            </label>
            <label className="field">
              Unit amount
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={line.unit_amount}
                onChange={(event) => updateLine(index, "unit_amount", event.target.value)}
                required
              />
            </label>
            <button
              className="secondary"
              type="button"
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
        >
          Add line
        </button>
        {error ? <p className="error">{error}</p> : null}
        <button className="primary" type="submit">
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
