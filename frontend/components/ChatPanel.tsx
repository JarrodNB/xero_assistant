/**
 * Purpose: Streaming chat with one confirm or deny card per proposed write.
 *
 * Public API:
 * - ChatPanel
 */

"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { FormEvent, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest } from "../lib/api";
import { ProposedAction, StoredMessage } from "../lib/types";

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

const NEAR_BOTTOM_PX = 48;
const STREAM_CHARACTERS_PER_TICK = 2;
const STREAM_TICK_MS = 30;

const OPTIONAL_FIELDS: Record<string, OptionalField[]> = {
  create_contact: [{ key: "email", label: "Email", inputType: "email", placeholder: "Optional" }],
  create_invoice: [
    { key: "reference", label: "Reference", inputType: "text", placeholder: "Optional" },
    { key: "due_date", label: "Due date", inputType: "date", hint: "Blank means 14 days from today." },
  ],
};

/**
 * Show a short label on a proposal status pill.
 */
function statusLabel(status: string): string {
  if (!status) {
    return status;
  }
  return status.charAt(0).toUpperCase() + status.slice(1);
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

type PacedTextProps = {
  active: boolean;
  messageId: string;
  onPacingChange: (messageId: string, pacing: boolean) => void;
  text: string;
};

/**
 * Reveal streamed text at a readable rate even when network chunks arrive quickly.
 */
function PacedText({ active, messageId, onPacingChange, text }: PacedTextProps) {
  const startedPaced = useRef(active);
  const target = useRef(text);
  const [visible, setVisible] = useState(active ? "" : text);
  target.current = text;
  const hasMore = visible.length < text.length;
  const stillMatches = text.startsWith(visible);

  useEffect(() => {
    if (active) {
      startedPaced.current = true;
    }
    if (!startedPaced.current) {
      setVisible(text);
      return;
    }
    if (!stillMatches) {
      setVisible(target.current);
      onPacingChange(messageId, false);
      return;
    }
    if (!hasMore) {
      onPacingChange(messageId, false);
      return;
    }
    onPacingChange(messageId, true);
    const timer = window.setTimeout(() => {
      setVisible(target.current.slice(0, visible.length + STREAM_CHARACTERS_PER_TICK));
    }, STREAM_TICK_MS);
    return () => window.clearTimeout(timer);
  }, [active, hasMore, messageId, onPacingChange, stillMatches, visible]);

  useEffect(
    () => () => {
      onPacingChange(messageId, false);
    },
    [messageId, onPacingChange],
  );

  return visible;
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
 * Place each stored action on the assistant reply that follows it.
 */
function groupHistoryActions(
  transcript: StoredMessage[],
  actions: ProposedAction[],
): { byMessageId: Record<string, ProposedAction[]>; trailing: ProposedAction[] } {
  const assistants = transcript.filter((message) => message.role === "assistant");
  const byMessageId: Record<string, ProposedAction[]> = {};
  const trailing: ProposedAction[] = [];
  const ordered = [...actions].sort((left, right) => (left.created_at ?? "").localeCompare(right.created_at ?? ""));
  for (const action of ordered) {
    const host = assistants.find((message) => message.created_at >= (action.created_at ?? ""));
    if (!host) {
      trailing.push(action);
      continue;
    }
    const bucket = byMessageId[host.id] ?? [];
    bucket.push(action);
    byMessageId[host.id] = bucket;
  }
  return { byMessageId, trailing };
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
 * Preview the confirmation sentence without echoing free-form reference edits.
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
    const due = (values.due_date ?? "").trim();
    return due ? `${base} with due ${due}.` : `${base}.`;
  }
  return proposal.summary;
}

/**
 * Return the element that actually scrolls the thread, if one does.
 */
function scrollParent(start: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = start;
  while (node) {
    if (node.scrollHeight - node.clientHeight > 1) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

/**
 * Return whether a scrollable element is already showing its latest content.
 */
function isNearBottom(list: HTMLElement): boolean {
  return list.scrollHeight - list.scrollTop - list.clientHeight <= NEAR_BOTTOM_PX;
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

type ChatPanelProps = {
  conversation: string;
  transcript: StoredMessage[];
  historyActions: ProposedAction[];
  onActivity: () => void;
};

/**
 * Stream the assistant and confirm each proposed write on its own.
 */
export function ChatPanel({ conversation, transcript, historyActions, onActivity }: ChatPanelProps) {
  return (
    <ChatSession
      conversation={conversation}
      transcript={transcript}
      historyActions={historyActions}
      onActivity={onActivity}
    />
  );
}

/**
 * Stream one conversation, including messages loaded from history.
 */
function ChatSession({ conversation, transcript, historyActions, onActivity }: ChatPanelProps) {
  const [seed] = useState(() =>
    transcript.map((message) => ({
      id: message.id,
      role: message.role as "user" | "assistant",
      parts: [{ type: "text" as const, text: message.content }],
    })),
  );
  const historyMessageIds = useRef(new Set(seed.map((message) => message.id)));
  const grouped = groupHistoryActions(transcript, historyActions);
  const { messages, sendMessage, status } = useChat({
    id: conversation,
    messages: seed,
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
  const [deciding, setDeciding] = useState(false);
  const [pacingIds, setPacingIds] = useState<Set<string>>(() => new Set());
  const listRef = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const decidingRef = useRef(false);
  const busy = status === "submitted" || status === "streaming";
  const visuallyBusy = busy || pacingIds.size > 0;
  const locked = visuallyBusy || deciding;
  const visible = (messages as ChatMessage[]).filter((message) => !isInternalTurn(message));
  const lastMessageId = messages.length > 0 ? (messages[messages.length - 1] as ChatMessage).id : "";

  /**
   * Track replies that are still being revealed after their network stream completes.
   */
  const setMessagePacing = useCallback((messageId: string, pacing: boolean) => {
    setPacingIds((current) => {
      const hasMessage = current.has(messageId);
      if (hasMessage === pacing) {
        return current;
      }
      const updated = new Set(current);
      if (pacing) {
        updated.add(messageId);
      } else {
        updated.delete(messageId);
      }
      return updated;
    });
  }, []);

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) {
      return;
    }
    const scroller = scrollParent(list) ?? list;
    if (followLatest.current) {
      scroller.scrollTop = scroller.scrollHeight;
    }

    /**
     * Stop following when the reader moves up, and resume near the latest message.
     */
    function onScroll() {
      followLatest.current = isNearBottom(scroller);
    }

    scroller.addEventListener("scroll", onScroll);
    return () => scroller.removeEventListener("scroll", onScroll);
  });

  /**
   * Send the typed message.
   */
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) {
      return;
    }
    followLatest.current = true;
    setDraft("");
    try {
      await sendMessage({ text });
    } finally {
      onActivity();
    }
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
    if (busy || decidingRef.current) {
      return;
    }
    decidingRef.current = true;
    setDeciding(true);
    const values = valuesFor(proposal);
    let narration: string;
    try {
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
      followLatest.current = true;
      try {
        await sendMessage({ text: narration });
      } catch {
        // The follow-up is for the model. Leave it off the screen if the request fails.
      }
    } finally {
      decidingRef.current = false;
      setDeciding(false);
    }
  }

  /**
   * Render one confirmation card.
   */
  function renderProposal(proposal: ProposedAction, cardLocked: boolean) {
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
                        disabled={cardLocked}
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
        <span className={`status status-${actionStatus.toLowerCase()}`}>{statusLabel(actionStatus)}</span>
        {pending ? (
          <div className="actions">
            <button className="primary" type="button" disabled={cardLocked} onClick={() => void decide(proposal, "confirm")}>
              Confirm
            </button>
            <button className="secondary" type="button" disabled={cardLocked} onClick={() => void decide(proposal, "deny")}>
              Deny
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <div className="messages" ref={listRef}>
        {visible.map((message) => {
          const streaming = busy && message.id === lastMessageId;
          const newAssistantReply =
            message.role === "assistant" &&
            message.id === lastMessageId &&
            !historyMessageIds.current.has(message.id);
          const pacing = [...pacingIds].some((id) => id.startsWith(`${message.id}-text-`));
          const texts = (message.parts ?? []).filter((part) => part.type === "text" && part.text);
          const proposals = streaming || pacing
            ? []
            : (message.parts ?? []).flatMap((part) => {
                const proposal = asProposal(part.output);
                return proposal ? [proposal] : [];
              });
          return (
            <div className="message-group" key={message.id}>
              {texts.map((part, index) => (
                <p className={`bubble ${message.role}`} key={`${message.id}-text-${index}`}>
                  {message.role === "assistant" ? (
                    <PacedText
                      active={newAssistantReply}
                      messageId={`${message.id}-text-${index}`}
                      onPacingChange={setMessagePacing}
                      text={part.text ?? ""}
                    />
                  ) : (
                    part.text
                  )}
                </p>
              ))}
              {proposals.map((proposal) => renderProposal(proposal, locked))}
              {(grouped.byMessageId[message.id] ?? []).map((proposal) => renderProposal(proposal, locked))}
            </div>
          );
        })}
        {grouped.trailing.map((proposal) => renderProposal(proposal, locked))}
      </div>
      <form className="chat-form" onSubmit={(event) => void onSubmit(event)}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Can you send an invoice to Bob's Construction for $55?"
          disabled={visuallyBusy}
        />
        <button className="primary" type="submit" disabled={visuallyBusy}>
          Send
        </button>
      </form>
    </>
  );
}
