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
  const [error, setError] = useState("");
  const busy = status === "submitted" || status === "streaming";

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
    setError("");
    await sendMessage({ text });
  }

  /**
   * Confirm or deny one proposal, then ask the assistant to explain the result.
   */
  async function decide(proposal: ProposedAction, decision: "confirm" | "deny") {
    setError("");
    try {
      const result = await apiRequest<Record<string, unknown>>(`/api/backend/actions/${proposal.action_id}/${decision}`, {
        method: "POST",
      });
      setStatuses((current) => ({ ...current, [proposal.action_id]: String(result.status ?? decision) }));
      const narration =
        decision === "confirm"
          ? `The user confirmed action ${proposal.action_id}. Execution result: ${JSON.stringify(result)}. Explain what happened. Do not propose another action unless the result says another step is required.`
          : `The user denied action ${proposal.action_id}: ${proposal.summary}. Acknowledge that and do not execute it.`;
      await sendMessage({ text: narration });
    } catch (caught) {
      const message = caught instanceof ApiRequestError ? `${caught.message}. ${caught.nextStep}` : "The action could not be finished.";
      setStatuses((current) => ({ ...current, [proposal.action_id]: "failed" }));
      setError(message);
      await sendMessage({
        text: `The user confirmed action ${proposal.action_id}, but execution failed: ${message}`,
      });
    }
  }

  return (
    <>
      <div className="messages">
        {(messages as ChatMessage[]).map((message) => (
          <div key={message.id}>
            {(message.parts ?? []).map((part, index) => {
              if (part.type === "text" && part.text) {
                return (
                  <p className={`bubble ${message.role}`} key={`${message.id}-${index}`}>
                    {part.text}
                  </p>
                );
              }
              const proposal = asProposal(part.output);
              if (!proposal) {
                return null;
              }
              const actionStatus = statuses[proposal.action_id] ?? proposal.status;
              return (
                <div className="proposal" key={proposal.action_id}>
                  <strong>{proposal.summary}</strong>
                  <span className="muted">{actionStatus}</span>
                  {actionStatus === "pending" ? (
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
        ))}
      </div>
      {error ? <p className="error">{error}</p> : null}
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
