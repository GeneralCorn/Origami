/**
 * Builds the Python runtime that ships inside the app bundle.
 *
 * Output is two directories under desktop/resources, which forge.config.js
 * hands to @electron/packager as extraResource:
 *
 *   resources/python   a relocatable CPython from python-build-standalone,
 *                      with the backend's locked dependencies installed into
 *                      its own site-packages
 *   resources/backend  the backend source, code only
 *
 * The build is idempotent: it records what it produced in a manifest and
 * exits early when the inputs have not moved. Pass --force to rebuild.
 */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PBS_RELEASE = "20260728";
const PYTHON_VERSION = "3.13.14";
const PYTHON_MINOR = "3.13";

// sha256 of the install_only_stripped tarballs, taken from the release's
// own SHA256SUMS. A mismatch aborts the build rather than shipping an
// interpreter nobody vouched for.
const PBS_CHECKSUMS = {
  arm64: "aa2a054f5e04bde63ae199e3bb6bbb634e457423efd294842deeb1299e7e5932",
  x64: "aa73c37aebebe3b7264dce1e49923719ab0ac0fc590353adf393eee3e2041c18",
};
const PBS_ARCH_TRIPLE = { arm64: "aarch64-apple-darwin", x64: "x86_64-apple-darwin" };

// Backend paths copied into the bundle. An allowlist rather than an
// ignore list, so a developer's notes, PDFs, uploads, or .env.local can
// never end up inside a shipped app.
const BACKEND_SOURCES = ["main.py", "config.py", "prompts", "routes", "services"];

// Removed after install. Everything here is either a build-time artifact
// or a subsystem the backend cannot reach: there is no Tk UI, nothing
// compiles C extensions at runtime, and nothing installs packages.
const PRUNED_PATHS = [
  "include",
  "share/man",
  `lib/python${PYTHON_MINOR}/idlelib`,
  `lib/python${PYTHON_MINOR}/tkinter`,
  `lib/python${PYTHON_MINOR}/turtledemo`,
  `lib/python${PYTHON_MINOR}/turtle.py`,
  `lib/python${PYTHON_MINOR}/ensurepip`,
  `lib/python${PYTHON_MINOR}/config-${PYTHON_MINOR}-darwin`,
  `lib/python${PYTHON_MINOR}/site-packages/pip`,
];
const PRUNED_PREFIXES = [
  { dir: "lib", prefix: "libtcl" },
  { dir: "lib", prefix: "libtk" },
  { dir: "lib", prefix: "tcl" },
  { dir: "lib", prefix: "tk" },
  { dir: "lib", prefix: "itcl" },
  { dir: "lib", prefix: "thread" },
  { dir: `lib/python${PYTHON_MINOR}/lib-dynload`, prefix: "_tkinter" },
  { dir: `lib/python${PYTHON_MINOR}/site-packages`, prefix: "pip-" },
];

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.resolve(scriptDir, "..");
const repoDir = path.resolve(desktopDir, "..");
const backendDir = path.join(repoDir, "backend");
const resourcesDir = path.join(desktopDir, "resources");
const pythonDir = path.join(resourcesDir, "python");
const bundledBackendDir = path.join(resourcesDir, "backend");
const manifestPath = path.join(resourcesDir, "bundle-manifest.json");
const cacheDir = path.join(desktopDir, ".cache", "python-build-standalone");

const force = process.argv.includes("--force");

function log(message) {
  process.stdout.write(`[bundle-python] ${message}\n`);
}

function run(command, args, options = {}) {
  return execFileSync(command, args, { stdio: "pipe", encoding: "utf8", ...options });
}

function sha256(filePath) {
  return createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function arch() {
  const value = process.env.ORIGAMI_TARGET_ARCH ?? process.arch;
  if (!PBS_ARCH_TRIPLE[value]) {
    throw new Error(`No python-build-standalone build pinned for arch "${value}"`);
  }
  return value;
}

function exportRequirements() {
  const target = path.join(resourcesDir, "requirements.txt");
  fs.mkdirSync(resourcesDir, { recursive: true });
  run("uv", [
    "export",
    "--frozen",
    "--no-dev",
    "--no-emit-project",
    "--no-hashes",
    "--format", "requirements-txt",
    "-o", target,
  ], { cwd: backendDir });
  return target;
}

async function downloadRuntime(targetArch) {
  const name = `cpython-${PYTHON_VERSION}+${PBS_RELEASE}-${PBS_ARCH_TRIPLE[targetArch]}-install_only_stripped.tar.gz`;
  const cached = path.join(cacheDir, name);
  if (fs.existsSync(cached) && sha256(cached) === PBS_CHECKSUMS[targetArch]) {
    log(`using cached ${name}`);
    return cached;
  }

  const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${encodeURIComponent(name)}`;
  log(`downloading ${name}`);
  fs.mkdirSync(cacheDir, { recursive: true });
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status} ${response.statusText} for ${url}`);
  }
  fs.writeFileSync(cached, Buffer.from(await response.arrayBuffer()));

  const actual = sha256(cached);
  if (actual !== PBS_CHECKSUMS[targetArch]) {
    fs.rmSync(cached);
    throw new Error(`Checksum mismatch for ${name}: expected ${PBS_CHECKSUMS[targetArch]}, got ${actual}`);
  }
  return cached;
}

