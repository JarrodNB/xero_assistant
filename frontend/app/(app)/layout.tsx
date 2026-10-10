/**
 * Purpose: Signed-in shell for Ledger's current Xero capabilities.
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
 * Keep all application pages behind the interviewer session.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [xeroConnected, setXeroConnected] = useState(true);
  const [xeroTenantName, setXeroTenantName] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    /**
     * Send unsigned visitors to the login page.
     */
    async function checkSession() {
      const status = await fetchSession();
      if (!status.authenticated) {
        router.replace("/login");
        return;
      }
      setXeroConnected(status.xeroConnected);
      setXeroTenantName(status.xeroTenantName);
      const params = new URLSearchParams(window.location.search);
      if (params.get("xero") === "denied") {
        setNotice("Xero authorisation was not completed. Connect again and choose the Demo Company.");
      } else if (params.get("xero") === "failed") {
        setNotice("Xero did not return a connection. Check the redirect URI in the Xero app, then try again.");
      } else if (params.get("xero") === "connected") {
        setNotice(`Connected to ${status.xeroTenantName || "Xero"}.`);
      }
      setReady(true);
    }
    void checkSession();
  }, [pathname, router]);

  /**
   * End the session and return to the login page.
   */
  async function logout() {
    await apiRequest("/api/backend/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  if (!ready) {
    return <p className="loading-screen muted">Checking session…</p>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <p className="wordmark">Ledger</p>
          {xeroConnected && xeroTenantName ? <p className="tenant-label">{xeroTenantName}</p> : null}
        </div>
        <nav>
          <Link className={pathname.startsWith("/invoices") ? "active" : ""} href="/invoices">
            Invoices
          </Link>
          <Link className={pathname.startsWith("/contacts") ? "active" : ""} href="/contacts">
            Contacts
          </Link>
          <Link className={pathname.startsWith("/chat") ? "active" : ""} href="/chat">
            Chat
          </Link>
        </nav>
        <button className="logout" type="button" onClick={() => void logout()}>
          Log out
        </button>
      </aside>
      <main className="main">
        {notice ? <p className={notice.startsWith("Connected") ? "banner banner-ok" : "banner banner-error"}>{notice}</p> : null}
        {xeroConnected ? null : (
          <div className="connect-banner panel">
            <p>Connect the Xero Demo Company to use Ledger.</p>
            <a className="primary" href="/api/xero/start">
              Connect Xero
            </a>
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
