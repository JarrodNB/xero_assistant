/**
 * Purpose: Streaming chat with one confirm or deny card per proposed write.
 *
 * Public API:
 * - ChatPanel
 */

"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { FormEvent, useEffect, useState } from "react";
import { ApiRequestError, apiRequest } from "../lib/api";
import { ProposedAction } from "../lib/types";

type ChatPart = {
  type: string;
  text?: string;
  state?: string;
  output?: unknown;
};

type ChatMessage = {
  id: string;
  role: string;
  parts?: ChatPart[];
};

type ProposalField = {
  key: string;
  label: string;
  value: string;
};

const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  email: "Email",
  contact_name: "Contact",
  invoice_number: "Invoice",
  reference: "Reference",
  due_date: "Due date",
};

const FIELD_ORDER = ["name", "email", "contact_name", "invoice_number", "reference", "due_date", "line_items"];

type OptionalField = {
  key: string;
  label: string;
  inputType: string;
  placeholder?: string;
  hint?: string;
};

const OPTIONAL_FIELDS: Record<string, OptionalField[]> = {
  create_contact: [{ key: "email", label: "Email", inputType: "email", placeholder: "Optional" }],
  create_invoice: [
    { key: "reference", label: "Reference", inputType: "text", placeholder: "Optional" },
    { key: "due_date", label: "Due date", inputType: "date", hint: "Blank means 14 days from today." },
  ],
};

/**
 * Return a stable conversation id for this browser tab.
 */
function conversationId(): string {
  const existing = window.sessionStorage.getItem("ledger-conversation-id");
  if (existing) {
    return existing;
  }
  const created = crypto.randomUUID();
  window.sessionStorage.setItem("ledger-conversation-id", created);
  return created;
}

/**
 * Read a proposed action out of a tool result.
 */
function asProposal(output: unknown): ProposedAction | null {
  if (!output || typeof output !== "object") {
    return null;
  }
  const record = output as Partial<ProposedAction>;
  if (record.kind !== "proposed_action" || !record.action_id) {
    return null;
  }
  return record as ProposedAction;
}

/**
 * Join the text parts of one message.
 */
function messageText(message: ChatMessage): string {
  return (message.parts ?? [])
    .filter((part) => part.type === "text" && part.text)
    .map((part) => part.text ?? "")
    .join("\n");
}

/**
 * Hide confirm and deny prompts that are only for the model.
 */
function isInternalTurn(message: ChatMessage): boolean {
  if (message.role !== "user") {
    return false;
  }
  const text = messageText(message).trim();
  return text.startsWith("The user confirmed action ") || text.startsWith("The user denied action ");
}

/**
 * Return whether a payload value should appear on the card.
 */
