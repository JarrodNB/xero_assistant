/**
 * Purpose: Browser calls to the FastAPI service through the Next.js proxy.
 *
 * Public API:
 * - ApiRequestError
 * - SessionStatus
 * - apiRequest
 * - fetchSession
 */

export class ApiRequestError extends Error {
  /** Store the explanation returned by the API. */
  constructor(
    message: string,
    readonly why: string,
    readonly nextStep: string,
    readonly statusCode: number = 0,
    readonly outcomeUnknown: boolean = false,
  ) {
    super(message);
  }
}

/**
 * Send a JSON request and return the parsed body.
 */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  const method = (init?.method ?? "GET").toUpperCase();
  const isEditorWrite = ["POST", "PUT"].includes(method) && /^\/api\/backend\/(contacts|invoices)(\/|$)/.test(path);
  let receiptKey: string | undefined;
  if (isEditorWrite && !headers.has("X-Write-Id")) {
    receiptKey = await editorReceiptKey(method, path, String(init?.body ?? ""));
    const requestId = sessionStorage.getItem(receiptKey) ?? crypto.randomUUID();
    sessionStorage.setItem(receiptKey, requestId);
    headers.set("X-Write-Id", requestId);
  }
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiRequestError("Request could not be completed", "No reliable response was received.", isEditorWrite ? "Check Xero before starting another write. Retrying the same values will check the saved receipt." : "Check the connection and try again.", 0, isEditorWrite);
  }
  let body: Record<string, unknown>;
  try {
    const text = await response.text();
    body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
    if (body === null || typeof body !== "object" || Array.isArray(body)) {
      throw new Error("Expected a JSON object.");
    }
  } catch {
    throw new ApiRequestError("Invalid server response", "The result could not be read.", isEditorWrite ? "Check Xero before starting another write." : "Try again.", response.status, isEditorWrite);
  }
  const unknown = body.outcome_unknown === true || (isEditorWrite && response.status >= 500);
  if (receiptKey && (response.ok || (!unknown && body.what !== "Write is still executing"))) {
    sessionStorage.removeItem(receiptKey);
  }
  if (!response.ok) {
    const what = String(body.what ?? "Request failed");
    throw new ApiRequestError(what, String(body.why ?? ""), String(body.next_step ?? ""), response.status, unknown);
  }
  return body as T;
}

/** Retain a retry identifier in this tab without storing the submitted personal values. */
async function editorReceiptKey(method: string, path: string, body: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify([method, path, body])));
  const fingerprint = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
  return `ledger-write:${fingerprint}`;
}

export type SessionStatus = {
  authenticated: boolean;
  xeroConnected: boolean;
  xeroTenantName: string;
};

/**
 * Return the interviewer session and whether Xero is connected.
 */
export async function fetchSession(): Promise<SessionStatus> {
  const response = await fetch("/api/backend/auth/session", { credentials: "include" });
  if (!response.ok) {
    return { authenticated: false, xeroConnected: false, xeroTenantName: "" };
  }
  const body = (await response.json()) as {
    authenticated?: boolean;
    xero_connected?: boolean;
    xero_tenant_name?: string;
  };
  return {
    authenticated: body.authenticated === true,
    xeroConnected: body.xero_connected === true,
    xeroTenantName: body.xero_tenant_name ?? "",
  };
}
