/**
 * Purpose: Root document for the Xero assistant.
 *
 * Public API:
 * - RootLayout
 */

import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ledger",
  description: "Ledger is a financial assistant for a connected Xero demo company.",
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
