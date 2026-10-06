/**
 * Purpose: Chat page that renders the streaming assistant.
 *
 * Public API:
 * - ChatPage
 */

"use client";

import { ChatPanel } from "../../../components/ChatPanel";

/**
 * Open the invoice chat.
 */
export default function ChatPage() {
  return (
    <section className="chat-layout">
      <div className="page-header">
        <h1>Chat</h1>
      </div>
      <ChatPanel />
    </section>
  );
}
