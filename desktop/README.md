# Origami Desktop

The Electron shell: a Vite plus React renderer around the existing FastAPI backend, which runs as a child process. Phases 1 and 2 of `docs/ELECTRON_PORT_PLAN.md`. It runs from source and it packages into a signed, installable `.app`.

## Running it

Prerequisites: Node 20.19 or newer, `uv` on `PATH`, and the backend dependencies installed (`cd backend && uv sync`).

```bash
cd desktop
npm install
npm run dev
```

`npm run dev` starts the Vite dev server, compiles the main process, and launches Electron pointed at the dev server with hot reload.

Other scripts:

| Script | What it does |
|---|---|
| `npm run build` | Compiles the main process, typechecks the renderer, and builds the production bundle into `dist/` |
| `npm start` | Runs Electron against the built bundle in `dist/renderer` |
| `npm run smoke` | Starts the backend, waits for readiness, prints `SMOKE_TEST_OK`, and exits without opening a window |
| `npm run bundle:python` | Builds the Python runtime under `resources/`. Idempotent; `-- --force` rebuilds |
| `npm run package` | Produces `out/Origami-darwin-arm64/Origami.app` |
| `npm run make` | Produces the DMG and the ZIP in `out/make` |

## How the pieces connect

The main process owns the backend's lifecycle:

1. It generates a random 32-byte token for the launch and passes it to the backend as `ORIGAMI_AUTH_TOKEN`, along with `ORIGAMI_PORT=0` so the OS assigns a free port.
2. The backend binds its socket, then prints `ORIGAMI_PORT=<n>` on stdout. The main process parses that line rather than assuming port 8000.
3. It polls `/health` with the token until the backend answers, then opens the window. The window never appears before the backend is ready.
4. The port and token reach the renderer through a preload script over `contextBridge`, as `window.origami`. `contextIsolation` is on and `nodeIntegration` is off.
5. The renderer talks to `http://127.0.0.1:<port>` directly. Every request carries `Authorization: Bearer <token>`; URLs the browser loads itself, meaning screenshot images and the PDF iframe, carry `?token=` instead because those cannot set headers.

On quit the main process sends `SIGTERM` to the backend and escalates to `SIGKILL` after three seconds. If the backend dies on its own, the app surfaces an error dialog and exits rather than leaving a dead window.

In packaged builds `ORIGAMI_DATA_DIR` is set to `userData/data`, which resolves to `~/Library/Application Support/Origami/data`. In development it is left unset, so dev data stays in `backend/` exactly where it was.

## Packaging

`main/backend-launch.ts` is the only file that knows where the backend lives. Development runs `uv run python main.py` against the checkout; a packaged app runs the interpreter under `Contents/Resources/python` against the copy of the backend under `Contents/Resources/backend`. Nothing else branches on `app.isPackaged` for this, and nothing should start.

### The Python runtime: python-build-standalone, not PyInstaller

