/**
 * Purpose: Proxy browser API calls to the FastAPI service, and poll the mounted source tree in development.
 *
 * Public API:
 * - nextConfig
 */

import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";

type WebpackSetup = NonNullable<NextConfig["webpack"]>;

/**
 * Send `/api/backend` calls to the FastAPI service.
 */
async function rewrites() {
  return [
    {
      source: "/api/backend/:path*",
      destination: `${backendUrl}/:path*`,
    },
  ];
}

/**
 * Poll for saves. The repo is bind-mounted from Windows, which does not emit file events in the container.
 */
const watchMountedSource: WebpackSetup = (config, { dev }) => {
  if (dev) {
    config.watchOptions = {
      poll: 1000,
      aggregateTimeout: 300,
    };
  }
  return config;
};

const nextConfig: NextConfig = {
  rewrites,
  webpack: watchMountedSource,
};

export default nextConfig;