function extractRuntime(tarball) {
  fs.rmSync(pythonDir, { recursive: true, force: true });
  fs.mkdirSync(resourcesDir, { recursive: true });
  const staging = fs.mkdtempSync(path.join(os.tmpdir(), "origami-python-"));
  try {
    run("tar", ["-xzf", tarball, "-C", staging]);
    fs.renameSync(path.join(staging, "python"), pythonDir);
  } finally {
    fs.rmSync(staging, { recursive: true, force: true });
  }
}

function installDependencies(requirementsPath) {
  log("installing locked dependencies");
  run("uv", [
    "pip", "install",
    "--python", path.join(pythonDir, "bin", "python3"),
    "--requirement", requirementsPath,
  ], { stdio: "inherit" });
}

function copyBackend() {
  fs.rmSync(bundledBackendDir, { recursive: true, force: true });
  fs.mkdirSync(bundledBackendDir, { recursive: true });
  for (const entry of BACKEND_SOURCES) {
    const source = path.join(backendDir, entry);
    const target = path.join(bundledBackendDir, entry);
    const stat = fs.statSync(source);
    if (stat.isDirectory()) {
      fs.cpSync(source, target, {
        recursive: true,
        filter: (from) => path.basename(from) !== "__pycache__" && (fs.statSync(from).isDirectory() || from.endsWith(".py")),
      });
    } else {
      fs.copyFileSync(source, target);
    }
  }
}

function prune() {
  for (const relative of PRUNED_PATHS) {
    fs.rmSync(path.join(pythonDir, relative), { recursive: true, force: true });
  }
  for (const { dir, prefix } of PRUNED_PREFIXES) {
    const parent = path.join(pythonDir, dir);
    if (!fs.existsSync(parent)) {
      continue;
    }
    for (const name of fs.readdirSync(parent)) {
      if (name.startsWith(prefix)) {
        fs.rmSync(path.join(parent, name), { recursive: true, force: true });
      }
    }
  }
}

function directorySize(target) {
  const output = run("du", ["-sk", target]).trim().split(/\s+/)[0];
  return Number(output) * 1024;
}

function megabytes(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function readManifest() {
  if (!fs.existsSync(manifestPath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  } catch {
    return null;
  }
}

function backendSourceHash() {
  const hash = createHash("sha256");
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, name);
      if (name === "__pycache__") {
        continue;
      }
      if (fs.statSync(full).isDirectory()) {
        walk(full);
      } else if (full.endsWith(".py")) {
        hash.update(path.relative(backendDir, full));
        hash.update(fs.readFileSync(full));
      }
    }
  };
  for (const entry of BACKEND_SOURCES) {
    const source = path.join(backendDir, entry);
    if (fs.statSync(source).isDirectory()) {
      walk(source);
    } else {
      hash.update(entry);
      hash.update(fs.readFileSync(source));
    }
  }
  return hash.digest("hex");
}

async function main() {
  const targetArch = arch();
  const requirementsPath = exportRequirements();
  const inputs = {
    pbsRelease: PBS_RELEASE,
    pythonVersion: PYTHON_VERSION,
    arch: targetArch,
    requirementsHash: sha256(requirementsPath),
    backendHash: backendSourceHash(),
  };

  const existing = readManifest();
  const upToDate = existing
    && fs.existsSync(path.join(pythonDir, "bin", "python3"))
    && fs.existsSync(path.join(bundledBackendDir, "main.py"))
    && Object.keys(inputs).every((key) => existing[key] === inputs[key]);
  if (upToDate && !force) {
    log(`up to date (${megabytes(existing.sizeBytes)}), pass --force to rebuild`);
    return;
  }

  const tarball = await downloadRuntime(targetArch);
  extractRuntime(tarball);
  installDependencies(requirementsPath);
  copyBackend();
  const rawSize = directorySize(pythonDir);
  prune();

  const runtimeSize = directorySize(pythonDir);
  const backendSize = directorySize(bundledBackendDir);
  const sizeBytes = runtimeSize + backendSize;
  fs.writeFileSync(manifestPath, `${JSON.stringify({ ...inputs, sizeBytes }, null, 2)}\n`);

  log(`runtime before pruning: ${megabytes(rawSize)}`);
  log(`runtime after pruning:  ${megabytes(runtimeSize)}`);
  log(`backend source:         ${megabytes(backendSize)}`);
  log(`total extraResource:    ${megabytes(sizeBytes)}`);
}

await main();
