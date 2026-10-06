/**
 * Purpose: Proxy browser API calls to the FastAPI service.
 *
 * Public API:
 * - nextConfig
 */

import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
