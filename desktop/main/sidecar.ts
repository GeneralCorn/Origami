import { spawn, type ChildProcess } from "node:child_process";
import readline from "node:readline";

const PORT_LINE_PATTERN = /^ORIGAMI_PORT=(\d+)$/;
const READY_TIMEOUT_MS = 30_000;
const HEALTH_POLL_INTERVAL_MS = 250;
const SIGKILL_GRACE_MS = 3_000;

export interface SidecarOptions {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
  authToken: string;
}

export interface Sidecar {
  baseUrl: string;
  stop: () => Promise<void>;
  onUnexpectedExit: (listener: (code: number | null) => void) => void;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function waitForPortLine(child: ChildProcess, deadline: number): Promise<number> {
  return new Promise((resolve, reject) => {
    if (!child.stdout) {
      reject(new Error("Sidecar has no stdout to announce its port on"));
      return;
    }
    const lines = readline.createInterface({ input: child.stdout });
    const timer = setTimeout(() => {
      lines.removeListener("line", onLine);
      reject(new Error("Timed out waiting for the backend to announce its port"));
    }, Math.max(0, deadline - Date.now()));

    const onLine = (line: string) => {
      process.stdout.write(`[backend] ${line}\n`);
      const match = PORT_LINE_PATTERN.exec(line.trim());
      if (match) {
        clearTimeout(timer);
        lines.removeListener("line", onLine);
        // Keep forwarding backend stdout after the port is found
        lines.on("line", (rest) => process.stdout.write(`[backend] ${rest}\n`));
        resolve(Number(match[1]));
      }
    };

    lines.on("line", onLine);
    child.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Backend exited with code ${code ?? "unknown"} before announcing its port`));
    });
  });
}

async function waitForHealth(baseUrl: string, authToken: string, deadline: number): Promise<void> {
  const headers: Record<string, string> = authToken
    ? { Authorization: `Bearer ${authToken}` }
    : {};
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/health`, {
        headers,
        signal: AbortSignal.timeout(1_000),
      });
      if (response.ok) {
        return;
      }
    } catch {
      // Not accepting connections yet; keep polling until the deadline
    }
    await delay(HEALTH_POLL_INTERVAL_MS);
  }
  throw new Error("Backend never became healthy before the timeout");
}

export async function startSidecar(options: SidecarOptions): Promise<Sidecar> {
  const child = spawn(options.command, options.args, {
    cwd: options.cwd,
    env: options.env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stderr?.setEncoding("utf8");
  child.stderr?.on("data", (chunk: string) => process.stderr.write(chunk));

  let stopping = false;
  let exited = false;
  const exitListeners: Array<(code: number | null) => void> = [];

  child.on("exit", (code) => {
    exited = true;
    if (!stopping) {
      for (const listener of exitListeners) {
        listener(code);
      }
    }
  });

  const deadline = Date.now() + READY_TIMEOUT_MS;
  try {
    const port = await waitForPortLine(child, deadline);
    const baseUrl = `http://127.0.0.1:${port}`;
    await waitForHealth(baseUrl, options.authToken, deadline);

    return {
      baseUrl,
      onUnexpectedExit: (listener) => {
        exitListeners.push(listener);
      },
      stop: async () => {
        stopping = true;
        if (exited) {
          return;
        }
        const gone = new Promise<void>((resolve) => child.once("exit", () => resolve()));
        child.kill("SIGTERM");
        await Promise.race([gone, delay(SIGKILL_GRACE_MS)]);
        if (!exited) {
          child.kill("SIGKILL");
          await gone;
        }
      },
    };
  } catch (error) {
    stopping = true;
    if (!exited) {
      child.kill("SIGKILL");
    }
    throw error;
  }
}
