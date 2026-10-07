/**
 * Purpose: Contact list with a name filter.
 *
 * Public API:
 * - ContactListPage
 */

"use client";

import { useEffect, useState } from "react";
import { ApiRequestError, apiRequest } from "../../../lib/api";
import { Contact } from "../../../lib/types";

/**
 * Show the demo company's contacts.
 */
export default function ContactListPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    /**
     * Load contacts for the current name filter.
     */
    async function load() {
      const params = new URLSearchParams();
      if (name) {
        params.set("name", name);
      }
      const query = params.toString();
      try {
        const body = await apiRequest<{ contacts: Contact[] }>(`/api/backend/contacts${query ? `?${query}` : ""}`);
        setContacts(body.contacts);
        setError("");
      } catch (caught) {
        const message = caught instanceof ApiRequestError ? `${caught.message}. ${caught.nextStep}` : "Contacts could not be loaded.";
        setError(message);
      }
    }
    void load();
  }, [name]);

  return (
    <section>
      <div className="page-header">
        <h1>Contacts</h1>
      </div>
      <div className="filters panel">
        <label className="field">
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Juvy" />
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div className="panel table-panel">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
            </tr>
          </thead>
          <tbody>
            {contacts.length === 0 ? (
              <tr>
                <td className="empty" colSpan={2}>
                  No contacts match this name.
                </td>
              </tr>
            ) : (
              contacts.map((contact) => (
                <tr key={`${contact.name}-${contact.email ?? ""}`}>
                  <td>{contact.name}</td>
                  <td>{contact.email ? contact.email : <span className="muted">No email</span>}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