`scripts/bundle-python.mjs` downloads a pinned [python-build-standalone](https://github.com/astral-sh/python-build-standalone) CPython, checks its SHA-256 against the release's own `SHA256SUMS`, installs the backend's locked dependencies into its `site-packages` with `uv pip install`, prunes the parts the backend cannot reach, and copies the backend source beside it. The two directories ship as `extraResource`.

PyInstaller was the alternative and was rejected. Its failure mode is native extensions, and this dependency tree is mostly native extensions: `fastembed` pulls `onnxruntime`, and `chromadb`, `pymupdf`, `tokenizers`, and `pydantic-core` each ship compiled libraries. PyInstaller rewrites how those are found and unpacks them to a temporary directory at startup, which is the part that breaks, and `onnxruntime` in particular has a history of it. A relocatable interpreter keeps ordinary `dlopen` semantics: the layout in the bundle is the layout the packages were installed into, so a package either works or fails for its own reasons rather than for packaging's.

The pins are constants at the top of the script. Moving to a new CPython means changing the release tag, the version, and both checksums together.

Two things the runtime relies on, both set in `backend-launch.ts`:

- `PYTHONPYCACHEPREFIX` points at `userData/data/pycache`. Bytecode cannot be written into the bundle, because a file added after signing invalidates the seal over `Resources` and the bundle is read-only under `/Applications` anyway. Shipping precompiled `.pyc` instead was measured at 169 MB for 1.3 s of launch time, so the cache goes outside: first launch pays 3.3 s, later launches 1.5 s, and the cache settles around 61 MB.
- `PYTHONNOUSERSITE` is set and `PYTHONPATH` and `PYTHONHOME` are deleted, so a developer's environment cannot shadow the locked dependencies with different versions.

### Size

Measured on `arm64`, CPython 3.13.14, release `20260728`:

| Part | Size |
|---|---|
| Python runtime, as installed | 463.3 MB |
| Python runtime, after pruning | 442.6 MB |
| Backend source | 0.2 MB |
| Electron frameworks | 275 MB |
| `app.asar` | 3.4 MB |
| **Installed `.app`** | **718 MB** |
| DMG | 238 MB |
| ZIP | 249 MB |

Pruning removes `pip`, `ensurepip`, `idlelib`, `tkinter` with its Tcl/Tk libraries, `turtledemo`, the C headers, and the build-time `config-` directory. That is 20 MB and it is all of the free saving. The rest is 267 MB of native code across 93 libraries, and the four largest are `onnxruntime` at 65 MB, `pymupdf` at 54 MB, `chromadb_rust_bindings` at 46 MB, and `grpc` at 37 MB.

§3.1 of the port plan sets 400 MB as the point at which the Electron decision should be revisited, and the app is well past it. Worth reading precisely though: the plan's reasoning was that Electron's overhead is small relative to the Python runtime, and that still holds, since Electron is 275 MB of the 718 MB and Tauri would save most but not all of it. Dropping `sentence-transformers` for `fastembed` did its job, in that Torch would have added several hundred megabytes on its own. What is left is genuinely used code plus three dependencies that are not:

- `grpc`, 37 MB, and `kubernetes`, 18 MB, both come from `chromadb` and serve its client-server mode. This app uses `PersistentClient`.
- `sympy`, 29 MB, comes from `onnxruntime` and is used by its graph-optimization tooling, not by inference.

Together that is 84 MB, and removing it is a change to `backend/pyproject.toml`, not to packaging. It was left alone because dropping a declared dependency to save space is a backend decision with its own failure modes, and Phase 2 is not the place to make it.

### Signing and notarization

Everything comes from the environment. No credential is committed and none is invented.

| Variable | Purpose |
|---|---|
| `ORIGAMI_SIGN_IDENTITY` | `Developer ID Application: NAME (TEAMID)` |
| `ORIGAMI_APPLE_ID` | Apple ID for `notarytool` |
| `ORIGAMI_APPLE_APP_SPECIFIC_PASSWORD` | app-specific password for that Apple ID |
| `ORIGAMI_APPLE_TEAM_ID` | ten-character team identifier |

With the identity set, the app is signed with it. With all four set, it is also notarized. With none set the build still succeeds, prints what it is doing, and signs ad-hoc.

Ad-hoc rather than truly unsigned, because truly unsigned is not an option: Apple Silicon refuses to execute a Mach-O whose signature does not validate, and packaging rewrites `Info.plist`, which invalidates the one Electron ships with. What ad-hoc actually costs is persistence. Its signature is regenerated on every build, so macOS sees a new application each time and every permission grant has to be given again.

Signing uses `@electron/osx-sign` and notarization uses `@electron/notarize`, the maintained scoped packages. Both arrive through `@electron/packager` and are pinned as direct dev dependencies so the versions are visible.

**Deep signing is covered.** `@electron/osx-sign` walks `Contents/` and signs every Mach-O it finds, including the ones several directories deep inside `site-packages`. Verified on the built bundle: 93 of 93 Mach-O files under `Contents/Resources` carry a signature with the `runtime` flag. Nothing extra had to be added for it, but it is worth knowing where the behaviour comes from, because notarization rejects a submission over a single unsigned nested library.

### Entitlements

Notarization requires the hardened runtime, so every build runs under it, including ad-hoc ones. A local build that skipped it would not be exercising the restrictions the shipped build has to survive.

The set below is what was measured, not what is conventional. Each key was tested by removing it and running the app.

| File | Applies to | Keys |
|---|---|---|
| `build/entitlements.app.plist` | Electron binaries | `com.apple.security.cs.allow-jit` |
| `build/entitlements.python.plist` | the bundled CPython and everything it loads | none |
| `build/entitlements.adhoc.plist` | every binary, ad-hoc builds only | the above plus `com.apple.security.cs.disable-library-validation` |

**`allow-jit` on the Electron side is required.** Without it the app aborts before a window appears:

```
# Fatal process out of memory: Failed to reserve virtual memory for CodeRange
```

**The Python sidecar needs nothing.** Signed with an empty entitlements dict under the hardened runtime, it starts the server, answers `/health`, produces 384-dimension embeddings through `onnxruntime`, and renders a page through PyMuPDF. Both of the keys usually pasted in alongside `allow-jit` were tested and are absent for that reason:

- `com.apple.security.cs.allow-unsigned-executable-memory` is not needed. It would matter if `ctypes` closures or an ONNX JIT allocated writable-executable pages, and neither path does.
- `com.apple.security.cs.allow-dyld-environment-variables` is not needed. Nothing sets `DYLD_*`, and the sidecar's environment is built explicitly in `backend-launch.ts`.

**`disable-library-validation` is confined to ad-hoc builds and is not an entitlement this app needs.** Under the hardened runtime, a process may only map libraries carrying its own Team ID. An ad-hoc signature has no Team ID, so an ad-hoc build cannot load its own Electron Framework:

```
Library not loaded: @rpath/Electron Framework.framework/Electron Framework
Reason: ... mapping process and mapped file (non-platform) have different Team IDs
```

The same failure hits the sidecar one library deeper, at `_pydantic_core.cpython-313-darwin.so`. A Developer ID build signs every nested binary with one real Team ID, so the check passes on its own, which is why the key is absent from the two shipped files. That last step is inferred rather than measured, since there is no certificate here to measure it with. If a real signed build fails to load its own libraries, this is the first thing to look at.

### The bundle identifier

`com.generalcorn.origami`, set in `forge.config.js`.

TCC binds a grant to the code signature, the bundle identifier, and the on-disk path. Changing this string later means every user re-granting Calendar, Reminders, Photos, Contacts, and Full Disk Access. It is chosen deliberately and it should now be treated as frozen.

There is one free window to change it, and it is open now: no build has been signed with a Developer ID yet, so no grant exists anywhere that would be lost. If a different identifier is wanted, change it before the first signed build and not after.

### Usage descriptions

All four keys from `docs/ELECTRON_PORT_PLAN.md` §3.3 are declared in `forge.config.js` and verified present in the built `Info.plist`: `NSCalendarsUsageDescription`, `NSRemindersUsageDescription`, `NSPhotoLibraryUsageDescription`, `NSContactsUsageDescription`.

They are declared before the connectors that need them because the failure mode is silent. macOS attributes the sidecar's request to this bundle and checks these keys; a missing key denies access with no prompt and no error, and an empty calendar is indistinguishable from a denied one. The strings are user-facing, since they appear inside the system's permission dialog.

`utilityProcess({ disclaim: true })` is deliberately not used, per §3.3.

### Full Disk Access

`Origami.app/Contents/MacOS/Origami --tcc-probe` reports whether the main process and a sidecar child can open `~/Library/Messages/chat.db`. It reads sixteen bytes, which is the SQLite header and no message content. See `docs/INTEGRATIONS_RESEARCH.md` §4 for what this measured and what it did not.

## The title bar

There is no OS title bar. The app's own header strip runs to the top of the window and the system draws its window controls over it.

- **macOS** uses `titleBarStyle: "hiddenInset"`, so the traffic lights float over the header. `trafficLightPosition` centers them against the 48px header.
- **Windows and Linux** use `titleBarStyle: "hidden"` with `titleBarOverlay`, which keeps the real minimize, maximize, and close buttons and draws them over the header. Bare `frame: false` is deliberately not used, because it would mean hand-drawing and hand-wiring those three buttons.

Two constraints follow from this, and both are easy to break:

1. The header carries `-webkit-app-region: drag` so the window still moves. **Every interactive element inside it needs the `titlebar-interactive` class**, which sets `no-drag`. Without it the control silently stops receiving clicks.
2. The header reserves space for the controls through `--titlebar-inset-left` and `--titlebar-inset-right` in `globals.css`, keyed off a `data-platform` attribute that comes from the preload bridge rather than user-agent sniffing. Windows reads the real button width from the `titlebar-area-*` environment variables, with a static fallback.

`titleBarOverlay` colors are baked in at window creation, so they go stale when the theme changes. The renderer resolves the active palette to hex and pushes it to the main process over IPC on every theme switch. That call is Windows-only; on macOS the system draws the traffic lights and it is skipped. The palette is authored in oklch, which the overlay cannot parse, so the conversion rasterizes the color to a single canvas pixel and reads the bytes back. Reading `fillStyle` directly does not work: Chromium echoes oklch unchanged rather than normalizing to hex.

If the header height changes, update `TITLE_BAR_HEIGHT` in `main/main.ts` to match, or the Windows buttons will not line up.

## Notes on the port from Next.js

The renderer is the `frontend/` application with the Next.js shell removed. What changed:

- `next/navigation` became `lib/router.tsx`, a small hash router. Four routes did not justify a routing dependency, and hash routing is what works from `file://` in a packaged build.
- `next/dynamic` became plain imports. It only existed to disable SSR, and there is no SSR here.
- `next/font/google` became `@fontsource-variable` packages, so the fonts are bundled rather than fetched at runtime.
- `app/api/chat`, the Next.js proxy route, is gone. The chat transport points at the backend's `/api/chat` directly and still streams over SSE.

## What signing still needs from you

The build is wired for both and neither is present here, so every build so far has been ad-hoc.

- **Apple Developer ID Application certificate**, installed in the login keychain, and its full name in `ORIGAMI_SIGN_IDENTITY`. A Developer ID is required; a development certificate will not keep permission grants across rebuilds.
- **Notarization credentials**: an Apple ID, an app-specific password, and the team ID, in the three variables above. Notarization runs through `xcrun notarytool`, which needs the Xcode command line tools. The App Store Connect API key route is also supported by `@electron/notarize` but is not wired up, since it needs a `.p8` file path rather than an environment variable.
- **Confirm the bundle identifier before the first signed build.** `com.generalcorn.origami` is a considered default, not a decision anyone made out loud, and it is free to change only until a real grant exists against it.

## Known gaps

- **Nothing has been signed with a real Developer ID.** Everything from `codesign` in this repository was produced ad-hoc, so notarization has never run and `notarytool` has never been called. The build path is wired and reads the credentials, but its first real execution will be its first test.
- **`disable-library-validation` being unnecessary for Developer ID builds is inferred, not measured.** The reasoning is in the entitlements section. It is the most likely thing to be wrong about the first signed build.
- **Only `arm64` is built.** `scripts/bundle-python.mjs` has the `x86_64` checksum pinned and takes `ORIGAMI_TARGET_ARCH`, but no Intel or universal build has been produced or run. A universal binary would also mean two Python runtimes, roughly doubling the 442 MB.
- **The app is 718 MB installed**, past the 400 MB threshold at which `docs/ELECTRON_PORT_PLAN.md` §3.1 says the Electron decision should be revisited. See the size section for the breakdown and for the 84 MB that three unused dependencies account for.
- **Whether a sidecar child inherits Full Disk Access is still unresolved.** Answering it means granting FDA to a real bundle. The harness is committed; see `docs/INTEGRATIONS_RESEARCH.md` §4.
- **There is no in-app way to set `ANTHROPIC_API_KEY`.** The hard blocker is fixed: `main.py` now reads `.env.local` from the data dir before falling back to the copy beside itself, so a packaged user can configure the app by creating `~/Library/Application Support/Origami/data/.env.local`. Precedence is launcher environment, then the data-dir file, then the bundled dev file, since `load_dotenv` never overrides a variable that is already set. What remains is that editing a dotfile by hand is not a reasonable ask for the non-technical audience this app targets, so a settings surface (or having the main process store the key and pass it through the environment, as it already does for `ORIGAMI_AUTH_TOKEN`) is still needed.
- **A full chat round trip is unverified.** The transport, the auth gate, and the SSE framing are confirmed working: an unauthenticated request gets 401, an authenticated one opens a stream and emits the first `start` event. The assistant response itself was never exercised, because no `ANTHROPIC_API_KEY` is configured in this checkout.
- **No application icon.** The bundle carries Electron's default, so the DMG and the Dock show a generic icon.
- **The renderer bundle is a single 2 MB chunk.** Fine for a local application with no network fetch, worth splitting only if startup time becomes a complaint.
- **The Windows title bar path is unverified.** It was written against the `titleBarOverlay` API and reviewed by inspection, but there is no Windows machine here to run it on. The macOS path is verified against a running window.
- **Windows and Linux are not supported** and are out of scope per the port plan.
- **Native vibrancy and Mica are not enabled.** Both need the CSS behind them to be transparent, which the current opaque palette is not, so turning them on would show no change without a palette pass first.
