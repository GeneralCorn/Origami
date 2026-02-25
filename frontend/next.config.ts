import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    return [
      {
        source: "/chat-:id",
        destination: "/c/:id",
      },
    ];
  },
};

export default nextConfig;
