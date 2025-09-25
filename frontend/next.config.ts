// next.config.ts
import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  async rewrites() {
    if (isProd) return []; // в проде проксирует nginx-proxy
    return [
      { source: "/api/v1/:path*", destination: "http://127.0.0.1:7000/api/v1/:path*" },
    ];
  },
  reactStrictMode: true,
};

export default nextConfig;
