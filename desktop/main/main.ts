import crypto from "node:crypto";
import path from "node:path";

import { app, BrowserWindow, dialog } from "electron";

import { startSidecar, type Sidecar } from "./sidecar";

const IS_SMOKE_TEST = process.argv.includes("--smoke-test");
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? "";
const EXTERNAL_BACKEND_URL = process.env.ORIGAMI_BACKEND_URL ?? "";

const DESKTOP_DIR = path.resolve(__dirname, "..", "..");
const BACKEND_DIR = path.join(DESKTOP_DIR, "..", "backend");

interface BackendInfo {
  baseUrl: string;
  authToken: string;
}

let sidecar: Sidecar | null = null;
let backendInfo: BackendInfo | null = null;
let mainWindow: BrowserWindow | null = null;
let quitting = false;
let sidecarStopped = false;

function rendererOrigin(): string {
  // A file:// page sends "Origin: null", so that literal string is the
  // origin the backend must allow when the renderer is loaded from disk.
  return DEV_SERVER_URL ? new URL(DEV_SERVER_URL).origin : "null";
}

async function launchBackend(): Promise<BackendInfo> {
  if (EXTERNAL_BACKEND_URL) {
    return { baseUrl: EXTERNAL_BACKEND_URL.replace(/\/+$/, ""), authToken: "" };
  }

  const authToken = crypto.randomBytes(32).toString("hex");
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ORIGAMI_PORT: "0",
    ORIGAMI_AUTH_TOKEN: authToken,
    ORIGAMI_ALLOWED_ORIGINS: rendererOrigin(),
  };
  if (app.isPackaged) {
    env.ORIGAMI_DATA_DIR = path.join(app.getPath("userData"), "data");
  }

  // Phase 2 swaps this for a bundled Python runtime in packaged builds;
  // running from source uses uv exactly like the manual dev workflow.
  const handle = await startSidecar({
    command: "uv",
    args: ["run", "python", "main.py"],
    cwd: BACKEND_DIR,
    env,
    authToken,
  });

  handle.onUnexpectedExit((code) => {
    if (quitting) {
      return;
    }
    if (IS_SMOKE_TEST) {
      console.error(`smoke test: backend exited unexpectedly with code ${code ?? "unknown"}`);
      app.exit(1);
      return;
    }
    dialog.showErrorBox(
      "Origami backend stopped",
      `The local backend exited unexpectedly (code ${code ?? "unknown"}). Origami will close.`,
    );
    app.quit();
  });

  sidecar = handle;
  return { baseUrl: handle.baseUrl, authToken };
}

function createWindow(info: BackendInfo): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [
        `--origami-backend-url=${info.baseUrl}`,
        `--origami-auth-token=${info.authToken}`,
      ],
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  if (DEV_SERVER_URL) {
    void mainWindow.loadURL(DEV_SERVER_URL);
  } else {
    void mainWindow.loadFile(path.join(DESKTOP_DIR, "dist", "renderer", "index.html"));
  }
}

async function stopSidecar(): Promise<void> {
  if (sidecarStopped || !sidecar) {
    return;
  }
  sidecarStopped = true;
  await sidecar.stop();
}

app.whenReady().then(async () => {
  if (IS_SMOKE_TEST) {
    app.dock?.hide();
  }
  try {
    backendInfo = await launchBackend();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`failed to start backend: ${message}`);
    if (!IS_SMOKE_TEST) {
      dialog.showErrorBox("Origami could not start", `The local backend failed to start.\n\n${message}`);
    }
    quitting = true;
    await stopSidecar();
    app.exit(1);
    return;
  }

  if (IS_SMOKE_TEST) {
    process.stdout.write(`SMOKE_TEST_OK backend=${backendInfo.baseUrl}\n`);
    quitting = true;
    await stopSidecar();
    app.exit(0);
    return;
  }

  createWindow(backendInfo);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0 && backendInfo) {
      createWindow(backendInfo);
    }
  });
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("before-quit", (event) => {
  quitting = true;
  if (sidecarStopped || !sidecar) {
    return;
  }
  event.preventDefault();
  void stopSidecar().finally(() => {
    app.quit();
  });
});
