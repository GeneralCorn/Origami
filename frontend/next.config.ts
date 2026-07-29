import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: "/Origami",
  assetPrefix: "/Origami",
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  reactCompiler: true,
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
