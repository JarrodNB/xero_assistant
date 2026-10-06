/**
 * Purpose: Chat page with stored conversation history beside the thread.
 *
 * Public API:
 * - ChatPage
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { ChatPanel } from "../../../components/ChatPanel";
import { apiRequest } from "../../../lib/api";
import { ConversationSummary, ProposedAction, StoredMessage } from "../../../lib/types";

const OPEN_CONVERSATION_KEY = "ledger-open-conversation";

type ConversationDetail = {
  id: string;
  messages: StoredMessage[];
  actions: ProposedAction[];
};

type OpenThread = {
  id: string;
  messages: StoredMessage[];
  actions: ProposedAction[];
};

/**
 * Open the invoice chat and its stored threads.
 */
export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [thread, setThread] = useState<OpenThread | null>(null);
  const [error, setError] = useState("");

  /**
   * Reload the history list without changing the open thread.
   */
  const refreshList = useCallback(async () => {
    const body = await apiRequest<{ conversations: ConversationSummary[] }>("/api/backend/conversations");
    setConversations(body.conversations);
  }, []);

  /**
   * Load one stored thread and remember it for the next visit.
   */
  const openStoredThread = useCallback(async (id: string) => {
    const detail = await apiRequest<ConversationDetail>(`/api/backend/conversations/${id}`);
    setThread({ id: detail.id, messages: detail.messages, actions: detail.actions });
    window.localStorage.setItem(OPEN_CONVERSATION_KEY, detail.id);
    setError("");
  }, []);

  /**
   * Start a blank thread. It joins the list after the first message.
   */
  const startNewChat = useCallback(() => {
    const id = crypto.randomUUID();
    setThread({ id, messages: [], actions: [] });
    window.localStorage.setItem(OPEN_CONVERSATION_KEY, id);
    setError("");
  }, []);

  useEffect(() => {
    let cancelled = false;

    /**
     * Open the last thread, otherwise the newest, otherwise a new chat.
     */
    async function load() {
      try {
        const body = await apiRequest<{ conversations: ConversationSummary[] }>("/api/backend/conversations");
        if (cancelled) {
          return;
        }
        setConversations(body.conversations);
        const saved = window.localStorage.getItem(OPEN_CONVERSATION_KEY);
        const known = saved !== null && body.conversations.some((item) => item.id === saved);
        if (known && saved) {
          const detail = await apiRequest<ConversationDetail>(`/api/backend/conversations/${saved}`);
          if (!cancelled) {
            setThread({ id: detail.id, messages: detail.messages, actions: detail.actions });
          }
          return;
        }
        if (body.conversations.length > 0) {
          const newest = body.conversations[0];
          const detail = await apiRequest<ConversationDetail>(`/api/backend/conversations/${newest.id}`);
          if (cancelled) {
            return;
          }
          setThread({ id: detail.id, messages: detail.messages, actions: detail.actions });
          window.localStorage.setItem(OPEN_CONVERSATION_KEY, detail.id);
          return;
        }
        const id = crypto.randomUUID();
        if (cancelled) {
          return;
        }
        setThread({ id, messages: [], actions: [] });
        window.localStorage.setItem(OPEN_CONVERSATION_KEY, id);
      } catch {
        if (!cancelled) {
          setError("Conversations could not be loaded.");
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Switch to a stored thread.
   */
  async function selectConversation(id: string) {
    if (thread?.id === id) {
      return;
    }
    try {
      await openStoredThread(id);
    } catch {
      setError("That conversation could not be opened.");
    }
  }

  /**
   * Refresh the list after a message is sent.
   */
  function onActivity() {
    void refreshList().catch(() => setError("Conversations could not be loaded."));
  }

  const draftingNew = thread !== null && !conversations.some((item) => item.id === thread.id);

  return (
    <section className="chat-layout">
      <div className="page-header">
        <h1>Chat</h1>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="chat-workspace">
        <div className="conversation-list">
          <button className={draftingNew ? "primary" : "secondary"} type="button" onClick={startNewChat}>
            New chat
          </button>
          {conversations.map((item) => (
            <button
              className={thread?.id === item.id ? "conversation-row active" : "conversation-row"}
              type="button"
              key={item.id}
              onClick={() => void selectConversation(item.id)}
            >
              <span>{item.preview || "New conversation"}</span>
            </button>
          ))}
        </div>
        <div className="chat-thread">
          {thread ? (
            <ChatPanel
              key={thread.id}
              conversation={thread.id}
              transcript={thread.messages}
              historyActions={thread.actions}
              onActivity={onActivity}
            />
          ) : (
            <p className="muted">Loading chat…</p>
          )}
        </div>
      </div>
    </section>
  );
}
