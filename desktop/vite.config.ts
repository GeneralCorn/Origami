import fs from "node:fs";
import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const RENDERER_OUT_DIR = path.resolve(__dirname, "dist/renderer");

// The CodeMirror spike's fixture images live in public/ so the dev route can
// reference them by URL, and Vite copies public/ verbatim. The dev-route guard
// keeps the JS out of a production bundle but says nothing about those files,
// so they would otherwise ship to every install.
function dropSpikeFixtures(): Plugin {
  return {
    name: "drop-spike-fixtures",
    apply: "build",
    closeBundle() {
      fs.rmSync(path.join(RENDERER_OUT_DIR, "spike-media"), { recursive: true, force: true });
    },
  };
}

export default defineConfig({
  root: path.resolve(__dirname, "renderer"),
  base: "./",
  plugins: [react(), tailwindcss(), dropSpikeFixtures()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "renderer/src"),
    },
  },
  build: {
    outDir: RENDERER_OUT_DIR,
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: false,
  },
});