function present(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

/**
 * Turn a payload key into a short label.
 */
function labelFromKey(key: string): string {
  const words = key.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Format one invoice line for the confirmation card.
 */
function lineSummary(item: unknown): string {
  if (!item || typeof item !== "object") {
    return "";
  }
  const line = item as Record<string, unknown>;
  const description = present(line.description) ? String(line.description) : "";
  const quantity = present(line.quantity) ? String(line.quantity) : "";
  const amount = present(line.unit_amount) ? String(line.unit_amount) : "";
  if (description && quantity && amount) {
    return `${description} · ${quantity} × ${amount}`;
  }
  return [description, quantity, amount].filter((part) => part.length > 0).join(" · ");
}

/**
 * List the fields that will be written, skipping empty values.
 */
function proposalFields(payload: Record<string, unknown>): ProposalField[] {
  const keys = [
    ...FIELD_ORDER.filter((key) => key in payload),
    ...Object.keys(payload).filter((key) => !FIELD_ORDER.includes(key)),
  ];
  const fields: ProposalField[] = [];
  for (const key of keys) {
    const value = payload[key];
    if (!present(value)) {
      continue;
    }
    if (key === "line_items" && Array.isArray(value)) {
      const lines = value.map((item) => lineSummary(item)).filter((line) => line.length > 0);
      if (lines.length > 0) {
        fields.push({ key, label: "Lines", value: lines.join("\n") });
      }
      continue;
    }
    if (typeof value === "object") {
      continue;
    }
    fields.push({ key, label: FIELD_LABELS[key] ?? labelFromKey(key), value: String(value) });
  }
  return fields;
}

/**
 * Return the optional fields a create card can edit.
 */
function optionalFields(actionType: string): OptionalField[] {
  return OPTIONAL_FIELDS[actionType] ?? [];
}

/**
 * Read one payload value as text for an input.
 */
function payloadText(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return present(value) ? String(value) : "";
}

/**
 * Start a card's optional inputs from the proposed payload.
 */
function optionalDraft(proposal: ProposedAction): Record<string, string> {
  const payload = proposal.payload ?? {};
  const draft: Record<string, string> = {};
  for (const field of optionalFields(proposal.action_type)) {
    draft[field.key] = payloadText(payload, field.key);
  }
  return draft;
}

/**
 * Build the confirm body from the optional fields on one card.
 */
function confirmOverrides(proposal: ProposedAction, values: Record<string, string>): Record<string, string> {
  const body: Record<string, string> = {};
  for (const field of optionalFields(proposal.action_type)) {
    body[field.key] = values[field.key] ?? payloadText(proposal.payload ?? {}, field.key);
  }
  return body;
}

/**
 * Preview the confirmation sentence from the optional fields being edited.
 */
function previewSummary(proposal: ProposedAction, values: Record<string, string>): string {
  const payload = proposal.payload ?? {};
  if (proposal.action_type === "create_contact" && typeof payload.name === "string") {
    const email = (values.email ?? "").trim();
    return email ? `Create contact ${payload.name} with email ${email}.` : `Create contact ${payload.name}.`;
  }
  if (proposal.action_type === "create_invoice") {
    const base = invoiceAmountSentence(payload);
    if (!base) {
      return proposal.summary;
    }
    const extras: string[] = [];
    const reference = (values.reference ?? "").trim();
    const due = (values.due_date ?? "").trim();
    if (reference) {
      extras.push(`reference ${reference}`);
    }
    if (due) {
      extras.push(`due ${due}`);
    }
    return extras.length > 0 ? `${base} with ${extras.join(" and ")}.` : `${base}.`;
  }
  return proposal.summary;
}

/**
 * Return the invoice sentence without optional reference or due date.
 */
function invoiceAmountSentence(payload: Record<string, unknown>): string | null {
  if (typeof payload.contact_name !== "string" || !Array.isArray(payload.line_items)) {
    return null;
  }
  let amount = 0;
  for (const item of payload.line_items) {
    if (!item || typeof item !== "object") {
      return null;
    }
    const line = item as Record<string, unknown>;
    const quantity = Number(line.quantity);
    const unitAmount = Number(line.unit_amount);
    if (!Number.isFinite(quantity) || !Number.isFinite(unitAmount)) {
      return null;
    }
    amount += quantity * unitAmount;
  }
  return `Create an authorised invoice for ${payload.contact_name} for ${amount.toFixed(2)}`;
}

/**
 * Stream the assistant and confirm each proposed write on its own.
 */
export function ChatPanel() {
  const [id, setId] = useState<string | null>(null);

  useEffect(() => {
    setId(conversationId());
  }, []);

  if (!id) {
    return <p className="muted">Loading chat…</p>;
  }

  return <ChatSession conversation={id} />;
}

/**
 * Stream one conversation after its id is known in the browser.
 */
function ChatSession({ conversation }: { conversation: string }) {
  const { messages, sendMessage, status } = useChat({
    id: conversation,
    transport: new DefaultChatTransport({
      api: "/api/backend/chat",
      headers: { "X-Conversation-Id": conversation },
      fetch: (input, init) => fetch(input, { ...init, credentials: "include" }),
    }),
  });
  const [draft, setDraft] = useState("");
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, Record<string, string>>>({});
  const [cardErrors, setCardErrors] = useState<Record<string, string>>({});
  const busy = status === "submitted" || status === "streaming";
  const visible = (messages as ChatMessage[]).filter((message) => !isInternalTurn(message));
  const lastMessageId = messages.length > 0 ? (messages[messages.length - 1] as ChatMessage).id : "";

  /**
   * Send the typed message.
   */
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) {
      return;
    }
    setDraft("");
    await sendMessage({ text });
  }

  /**
   * Return the optional field values for one card, including unsaved edits.
   */
  function valuesFor(proposal: ProposedAction): Record<string, string> {
    return fieldDrafts[proposal.action_id] ?? optionalDraft(proposal);
  }

  /**
   * Keep one optional field on a pending card.
   */
  function setOptionalValue(proposal: ProposedAction, key: string, value: string) {
    setFieldDrafts((current) => ({
      ...current,
      [proposal.action_id]: { ...(current[proposal.action_id] ?? optionalDraft(proposal)), [key]: value },
    }));
    setCardErrors((current) => {
      if (!current[proposal.action_id]) {
        return current;
      }
      const next = { ...current };
      delete next[proposal.action_id];
      return next;
    });
  }

  /**
   * Confirm or deny one proposal, then ask the assistant to explain the result.
   */
  async function decide(proposal: ProposedAction, decision: "confirm" | "deny") {
    const values = valuesFor(proposal);
    let narration: string;
    try {
      const result = await apiRequest<Record<string, unknown>>(`/api/backend/actions/${proposal.action_id}/${decision}`, {
        method: "POST",
        body: decision === "confirm" ? JSON.stringify(confirmOverrides(proposal, values)) : undefined,
      });
      setStatuses((current) => ({ ...current, [proposal.action_id]: String(result.status ?? decision) }));
      setCardErrors((current) => {
        if (!current[proposal.action_id]) {
          return current;
        }
        const next = { ...current };
        delete next[proposal.action_id];
        return next;
      });
      narration =
        decision === "confirm"
          ? `The user confirmed action ${proposal.action_id}. Execution result: ${JSON.stringify(result)}. Explain what happened in plain language. Do not repeat this message or the action id. Do not propose another action unless the result says another step is required.`
          : `The user denied action ${proposal.action_id}: ${proposal.summary}. Acknowledge that in plain language and do not repeat this message or the action id. Do not execute it.`;
    } catch (caught) {
      const message = caught instanceof ApiRequestError ? `${caught.message}. ${caught.nextStep}` : "The action could not be finished.";
      if (caught instanceof ApiRequestError && caught.statusCode === 422) {
        setCardErrors((current) => ({ ...current, [proposal.action_id]: message }));
        return;
      }
      setStatuses((current) => ({ ...current, [proposal.action_id]: "failed" }));
      narration = `The user confirmed action ${proposal.action_id}, but execution failed: ${message}. Explain the failure in plain language. Do not repeat this message or the action id.`;
    }
    try {
      await sendMessage({ text: narration });
    } catch {
      // The follow-up is for the model. Leave it off the screen if the request fails.
    }
  }

  return (
    <>
      <div className="messages">
        {visible.map((message) => {
          const streaming = busy && message.id === lastMessageId;
          const texts = (message.parts ?? []).filter((part) => part.type === "text" && part.text);
          const proposals = streaming
            ? []
            : (message.parts ?? []).flatMap((part) => {
                const proposal = asProposal(part.output);
                return proposal ? [proposal] : [];
              });
          return (
            <div key={message.id}>
              {texts.map((part, index) => (
                <p className={`bubble ${message.role}`} key={`${message.id}-text-${index}`}>
                  {part.text}
                </p>
              ))}
              {proposals.map((proposal) => {
                const actionStatus = statuses[proposal.action_id] ?? proposal.status;
                const pending = actionStatus === "pending";
                const values = valuesFor(proposal);
                const editable = new Set(optionalFields(proposal.action_type).map((field) => field.key));
                const fields = proposalFields(proposal.payload ?? {}).filter((field) => !editable.has(field.key));
                const optional = optionalFields(proposal.action_type).filter((field) => pending || present(values[field.key]));
                return (
                  <div className="proposal" key={proposal.action_id}>
                    <strong>{previewSummary(proposal, values)}</strong>
                    {fields.length > 0 || optional.length > 0 ? (
                      <dl>
                        {fields.map((field) => (
                          <div className="proposal-field" key={field.key}>
                            <dt>{field.label}</dt>
                            <dd>{field.value}</dd>
                          </div>
                        ))}
                        {optional.map((field) => (
                          <div className="proposal-field" key={field.key}>
                            <dt>{field.label}</dt>
                            <dd>
                              {pending ? (
                                <>
                                  <input
                                    type={field.inputType}
                                    value={values[field.key] ?? ""}
                                    aria-label={field.label}
                                    placeholder={field.placeholder}
                                    onChange={(event) => setOptionalValue(proposal, field.key, event.target.value)}
                                  />
                                  {field.hint ? <span className="muted proposal-hint">{field.hint}</span> : null}
                                </>
                              ) : (
                                values[field.key]
                              )}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : null}
                    {cardErrors[proposal.action_id] ? <p className="error">{cardErrors[proposal.action_id]}</p> : null}
                    <span className="muted">{actionStatus}</span>
                    {pending ? (
                      <div className="actions">
                        <button className="primary" type="button" onClick={() => void decide(proposal, "confirm")}>
                          Confirm
                        </button>
                        <button className="secondary" type="button" onClick={() => void decide(proposal, "deny")}>
                          Deny
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
      <form className="chat-form" onSubmit={(event) => void onSubmit(event)}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Can you send an invoice to Bob's Construction for $55?"
          disabled={busy}
        />
        <button className="primary" type="submit" disabled={busy}>
          Send
        </button>
      </form>
    </>
  );
}
