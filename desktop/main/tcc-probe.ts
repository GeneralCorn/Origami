import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { resolvePythonEval } from "./backend-launch";

const CHAT_DB = path.join(os.homedir(), "Library", "Messages", "chat.db");

// Full Disk Access is enforced at open(), not stat(), and it answers
// EPERM rather than the EACCES that ordinary file permissions produce.
// Reading the first 16 bytes gets the SQLite header and no message data.
const PROBE_SOURCE = `
import os, pathlib, sys
target = pathlib.Path.home() / "Library" / "Messages" / "chat.db"
try:
    with open(target, "rb") as handle:
        handle.read(16)
    sys.stdout.write("readable\\n")
except OSError as error:
    sys.stdout.write(f"denied errno={error.errno}\\n")
`;

function probeFromMainProcess(): string {
  try {
    const handle = fs.openSync(CHAT_DB, "r");
    fs.closeSync(handle);
    return "readable";
  } catch (error) {
    const errno = (error as NodeJS.ErrnoException).errno;
    const code = (error as NodeJS.ErrnoException).code;
    return `denied ${code} errno=${errno}`;
  }
}

function probeFromSidecar(): Promise<string> {
  const launch = resolvePythonEval(process.env, PROBE_SOURCE);
  return new Promise((resolve) => {
    execFile(launch.command, launch.args, { cwd: launch.cwd, env: launch.env }, (error, stdout, stderr) => {
      if (error) {
        resolve(`probe failed to run: ${stderr.trim() || error.message}`);
        return;
      }
      resolve(stdout.trim());
    });
  });
}

/**
 * Answers whether Full Disk Access follows the responsible-process rule.
 *
 * FDA is path-based rather than gated by an NS*UsageDescription key, so
 * the attribution question the NS* keys answer does not automatically
 * answer this one, and iMessage ingestion depends on it. The probe has to
 * run inside the app bundle: launching the interpreter from a terminal
 * would make the terminal the responsible process and measure nothing.
 *
 * Read the two lines together.
 *   both readable            the child inherits, iMessage is schedulable
 *   parent readable, child   denied  FDA does not follow the rule, and the
 *                            sidecar cannot be the process that reads
 *   both denied              the app has no grant yet, grant it first
 */
export async function runTccProbe(): Promise<void> {
  const parent = probeFromMainProcess();
  const child = await probeFromSidecar();
  process.stdout.write(`TCC_PROBE chat.db parent=${parent}\n`);
  process.stdout.write(`TCC_PROBE chat.db child=${child}\n`);
}
