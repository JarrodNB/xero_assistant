/**
 * Purpose: Send the front door to chat.
 *
 * Public API:
 * - HomePage
 */

import { redirect } from "next/navigation";

/**
 * Open chat, which sends unsigned visitors to login.
 */
export default function HomePage() {
  redirect("/chat");
}
