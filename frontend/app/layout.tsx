/**
 * Purpose: Root document for the invoice assistant.
 *
 * Public API:
 * - RootLayout
 */

import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ledger",
  description: "Invoice assistant for a Xero demo company.",
};

/**
 * Render the shared HTML shell.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
