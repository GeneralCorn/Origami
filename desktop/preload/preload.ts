import { contextBridge } from "electron";

function argValue(prefix: string): string {
  const match = process.argv.find((arg) => arg.startsWith(prefix));
  return match ? match.slice(prefix.length) : "";
}

contextBridge.exposeInMainWorld("origami", {
  backendUrl: argValue("--origami-backend-url="),
  authToken: argValue("--origami-auth-token="),
});
