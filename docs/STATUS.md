# Status

Last updated 2026-07-30.

The port has happened. Origami is a desktop application that starts its own backend, packages into a DMG with a Python runtime inside, and stores everything under one schema with provenance on every write. What it cannot yet do is prove itself end to end, because no chat turn has ever run against a live model, and it cannot hold a macOS permission, because there is no signing identity.

The launch site is live at https://generalcorn.github.io/Origami/.

## What shipped

| Phase | State | What landed |
|---|---|---|
| Prerequisite | Done | Screenshot vision and digest pipeline |
| 0, portable backend | Done | `ORIGAMI_DATA_DIR` for every write path, `fastembed` replacing `sentence-transformers` so torch is gone, port announced on stdout |
| 1, Electron shell | Done | Main process owns the sidecar lifecycle, Vite renderer off Next.js, loopback auth token, AI SDK stream compliance, frameless native window chrome |
| 2, packaging | Done | Bundled relocatable CPython, Forge with DMG and ZIP, all four `NS*UsageDescription` keys, signing wired but env-gated |
| 3, schema | Done | Item, Segment and Provenance, written on every path, `embedding_model` recorded and backfilled |
| 4, cost controls | Done | Usage ledger, one model chokepoint, loop bounds, routing, background-context rule. Lever 1 blocked, see below |
| §7 steps 4 and 5 | Done | Vision on the schema with OCR kept as its own segment, snippet capture |
| 7, launch site | Done | Static export on GitHub Pages, deploys on push to `main` |

Backend has 212 passing tests. There is no renderer test suite, so any claim that the interface still works rests on manual checks.

## Blocked, and on what

Everything here is waiting on something only the maintainer can provide.

| Blocked | Waiting on | Cost | Unblocks |
|---|---|---|---|
| Signing and notarization | An Apple Developer Program membership, then a Developer ID certificate in the login keychain plus Apple ID, team ID, and an app-specific password for `notarytool` | $99/yr | Every permissioned source: Calendar, Reminders, Photos, iMessage. macOS binds a permission grant to a signing identity, so an unsigned build presents as a new app on each rebuild and loses its grants |
| End-to-end chat verification | An `ANTHROPIC_API_KEY` in `backend/.env.local` | usage-based | Proof the app works at all, plus the first real numbers in the usage ledger |
| Measured cost savings | The same key, then a day of ordinary use | none beyond the above | Phase 4's levers are proven by test but no dollar saving has ever been measured |
| Full Disk Access inheritance | Granting FDA to a built bundle, then re-running the probe without rebuilding | none | Decides whether iMessage ingestion is possible at all, and if so whether the read lives in the sidecar or the main process |
| Local text generation | A decision, not a credential | none | See "Open decisions" |

### Finishing the Full Disk Access probe

The harness is committed. Build the app, grant Full Disk Access to that exact bundle, then run the probe against the same bundle without rebuilding in between, because an ad-hoc identity changes on every rebuild and a grant does not carry.

```bash
cd desktop
npm run bundle:python && npm run package
# grant Full Disk Access to out/Origami-darwin-arm64/Origami.app in System Settings
./out/Origami-darwin-arm64/Origami.app/Contents/MacOS/Origami --tcc-probe
```

Baseline with no grant, confirmed on 2026-07-30:

```
TCC_PROBE chat.db parent=denied EPERM errno=-1
TCC_PROBE chat.db child=denied errno=1
```

`parent=readable child=readable` means the sidecar inherits the grant and can read `chat.db` itself. `parent=readable child=denied` means Full Disk Access does not follow the responsible-process rule, and the read has to move into the Electron process with rows passed to the sidecar over IPC. See `INTEGRATIONS_RESEARCH.md` §4.

## Open decisions

**Local text generation.** `ollama.py` was deleted in `df2993e`, and `OLLAMA_MODEL` survives in `config.py` imported by nothing. Screenshot vision still runs locally. Restoring a local text tier is deliberately out of scope for Phase 4, and `resolve_model()` in `services/llm.py` is the seam it would go through, which makes it a one-function change rather than a refactor. The standing recommendation is to measure first: the highest-volume call is `contextualize`, once per chunk at ingest, and it is mechanical enough that a small local model is unlikely to do damage, whereas `final_response` is where a weak model turns a cheap answer into a confident wrong one.

**Tool-definition pruning, cost lever 1.** Blocked rather than deferred. There is no tool-calling loop in the codebase: `bind_tools`, `ToolNode`, `create_react_agent` and `tool_choice` all return zero hits. Building tool-group machinery for tools that do not exist would be speculative. The loop is also where the taint gate has to be enforced, so the two arrive together.

**MCP client and Origami as an MCP server.** Designed, and deliberately parked until real users exist. Both add moving parts against evidence that fragility is the main reason people abandon tools like this, and the server direction sits in tension with the claim that the corpus stays on the machine. If it ships, the public wording has to become "nothing leaves without an explicit per-source grant" first.

**Windows and Linux.** The shell is Electron so both are reachable, but there is no packaging target for either, and the Windows title-bar path was written against the API and never run. Worth noting that an MIT licence plus GitHub distribution normally reaches an audience skewed toward Linux and Windows, which a macOS-only binary cannot serve.

**Meetings and audio.** Not in the integrations matrix, and raised as a possible source. Two routes exist. A browser extension only reaches meetings held in a browser tab, so it misses the native Zoom, Teams, Tencent Meeting and ClassIn clients. Capturing system audio through ScreenCaptureKit reaches all of them, because it takes the output rather than hooking any one application, and it is the route the local-first competitor in this space takes with on-device transcription.

Two things gate it. System audio capture sits behind a macOS permission that an unsigned build cannot hold, so it waits on the same Developer ID as everything else. More importantly it is the most consent-fraught source in the whole product: the user research found that recording a call captures the other party too, and that this reads as a decision made on their behalf rather than a private one. Several jurisdictions require all-party consent. If this is built, the consent surface is the design problem, not the capture. Needs its own research pass before it earns a place in the matrix.

## What to pick up next

In rough order of value over risk.

1. **Add an API key and use the app for a day.** It is the cheapest action with the highest information return: it proves the app works, fills the usage ledger with real numbers, and turns the local-generation question from a guess into a measurement.
2. **Enrol in the Apple Developer Program.** Long lead time, and everything permissioned waits behind it.
3. **Finish the Full Disk Access probe** once a signed or at least stable bundle exists.
4. **Phase 6, the editor.** `EDITOR_DECISION.md` confirms CodeMirror 6 and names the real work: caret semantics at widget boundaries, which the spike got wrong in a way that silently corrupts markdown. The interface redesign alongside it is a design workstream, not a specified task.
5. **The tool loop with its taint gate**, which unblocks cost lever 1 and every MCP item.

## Known gaps worth remembering

- No renderer test suite anywhere, so interface regressions are invisible to CI.
- The app is 718 MB installed, past the 400 MB mark at which `ELECTRON_PORT_PLAN.md` §3.1 says the Electron decision should be revisited. Electron is 275 MB of it and three unused Python dependencies account for 84 MB.
- Only `arm64` is built. No Intel or universal build has ever been produced.
- First run downloads the embedding model from Hugging Face, so a packaged first launch needs network unless the model is bundled.
- There is no telemetry and no crash reporting by design, which also means there is no way to learn that something broke for someone.
