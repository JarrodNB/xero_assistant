/**
 * Purpose: Login page for the shared interviewer account.
 *
 * Public API:
 * - LoginPage
 */

"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiRequestError, apiRequest } from "../../lib/api";

/**
 * Collect the shared username and password and start a session.
 */
export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  /**
   * Submit the login form.
   */
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest("/api/backend/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      router.push("/invoices");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Login failed");
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <h1>Ledger</h1>
        <p className="muted">Sign in with the username and password you were given.</p>
        <form onSubmit={onSubmit}>
          <label className="field">
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label className="field">
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="error">{error}</p> : null}
          <button className="primary" type="submit">
            Sign in
          </button>
        </form>
      </section>
    </main>
  );
}
