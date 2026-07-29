import { contextBridge, ipcRenderer } from "electron";

function argValue(prefix: string): string {
  const match = process.argv.find((arg) => arg.startsWith(prefix));
  return match ? match.slice(prefix.length) : "";
}

contextBridge.exposeInMainWorld("origami", {
  backendUrl: argValue("--origami-backend-url="),
  authToken: argValue("--origami-auth-token="),
  platform: process.platform,
  setTitleBarTheme: (color: string, symbolColor: string) => {
    ipcRenderer.send("titlebar:set-theme", color, symbolColor);
  },
});
