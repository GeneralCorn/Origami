# Origami Desktop

The Electron shell: a Vite plus React renderer around the existing FastAPI backend, which runs as a child process. This is Phase 1 of `docs/ELECTRON_PORT_PLAN.md`. It runs from source. Packaging and signing are Phase 2 and are deliberately not here.

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

## How the pieces connect

The main process owns the backend's lifecycle:

1. It generates a random 32-byte token for the launch and passes it to the backend as `ORIGAMI_AUTH_TOKEN`, along with `ORIGAMI_PORT=0` so the OS assigns a free port.
2. The backend binds its socket, then prints `ORIGAMI_PORT=<n>` on stdout. The main process parses that line rather than assuming port 8000.
3. It polls `/health` with the token until the backend answers, then opens the window. The window never appears before the backend is ready.
4. The port and token reach the renderer through a preload script over `contextBridge`, as `window.origami`. `contextIsolation` is on and `nodeIntegration` is off.
5. The renderer talks to `http://127.0.0.1:<port>` directly. Every request carries `Authorization: Bearer <token>`; URLs the browser loads itself, meaning screenshot images and the PDF iframe, carry `?token=` instead because those cannot set headers.

On quit the main process sends `SIGTERM` to the backend and escalates to `SIGKILL` after three seconds. If the backend dies on its own, the app surfaces an error dialog and exits rather than leaving a dead window.

In packaged builds `ORIGAMI_DATA_DIR` is set to `userData/data`. In development it is left unset, so dev data stays in `backend/` exactly where it was.

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

## What Phase 2 needs from you

Packaging and signing cannot be done without these. Per `docs/ELECTRON_PORT_PLAN.md` §3.4, signing has to be in place from the first packaged build, because TCC permission grants are bound to the code signature and unsigned builds present as a new application on every rebuild.

- **Apple Developer ID Application certificate**, installed in the login keychain. A Developer ID is required; an ad-hoc or development certificate will not keep permission grants across rebuilds.
- **Notarization credentials**: an App Store Connect API key (issuer ID, key ID, and the `.p8` file), or an Apple ID with an app-specific password and the team ID. Notarization runs through `xcrun notarytool`, which needs the Xcode command line tools.
- **A decision on the bundle identifier**, for example `com.yourname.origami`. It must stay stable forever, since TCC binds grants to it.

Phase 2 must also declare these `NS*UsageDescription` keys in the bundle's `Info.plist`, ahead of the connectors that need them. macOS attributes a child process's permission requests to the Electron bundle, and a missing key means access is denied **silently**, with no prompt and no error:

| Key | Unlocks |
|---|---|
| `NSCalendarsUsageDescription` | Calendar ingestion |
| `NSRemindersUsageDescription` | Todo ingestion |
| `NSPhotoLibraryUsageDescription` | Apple Photos ingestion |
| `NSContactsUsageDescription` | Resolving message participants to people |

Full Disk Access, which iMessage ingestion needs, is path-based rather than key-gated. Whether it follows the same responsible-process attribution rule is still unverified and must be tested in Phase 2, since it decides whether the iMessage connector is schedulable at all.

## Known gaps

- **The backend is not bundled.** The sidecar runs `uv run python main.py`, so `uv` and a synced backend environment must exist on the machine. Bundling the Python runtime is Phase 2.
- **A full chat round trip is unverified.** The transport, the auth gate, and the SSE framing are confirmed working: an unauthenticated request gets 401, an authenticated one opens a stream and emits the first `start` event. The assistant response itself was never exercised, because no `ANTHROPIC_API_KEY` is configured in this checkout. Set one in `backend/.env.local` to confirm.
- **The renderer bundle is a single 2 MB chunk.** Fine for a local application with no network fetch, worth splitting only if startup time becomes a complaint.
- **The Windows title bar path is unverified.** It was written against the `titleBarOverlay` API and reviewed by inspection, but there is no Windows machine here to run it on. The macOS path is verified against a running window.
- **Windows and Linux are not supported** and are out of scope per the port plan.
- **Native vibrancy and Mica are not enabled.** Both need the CSS behind them to be transparent, which the current opaque palette is not, so turning them on would show no change without a palette pass first.
