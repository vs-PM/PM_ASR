// next.config.ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Прокси всего /api/v1/* на локальный бекенд (порт 7000 НЕ нужен наружу)
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: "http://127.0.0.1:7000/api/v1/:path*" },
    ];
  },
};

export default nextConfig;
