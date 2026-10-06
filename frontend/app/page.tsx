/**
 * Purpose: Send the front door to the invoice list.
 *
 * Public API:
 * - HomePage
 */

import { redirect } from "next/navigation";

/**
 * Open the invoice list, which sends unsigned visitors to login.
 */
export default function HomePage() {
  redirect("/invoices");
}
