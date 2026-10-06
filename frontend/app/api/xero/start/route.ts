/**
 * Purpose: Send the browser to the Xero consent screen.
 *
 * Public API:
 * - GET
 */

import { NextRequest } from "next/server";
import { proxyXeroRedirect } from "../../../../lib/xeroProxy";

/**
 * Start the Xero authorisation-code flow.
 */
export function GET(request: NextRequest) {
  return proxyXeroRedirect(request, "/auth/xero/start");
}
