import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import electronPath from "electron";
import { createServer } from "vite";

const desktopDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const server = await createServer({
  configFile: path.join(desktopDir, "vite.config.ts"),
});
await server.listen();

const address = server.httpServer.address();
if (address === null || typeof address === "string") {
  console.error("vite dev server did not report a port");
  process.exit(1);
}
const devServerUrl = `http://localhost:${address.port}`;
server.printUrls();

const electron = spawn(String(electronPath), [desktopDir], {
  stdio: "inherit",
  env: { ...process.env, VITE_DEV_SERVER_URL: devServerUrl },
});

electron.on("exit", (code) => {
  server.close().finally(() => {
    process.exit(code ?? 0);
  });
});
