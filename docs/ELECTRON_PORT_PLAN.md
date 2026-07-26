# Electron Port Plan

**Date:** 2026-07-26
**Status:** Plan, no code written
**Reads with:** `ARCHITECTURE_V2.md`, `INTEGRATIONS_RESEARCH.md`, `COST_MODEL.md`

---

## 1. The goal in one paragraph

Origami becomes a signed macOS desktop application: an Electron shell around the existing React interface, with the existing Python backend running as a bundled sidecar. The Next.js application stops being the product and becomes a light-mode open-source launch page. The product itself grows from a PDF and notes tool into a local-first personal knowledge base that ingests from many sources, with an editing experience closer to Obsidian and a visual density considerably lower than the current interface.

---

## 2. Current state, verified

Checked against the working tree on 2026-07-26.

| Component | State |
|---|---|
| Repository | `github.com/GeneralCorn/Origami`, `main` at `d3f67e7`. Push access confirmed. |
| Backend | Python 3.13, FastAPI, LangGraph, LangChain, Chroma, `sentence-transformers` |
| Frontend | Next.js 16.1.6, React 19.2.3, Tailwind 4, shadcn/ui, AI SDK v6 |
| Embedding | `bge-small-en-v1.5`, 384 dimensions, via `sentence-transformers` |
| In flight, uncommitted | Screenshot, vision, and digest feature: 22 modified files, 7 new. `ollama.py` and `prompts/title.py` deleted. |

The uncommitted work matters to sequencing. It is a vision and digest pipeline that already produces the shape `ARCHITECTURE_V2.md` §2 describes, and the deletion of `ollama.py` means the local model path is currently in flux.

---

## 3. The five decisions

### 3.1 Electron, with the size cost acknowledged

`[SECONDARY]` Electron applications start around 100 to 200 MB; Tauri lands at 2 to 10 MB.

Electron is still correct here, and the honest reason is not that the size penalty is small. It is that the penalty is already paid. A bundled Python runtime with ONNX, Chroma, and the LangGraph dependency tree is well over 100 MB on its own, so Tauri's advantage shrinks from roughly 20x to a much smaller multiple. Set against that, the existing React and shadcn interface transfers directly, and Electron's `utilityProcess` provides the macOS TCC control described in §3.3 that would otherwise have to be built by hand.

Decision: **Electron.** Revisit only if the bundle exceeds roughly 400 MB, at which point the calculation changes.

### 3.2 Keep the Python backend as a sidecar

The backend is LangGraph, LangChain, Chroma, and PyMuPDF. There is no proportionate route to reimplementing that in Node, and no benefit that would justify it.

Decision: **bundle the existing FastAPI application as a child process.** It keeps speaking HTTP over localhost, which means the frontend contract does not change and web development stays possible during the port.

### 3.3 Declare TCC usage descriptions on the Electron bundle

This is the decision most likely to be got wrong, because getting it wrong produces no error.

Per `INTEGRATIONS_RESEARCH.md` §4, macOS attributes a child process's permission requests to the **responsible process**, which is the Electron application. The system checks that bundle's `Info.plist` for the relevant `NS*UsageDescription` key. When the key is missing, access is denied **silently**, with no prompt and no error. A sidecar reading EventKit inside an app that has not declared `NSCalendarsUsageDescription` returns an empty calendar, indistinguishable from a user with no events.

Decision: **declare every usage description the sidecar will ever need on the Electron bundle at the signing step**, before the corresponding connector is built. Do not use `utilityProcess({ disclaim: true })`. Disclaiming exists for launching untrusted third-party code, which the sidecar is not, and it splits the permission story across two bundle identities for no gain.

Keys required, matched to the connectors in the integrations matrix:

| Key | Unlocks |
|---|---|
| `NSCalendarsUsageDescription` | Calendar ingestion |
| `NSRemindersUsageDescription` | Todo ingestion |
| `NSPhotoLibraryUsageDescription` | Apple Photos ingestion |
| `NSContactsUsageDescription` | Resolving message participants to people |

