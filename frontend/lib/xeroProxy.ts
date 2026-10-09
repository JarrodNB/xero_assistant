/**
 * Purpose: Pass Xero OAuth redirects from FastAPI back to the browser.
 *
 * Public API:
 * - proxyXeroRedirect
 */

import { NextRequest, NextResponse } from "next/server";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";

/**
 * Use the browser host. Next reports 0.0.0.0 when the server listens on all interfaces.
 */
function browserOrigin(request: NextRequest): string {
  const forwardedHost = request.headers.get("x-forwarded-host");
  const host = (forwardedHost ?? request.headers.get("host") ?? "localhost:3001").replace(/^0\.0\.0\.0/, "localhost");
  const proto = request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.replace(":", "");
  return `${proto}://${host}`;
}

/**
 * Call a FastAPI OAuth route and return its redirect without following it.
 */
export async function proxyXeroRedirect(request: NextRequest, path: string): Promise<NextResponse> {
  const target = new URL(path, backendUrl);
  target.search = request.nextUrl.search;
  const response = await fetch(target, {
    headers: { cookie: request.headers.get("cookie") ?? "" },
    redirect: "manual",
  });
  const location = response.headers.get("location");
  if (!location) {
    return new NextResponse(await response.text(), { status: response.status });
  }
  const redirected = NextResponse.redirect(new URL(location, `${browserOrigin(request)}/`), 302);
  for (const cookie of response.headers.getSetCookie()) {
    redirected.headers.append("set-cookie", cookie);
  }
  return redirected;
}
