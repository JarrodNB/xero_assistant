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
  ) {
    super(message);
  }
}

/**
 * Send a JSON request and return the parsed body.
 */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const text = await response.text();
  const body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
  if (!response.ok) {
    const what = String(body.what ?? "Request failed");
    throw new ApiRequestError(what, String(body.why ?? ""), String(body.next_step ?? ""));
  }
  return body as T;
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