Full Disk Access, which iMessage ingestion depends on, is path-based rather than gated by a usage description key. `[UNVERIFIED]` Whether it follows the same responsible-process attribution rule has not been confirmed and must be tested before the iMessage connector is scheduled.

### 3.4 Sign with a real Developer ID from the first build

`[VERIFIED]` TCC binds a permission grant to the code signature, bundle identifier, and on-disk path. `[SECONDARY]` Ad-hoc and unsigned builds regenerate their signature each time, so every rebuild presents as a new application and grants do not persist. OpenClaw's own macOS documentation reaches the same conclusion and requires real Apple certificates for all builds.

**Correction to the inherited plan,** which claimed Full Disk Access is "revoked on every update." That describes unsigned builds. A build signed with a stable Developer ID retains its grants across updates normally. The requirement is a stable identity, not a property of updating.

Decision: **Developer ID signing from the first packaged build, not as a release-time step.** Deferring it means developing against permission behaviour that does not match shipped behaviour, which is the kind of divergence that surfaces late and expensively.

`[SECONDARY]` Tooling: `@electron/osx-sign` and `@electron/notarize` are the maintained scoped packages; the unscoped `electron-osx-sign` and `electron-notarize` are deprecated. Notarization uses `xcrun notarytool` from the Xcode command line tools.

### 3.5 Next.js becomes the launch page, and the desktop renderer drops it

Next.js exists for server rendering, routing, and API routes. Inside Electron the renderer is a local window with a local backend, so all three are dead weight, and Next's build model fights the packaging step.

Decision: **the desktop renderer becomes a Vite plus React application.** The React components, Tailwind configuration, and shadcn primitives port directly; what is discarded is the Next.js shell, `app/api/chat`, and file-system routing.

The existing Next.js project is then repurposed as the public launch page. See §5.

---

## 4. The editing experience

The product metaphor is Obsidian with intelligence, and the brief calls for cleaner presentation with lower text density than the current interface.

`[SECONDARY]` For a markdown-first editor, CodeMirror 6 is the closest fit and is widely reported to be what Obsidian itself uses. It is built for text with markdown as the source of truth, which is the correct model for a knowledge base whose files should stay portable and greppable.

The alternatives serve a different product. `[SECONDARY]` TipTap sits on ProseMirror and typically takes two to four weeks to integrate; Lexical is lower-level and expects months of engineering for a custom editor product. Both are rich-text-document editors, and choosing one means the document model stops being markdown.

Decision: **CodeMirror 6**, markdown on disk as the source of truth.

`[UNVERIFIED]` Whether CodeMirror 6 handles the mixed-media blocks this product needs, meaning an inline photo or a screenshot embedded in a note, as cleanly as a ProseMirror-based editor would. This is the one place the decision could reverse, and it should be spiked before the editor work is scheduled rather than discovered during it.

On density: the current interface is a research tool built around dense chat and document panes. The target is a reading and writing surface. This is a design workstream in its own right and is deliberately not specified here beyond the constraint that it comes after the port is stable, since redesigning while the runtime is changing underneath means doing it twice.

---

## 5. The launch page

The existing Next.js project is exported statically and becomes the public site.

### 5.1 Scope

**Decided 2026-07-26: one to four pages, no more.** A landing page, an FAQ, and one or two light documentation pages. This is a launch site, not a documentation platform. If documentation outgrows a couple of pages it belongs in the repository as markdown, where it stays next to the code that it describes.

Landing page content: what Origami is in one line, a screenshot or short loop of the product, three or four capability points, an explicit local-first and privacy statement given what the product ingests, install instructions, and a GitHub link.

### 5.2 The permanent constraint: no backend of any kind

**Decided 2026-07-26: the site will never have authentication, login, accounts, or server-handled forms.**

This is recorded as a standing constraint rather than a current state, because it is the fact that makes the hosting decision in §5.3 permanently correct instead of correct-for-now. A waitlist form, a newsletter signup, or any login would each require server compute and would reopen the question. None of them are planned.

It also happens to be the honest posture for the product. A local-first tool whose entire pitch is that your data never leaves your machine should not ask visitors to create an account to read about it.

### 5.3 Hosting: GitHub Pages

