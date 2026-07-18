import type { NextConfig } from "next";

const api = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${api}/api/v1/:path*` },
      { source: "/health/api", destination: `${api}/health` },
    ];
  },
};

export default nextConfig;
