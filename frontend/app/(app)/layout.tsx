/**
 * Purpose: Signed-in shell with navigation between invoices and chat.
 *
 * Public API:
 * - AppShell
 */

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { apiRequest, fetchSession } from "../../lib/api";

/**
 * Keep invoice and chat pages behind the interviewer session.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    /**
     * Send unsigned visitors to the login page.
     */
    async function checkSession() {
      const signedIn = await fetchSession();
      if (!signedIn) {
        router.replace("/login");
        return;
      }
      setReady(true);
    }
    void checkSession();
  }, [router]);

  /**
   * End the session and return to the login page.
   */
  async function logout() {
    await apiRequest("/api/backend/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  if (!ready) {
    return <p className="main muted">Checking session…</p>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <p className="wordmark">Ledger</p>
        <nav>
          <Link className={pathname.startsWith("/invoices") ? "active" : ""} href="/invoices">
            Invoices
          </Link>
          <Link className={pathname.startsWith("/chat") ? "active" : ""} href="/chat">
            Chat
          </Link>
        </nav>
        <button className="logout" type="button" onClick={() => void logout()}>
          Log out
        </button>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
