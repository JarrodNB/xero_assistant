/**
 * Purpose: Receive the Xero authorisation code and return the app redirect.
 *
 * Public API:
 * - GET
 */

import { NextRequest } from "next/server";
import { proxyXeroRedirect } from "../../../../lib/xeroProxy";

/**
 * Finish the Xero authorisation-code flow.
 */
export function GET(request: NextRequest) {
  return proxyXeroRedirect(request, "/auth/xero/callback");
}
