/**
 * Purpose: Build bounded, id-free outcome narration for the chat model.
 *
 * Public API:
 * - actionNarration
 */

/** Include only bounded outcome facts, never receipt ids, payloads, or diagnostics. */
export function actionNarration(decision: "confirm" | "deny", result: Record<string, unknown>): string {
  const status = ["pending", "executing", "executed", "failed", "unknown", "denied"].includes(String(result.status))
    ? String(result.status) : "unknown";
  let facts = "";
  if (status === "executed") {
    const invoice = result.invoice as Record<string, unknown> | undefined;
    const contact = result.contact as Record<string, unknown> | undefined;
    if (invoice && typeof invoice.invoice_number === "string") {
      facts = ` Invoice ${invoice.invoice_number.slice(0, 50)}.`;
      if (typeof invoice.total === "number" && Number.isFinite(invoice.total)) {
        facts += ` Total ${invoice.total.toFixed(2)} ${String(invoice.currency ?? "").slice(0, 8)}.`;
      }
    } else if (contact && typeof contact.name === "string") {
      facts = ` Contact ${contact.name.slice(0, 40)}.`;
    }
  }
  return `The user ${decision === "confirm" ? "confirmed" : "denied"} action with recorded status ${status}.${facts} Explain this status briefly. Do not propose another action.`;
}