**Decided 2026-07-26: GitHub Pages, not Vercel.** Given §5.2, the only meaningful advantage Vercel held was serverless functions for a future form, and there will be no form. GitHub Pages is free, lives in the same repository, adds no third-party account, and needs no build-skipping configuration.

Vercel was evaluated and would also have worked. `[VERIFIED]` It supports deploying from a subdirectory through the Root Directory setting, and multiple projects can connect to one repository. The complication was that its automatic build-skipping requires JavaScript workspaces, and this repository's Python backend can never be a workspace member, so every backend commit would have counted as a global change and triggered a site rebuild. That was solvable through the Ignored Build Step, but it is configuration that GitHub Pages does not require at all.

Required configuration, `[VERIFIED]` against the Next.js static export documentation:

| Setting | Value | Reason |
|---|---|---|
| `output` | `'export'` | Emits `out/` with one HTML file per route |
| `images.unoptimized` | `true` | The default image loader requires a server and is unsupported |
| `basePath`, `assetPrefix` | `/Origami` | Project sites serve from a repository subpath, so links and assets need the prefix |
| `trailingSlash` | `true` | Emits `/faq/index.html`, which static hosts resolve more predictably |
| `public/.nojekyll` | empty file | GitHub Pages runs Jekyll, which ignores underscore-prefixed directories, and Next.js emits everything into `_next/`. Without this the site deploys successfully, renders unstyled, and 404s every asset. |

`basePath` and `assetPrefix` become unnecessary if a custom domain is added later, since the site then serves from root.

