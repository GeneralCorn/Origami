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

// Origami ingests content written by other people, and that content reaches
// the renderer through notes and through the agent's answers. Markdown carries
// image syntax, so without a policy a remote URL in ingested text is fetched
// on render: an exfiltration channel that needs no tool call and no agent
// cooperation, which is exactly the third leg ARCHITECTURE_V2 section 3 exists
// to remove. Only loopback and bundled assets are reachable.
const LOCAL_BACKEND = "http://127.0.0.1:* http://localhost:*";

function contentSecurityPolicy(isDev: boolean): string {
  const directives = [
    "default-src 'self'",
    // Vite injects inline bootstrap scripts and uses eval for HMR in dev only.
    isDev ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${LOCAL_BACKEND}`,
    "font-src 'self' data:",
    isDev
      ? `connect-src 'self' ${LOCAL_BACKEND} ws://127.0.0.1:* ws://localhost:*`
      : `connect-src 'self' ${LOCAL_BACKEND}`,
    `frame-src 'self' blob: ${LOCAL_BACKEND}`,
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ];
  return directives.join("; ");
}

function injectCsp(): Plugin {
  return {
    name: "inject-csp",
    transformIndexHtml(html, ctx) {
      const meta = `<meta http-equiv="Content-Security-Policy" content="${contentSecurityPolicy(!ctx.bundle)}">`;
      return html.replace("<head>", `<head>\n    ${meta}`);
    },
  };
}

export default defineConfig({
  root: path.resolve(__dirname, "renderer"),
  base: "./",
  plugins: [react(), tailwindcss(), dropSpikeFixtures(), injectCsp()],
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
