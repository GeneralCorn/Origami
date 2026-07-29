import path from "node:path";

import { app } from "electron";

export interface BackendLaunch {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
}

const DESKTOP_DIR = path.resolve(__dirname, "..", "..");
const DEV_BACKEND_DIR = path.join(DESKTOP_DIR, "..", "backend");

/**
 * The only place that knows where the backend lives.
 *
 * Development runs the checkout through uv, exactly like the manual
 * workflow. A packaged app has neither uv nor a checkout, so it runs the
 * relocatable CPython that scripts/bundle-python.mjs put under Resources.
 */
export function resolveBackendLaunch(baseEnv: NodeJS.ProcessEnv): BackendLaunch {
  if (!app.isPackaged) {
    return {
      command: "uv",
      args: ["run", "python", "main.py"],
      cwd: DEV_BACKEND_DIR,
      env: baseEnv,
    };
  }

  const backendDir = path.join(process.resourcesPath, "backend");
  const env: NodeJS.ProcessEnv = {
    ...baseEnv,
    // Bytecode goes to userData, not into the bundle. Writing .pyc files
    // beside the sources would invalidate the code signature's seal over
    // Resources, and Resources is read-only under /Applications anyway.
    // Shipping the .pyc instead costs 169 MB; this costs one slow launch.
    PYTHONPYCACHEPREFIX: path.join(app.getPath("userData"), "data", "pycache"),
    // A stray ~/.local/lib/python3.13/site-packages on the user's machine
    // would otherwise shadow the versions this bundle was locked against.
    PYTHONNOUSERSITE: "1",
    PYTHONUNBUFFERED: "1",
  };
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;

  return {
    command: path.join(process.resourcesPath, "python", "bin", "python3"),
    args: [path.join(backendDir, "main.py")],
    cwd: backendDir,
    env,
  };
}