Next.js maintains an official [deploy-github-pages template](https://github.com/nextjs/deploy-github-pages), referenced from its static export documentation. Use it rather than assembling this configuration by hand.

### 5.4 One prerequisite in the current code

`[VERIFIED]` Route Handlers that read from `Request` are unsupported in static export, and `frontend/app/api/chat` is exactly that.

This costs nothing, because §3.5 already deletes it: the desktop renderer moves to Vite and talks to the Python sidecar directly, leaving the Next.js API route with no purpose. It does mean the launch site conversion and the `app/api/chat` deletion are one piece of work rather than two.

Nothing else on the unsupported list, meaning redirects, headers, rewrites, cookies, Server Actions, and incremental static regeneration, is reachable from a site of this scope.

### 5.5 Static does not mean plain

Worth stating because the two get conflated. Static describes where computation happens, not how the page looks. Animation, scroll-linked motion, WebGL, and interactive demos all execute in the visitor's browser and are unaffected by the absence of a server.

The dependencies for this are already present in `frontend/package.json`: `motion` 12.34.3 for animation, Tailwind 4, and the Radix and shadcn primitives. Nothing needs adding.

Two design constraints carry over: light mode only, and no application chrome, since a landing page that looks like a dashboard reads as a screenshot rather than a pitch. Note that light backgrounds are the harder surface to make feel premium, because they expose spacing and alignment errors that dark backgrounds hide. The quality will come from typography and restraint rather than effects. Motion should respect `prefers-reduced-motion`, which is both correct and a competence signal to a developer audience.

### 5.6 Why this is last

A launch site for software nobody can install yet is wasted work, and it would need rewriting once the product's shape settles. Phase 8 is deliberate.

---

## 6. Phase sequence

Each phase leaves a working system. Phases 0 through 2 change no user-visible behaviour.

### Phase 0: portable backend

Pure refactor. The dev workflow keeps working throughout and nothing about Electron appears yet.

- `ORIGAMI_DATA_DIR` in `backend/config.py`. Every path that currently resolves relative to the working directory, meaning Chroma storage, uploads, and digests, resolves under it instead. A packaged application cannot write next to its binary.
- Replace `sentence-transformers` with `fastembed`, removing the transitive Torch dependency. `pyproject.toml` pins `sentence-transformers>=3.0.0` with no direct Torch entry, so the swap is clean at the dependency level. Torch is the single largest contributor to bundle size.
- Print the bound port on stdout so the Electron main process can discover it rather than assuming 8000.

Before this phase closes, run the embedding equivalence check described in `ARCHITECTURE_V2.md` §5. Note that per that section the expected answer is "close but not identical," because `fastembed` ships quantized models, and that this is no longer blocking once `embedding_model` is recorded per segment.

### Phase 1: Electron shell

- Electron main process, `utilityProcess` spawning the Python sidecar, port discovery from stdout, lifecycle management including clean shutdown.
- Renderer migrated from Next.js to Vite, components carried over unchanged.
- Runs from source. No packaging yet.

### Phase 2: packaging, signing, permissions

- Bundle the Python runtime. Electron Forge with DMG and ZIP makers.
- Developer ID signing and notarization wired into the build, not bolted on later.
- All `NS*UsageDescription` keys from §3.3 declared, ahead of the connectors that need them.
- Resolve the `[UNVERIFIED]` Full Disk Access question from §3.3 here, because it determines whether iMessage is schedulable at all.

At the end of Phase 2 there is a signed, installable application with the current feature set. That is the point at which the port has actually happened.

### Phase 3: schema and provenance

`ARCHITECTURE_V2.md` §7 steps 1 through 3. Item and Segment, provenance on every write path, `embedding_model` recorded and backfilled.

This is placed after packaging and before any connector because it is the irreversible step. Every connector built before it would need re-ingesting after it.

### Phase 4: land the in-flight vision work

Fold the uncommitted screenshot, vision, and digest branch onto the new schema. It is already written and it is the natural first non-document Item.

### Phase 5: cost controls

The four levers in `COST_MODEL.md` §3. Tool-definition pruning, the no-polling-with-full-context rule, difficulty-based model routing, and difficulty-based loop bounds. Instrument first so the savings are measured rather than assumed.

### Phase 6: connectors

In the order `ARCHITECTURE_V2.md` §7 sets out: snippets, then Calendar as the first permissioned local source, then the rest of the matrix. Calendar goes first among permissioned sources specifically because its failure mode is silent, so it exercises the §3.3 machinery while the context is fresh.

### Phase 7: editor and density redesign

CodeMirror 6, markdown as source of truth, the interface redesign. After the runtime is stable, not during.

### Phase 8: launch page

§5.

---

## 7. What this plan deliberately does not do

- **No Discord, WhatsApp, or Google Photos API integration.** Per `INTEGRATIONS_RESEARCH.md`, the first two are bannable and the third no longer has a library-read API. Apple Photos is the primary photo surface via PhotoKit; Google Photos is served by Takeout import only, and the Picker API is explicitly not being built.
- **No hosted cloud tier yet.** It is in the product brief as "eventually," and it should stay there. Every architectural decision here keeps it possible, chiefly the per-segment `embedding_model` field, without any of them assuming it.
- **No Windows or Linux build.** The permission model, the sidecar packaging, and the highest-value connectors are all macOS-specific. Adding a second platform before the first one ships would double the surface for no user.
- **No redesign before the port lands.** Phase 7 is late on purpose.
- **No accounts, login, or server-handled forms on the public site, ever.** Per §5.2 this is a standing constraint rather than a current state, and it is what keeps the GitHub Pages decision correct permanently rather than only for now.

---

## 8. Consolidated open questions

| # | Question | Blocks | Where |
|---|---|---|---|
| 1 | Does Full Disk Access follow responsible-process attribution for child processes? | iMessage connector | §3.3, resolve in Phase 2 |
| 2 | How far do quantized `fastembed` vectors diverge from the current ones? | Nothing, once `embedding_model` is recorded | `ARCHITECTURE_V2.md` §5, check in Phase 0 |
| 3 | Does CodeMirror 6 handle inline mixed media acceptably? | Editor choice | §4, spike before Phase 7 |
| 4 | Is the taint rule ergonomically tolerable? | Connector UX | `ARCHITECTURE_V2.md` §3 |
| 5 | Are Google Takeout photo exports practical at personal scale? | The entire Google Photos story, since Takeout is now the only path | `INTEGRATIONS_RESEARCH.md` §3 |
| 6 | Can target users create internal Slack apps in their workspaces? | Slack onboarding | `INTEGRATIONS_RESEARCH.md` §2 |
| 7 | How should threads map onto Items? | Message connectors | `ARCHITECTURE_V2.md` §8 |
