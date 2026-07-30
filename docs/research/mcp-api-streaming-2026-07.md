# MCP, External APIs, and Streaming: Adoption Research

**Date:** 2026-07-28
**Status:** Research complete, no code written
**Reads with:** `docs/ARCHITECTURE_V2.md` §3, `docs/INTEGRATIONS_RESEARCH.md`, `docs/COST_MODEL.md` §3, `docs/ELECTRON_PORT_PLAN.md` §6
**Tagging:** same discipline as `INTEGRATIONS_RESEARCH.md`: `[VERIFIED]` with primary link, `[SECONDARY]`, `[UNVERIFIED]`.

---

## Executive summary

- MCP client support in Python is mature but hit a fault line this exact week: `mcp` 2.0.0 shipped 2026-07-28 with breaking changes, while `langchain-mcp-adapters` 0.3.1 (2026-07-27) declares `mcp>=1.24.0` with no upper bound. Build on 1.29.x and pin `mcp<2` until the adapters declare v2 support.
- The larger gap is internal: `backend/services/agent.py` has no tool-calling loop at all. Adopting MCP means adding one, and that node is exactly where the §3 taint gate must be enforced, structurally, before any MCP tool ships.
- Origami-as-MCP-server should be a separate stdio entrypoint that proxies the sidecar over authenticated localhost HTTP, read-only, off by default. Do not mount streamable HTTP into the FastAPI app: it creates a standing network surface with spec-mandated DNS-rebinding obligations, and the sidecar has no auth today.
- The streaming question is already answered by the code: the backend emits the AI SDK v6 UI message stream over SSE and the frontend consumes it with `DefaultChatTransport`. WebSocket buys nothing on loopback. The whole workstream is two protocol-compliance one-liners plus retargeting the transport during the Vite move.
- The zero-credential surface is larger than the credentialed one. MCP client plus curated local servers, RSS, folder watchers, snippets, and every Apple TCC source need no keys. Only Slack, Google Calendar, Todoist, and the already-required Anthropic key need user setup, and Google's bring-your-own-client path carries a verified 7-day refresh-token trap in Testing status.

---

## 1. MCP client in the Python backend

### 1.1 SDK state

`[VERIFIED]` The official Python SDK released [v2.0.0 on 2026-07-28](https://github.com/modelcontextprotocol/python-sdk/releases), the same day as [v1.29.0](https://pypi.org/project/mcp/), the final v1.x feature release; v1 is now security-fix-only. v2 replaces `FastMCP` with `MCPServer`, unifies the client into a single `Client` object, and supports the 2025-11-25 and 2026-07-28 protocol revisions.

`[VERIFIED]` The current finalized spec is [2025-11-25](https://modelcontextprotocol.info/specification/2025-11-25/changelog/) (async tasks, OIDC discovery, icons); the [2026-07-28 revision is a release candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/) targeted for publication today. Nothing Origami needs depends on either newer revision; tools over stdio have been stable since 2025-03-26.

### 1.2 langchain-mcp-adapters

`[VERIFIED]` [langchain-mcp-adapters 0.3.1](https://pypi.org/project/langchain-mcp-adapters/) released 2026-07-27, actively maintained by LangChain. `MultiServerMCPClient` takes a dict of server configs (`command`/`args` with `transport: "stdio"`, or `url` with `transport: "streamable_http"`), and `get_tools()` / `load_mcp_tools()` return LangChain `BaseTool` objects, with optional explicit session management via context managers. The API is async-only, which fits Origami cleanly: every node in `agent.py` is `async def` and `routes/chat.py` consumes `astream`.

`[VERIFIED]` Its pin is `mcp>=1.24.0` with **no upper bound** (PyPI metadata), so a fresh install today resolves to `mcp` 2.0.0. `[UNVERIFIED]` Whether 0.3.1 works against v2's restructured client; released one day before 2.0.0, it was almost certainly developed against 1.x. Design consequence: pin `mcp>=1.24,<2` explicitly in `pyproject.toml`.

### 1.3 The real integration cost: there is no tool loop

Read from the code, not the docs: the agent is a fixed LangGraph pipeline (`retrieve -> analyze -> save_notes -> review -> final_response`). No `bind_tools`, no `ToolNode`, no `tool_use` blocks; even note edits are parsed out of a JSON blob in `final_response_node`. MCP adoption therefore starts with introducing a tool-calling step (a `bind_tools` model call plus a tool-execution node, or a `create_react_agent` subgraph), and that refactor, not MCP wiring, is the bulk of the effort. It is also an opportunity: a purpose-built tool node is the single choke point where both the taint gate and per-turn tool pruning get enforced.

### 1.4 Transport for locally spawned servers

`[VERIFIED]` The spec [recommends stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): "Clients SHOULD support stdio whenever possible," and its streamable HTTP security section requires Origin validation against DNS rebinding, localhost-only binding, and authentication for local HTTP servers. For servers the sidecar itself spawns, stdio is strictly better: no port, no Origin policy, no auth surface, lifecycle tied to the child process.

Two Electron-specific consequences. First, MCP server children of the sidecar inherit responsible-process attribution to the Origami bundle (per `INTEGRATIONS_RESEARCH.md` §4), so a filesystem server touching TCC-protected folders draws on Origami's `Info.plist` declarations and Full Disk Access state, exactly like the sidecar itself. Second, runtimes: `[VERIFIED]` the [reference servers](https://github.com/modelcontextprotocol/servers) (filesystem, git, fetch, memory, time, sequential thinking; puppeteer is archived) run via `npx` for TypeScript and `uvx` for Python. A packaged app cannot assume Node or uv on the user's machine, so the curated allowlist should prefer Python servers launchable with the bundled interpreter, or Origami must bundle a Node runtime. This is a packaging decision to make in Phase 2, not an afterthought.

### 1.5 Interaction with cost lever 1 (prune tool definitions per turn)

MCP tool definitions are fetched client-side via `tools/list` and cached; they cost tokens only when bound into a model call. Since the adapters hand back a plain Python list, Origami controls the bound subset per request. That makes MCP compatible with `COST_MODEL.md` §3 lever 1 by construction, with one rule: never `bind_tools(all_mcp_tools)`. Extend `classify_query()` to select a named tool group (as the cost model already proposes), resolve the group to a small subset of the cached MCP tool list, and bind only that. Servers can push `listChanged` notifications; treat them as cache invalidation, not as a reason to rebind everything. The failure mode to avoid is precisely the one the cost model documents in Hermes: tool definitions as half of a fixed 6k to 20k token per-request overhead.

### 1.6 Interaction with the taint rule

`ARCHITECTURE_V2.md` §3 says tainted turns lose external-communication tools. Two findings shape how MCP tools map onto that rule.

First, annotations exist but cannot carry the gate. `[VERIFIED]` The spec defines `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`, with conservative defaults (an unannotated tool is assumed destructive and open-world), and states: "clients MUST consider tool annotations to be untrusted unless they come from trusted servers" ([spec, Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)). `[VERIFIED]` The official MCP blog is blunter: a server "can claim `readOnlyHint: true` and delete your files anyway"; real enforcement requires "network controls or sandboxing, not a boolean hint" ([Tool Annotations as Risk Vocabulary](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)).

Second, read versus write is the wrong primary axis. Exfiltration capability is about whether tool **arguments leave the machine**. The reference `fetch` server is read-only and fully exfiltration-capable, because a crafted URL carries the payload outward. So Origami's classification should be a per-tool capability manifest, assigned at install time from a curated registry (and by explicit user choice for anything uncurated):

- `network_egress`: any argument leaves the machine (fetch, send, post). Removed on tainted turns.
- `write_local`: writes outside the user's own store. Removed on tainted turns per §3.
- `read_local`: allowed on tainted turns.
- Separately, `returns_untrusted_content`: the tool's results are third-party bytes (fetch, filesystem over a downloads folder, any message reader). Invoking one taints the remainder of the turn.

Unknown third-party servers default to `network_egress` plus `returns_untrusted_content`, mirroring MCP's own worst-case defaults. Enforcement lives in the tool node: compute taint from retrieved segments' provenance before the first model call, filter the bound tool list, and re-filter after every tool result inside the loop, because taint can arrive mid-turn. The per-action user confirmation that §3 proposes as the escape hatch maps naturally onto MCP hosts' human-in-the-loop guidance in the same spec section.

---

## 2. Origami as an MCP server

### 2.1 SDK and shape

Exposing `query` and `get_item` is a few dozen lines with the decorator API (`FastMCP` on v1, `MCPServer` on v2, decorators unchanged). Results should include provenance fields (`origin`, `trust`, `channel`) so consuming hosts see what Origami knows about trustworthiness.

### 2.2 Transport: separate stdio entrypoint, not a mounted HTTP endpoint

The tempting route, mounting a streamable HTTP MCP app inside the existing FastAPI sidecar, is the wrong one:

- `[VERIFIED]` Local streamable HTTP servers carry mandatory Origin validation and should carry auth ([spec transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)). Today `backend/main.py` has CORS only and **no authentication**; any local process can already read the KB via `localhost:8000`. Adding MCP there widens a surface that should instead be closed (see plan item 1).
- The sidecar's port becomes dynamic in Phase 0 (printed on stdout), so there is no stable URL to hand to hosts.
- `[VERIFIED]` Claude Desktop's native model for local servers is spawning stdio processes from [`claude_desktop_config.json`](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop), with one-click distribution via [.mcpb bundles](https://github.com/modelcontextprotocol/mcpb); Claude Code uses the same shape.

Recommendation: ship `origami-mcp`, a thin stdio executable that proxies the sidecar's localhost API using a loopback auth token. Proxying rather than opening Chroma directly avoids two processes sharing the embedded store (`[UNVERIFIED]` whether concurrent multi-process access to one Chroma persistent store is safe; do not find out in production) and reuses the existing retrieval stack. An "Install to Claude Desktop" action can write the config entry; a `.mcpb` bundle is optional polish later.

### 2.3 Privacy: does this violate the stance?

Mechanically, a host query sends retrieved KB content into that host's model context, which for Claude Desktop means Anthropic's cloud. That is the same class of egress as Origami's own agent calling the Anthropic API, but with two real differences: the selection of what leaves is driven by another product's model rather than the user's direct question to Origami, and the content then lives under that product's data policies. There is also a mirror-image hazard: serving untrusted segments hands ingested prompt-injection payloads into another agent's context, making Origami leg two of someone else's trifecta.

Verdict: not a violation if, and only if, it is opt-in and scoped. Required controls: master toggle off by default; read-only tools only (no write tool, so a compromised host cannot poison the KB); default result scope `trust: trusted` and `origin: self`, with per-source opt-in for counterparty data (iMessage stays excluded by default, consistent with `INTEGRATIONS_RESEARCH.md` §7 on two-party data); provenance labels on every result; a local audit log of what was served to which host. With those, this is the honest version of the feature and a genuinely differentiating one.

---

## 3. Streaming transport

**What exists today (from code):** `backend/routes/chat.py` returns a FastAPI `StreamingResponse` with `media_type="text/event-stream"`, hand-emitting AI SDK v6 UI message stream events: `start`, `text-start/-delta/-end`, `reasoning-start/-delta/-end`, custom `data-action` parts, `finish`, with per-event `providerMetadata.origami` stats. The frontend (`components/chat/chat-panel.tsx`) uses `useChat` with `DefaultChatTransport` pointed at `/api/chat`, a Next.js route (`app/api/chat/route.ts`) that just proxies the byte stream from the sidecar.

**Protocol verdict:** `[VERIFIED]` The [AI SDK stream protocol docs](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) confirm the UI message stream is SSE and list exactly this event vocabulary, including `data-*` parts and, for the future tool loop, `tool-input-*` and `tool-output-*` parts. So the current wiring already implements the expected custom-backend protocol. Two compliance gaps: the docs require the `x-vercel-ai-ui-message-stream: v1` response header and a terminating `data: [DONE]`, and `chat.py` sends neither. It works in practice today, so the transport is tolerant, but both are one-line additions worth making before the Electron move (`[UNVERIFIED]` whether future SDK versions keep tolerating their absence).

**WebSocket?** Not justified. The renderer talks to a loopback sidecar: no intermediary proxies, no buffering middleboxes, no reconnection story worth engineering. The interaction is strictly request-then-stream, which is what POST plus SSE is. Cancellation already works through fetch abort. `[VERIFIED]` The AI SDK docs describe only SSE for this protocol, so WebSocket would mean a custom `ChatTransport` and a bespoke backend protocol for zero user-visible gain. The one future need that smells like WebSocket, server-initiated push such as ingest progress, is better served by a second SSE channel or Electron IPC than by migrating chat.

**Recommendation:** keep fetch plus SSE. During Phase 1 (Vite renderer): point `DefaultChatTransport` directly at the discovered sidecar port, delete the Next proxy (already planned in port plan §3.5/§5.4), update `FRONTEND_URL` CORS for the new origin, add the `v1` header and `[DONE]` terminator, and attach the loopback auth token header.

---

## 4. Zero-credential today vs needs user setup

**Self-addable with zero user credentials** (at most an OS prompt):

| Capability | What the user does |
|---|---|
| MCP client machinery (deps in sidecar) | Nothing |
| Curated stdio MCP servers: filesystem, git, fetch, memory, time | Toggle on; Origami must bundle or verify the `npx`/`uvx` runtime |
| Origami-as-MCP-server (stdio) | Flip a toggle; config written for them |
| Snippet capture | Nothing |
| Local folder watchers | Pick folders in a dialog |
| RSS | Paste a feed URL |
| Apple Calendar and Reminders (EventKit) | Click Allow on the TCC prompt; gated on Phase 2 signing and `Info.plist` keys per port plan §3.3 |
| Apple Photos (PhotoKit) | Click Allow on the TCC prompt; same gate |
| iMessage | Grant Full Disk Access in System Settings; no credentials, but gated on the unresolved FDA attribution question (port plan §8 Q1) |

**Needs user-provided setup:**

| Capability | What the user does |
|---|---|
| Anthropic API key (already required, `backend/config.py`) | Create a key in the Anthropic console, paste it |
| Slack | Create an internal app from Origami's shipped manifest YAML, install to workspace, paste the `xoxp-` token; required because distributed non-Marketplace apps get 15 messages/minute vs about 50,000 for internal apps, `[VERIFIED]` in `INTEGRATIONS_RESEARCH.md` §2 |
| Google Calendar | Create their own Google Cloud project and Desktop OAuth client, paste client ID and secret, complete the loopback consent flow; set publishing status to In production or re-auth weekly |
| Todoist | Paste the personal API token from [integrations settings](https://developer.todoist.com/api/v1/) `[VERIFIED]` |
| Uncurated community MCP servers | Provide command or URL plus whatever keys that server needs; classified exfiltration-capable by default |

**The Google desktop OAuth story, honestly.** `[VERIFIED]` A client ID registration is mandatory; there is no clientless OAuth. `[VERIFIED]` [Installed apps cannot keep secrets](https://developers.google.com/identity/protocols/oauth2/native-app): loopback redirects are supported on desktop and PKCE is supported (recommended, not mandated), and any shipped `client_secret` is public by design. So if Origami ships its own client, the secret-in-binary is normal and sanctioned; the real cost is that Calendar scopes are sensitive, and `[SECONDARY]` an unverified app requesting them shows the "unverified app" warning and is capped at 100 users for the project's lifetime ([Google support](https://support.google.com/cloud/answer/7454865)), which forces the maintainer through brand and scope verification with ongoing overhead. If instead the user creates their own project (the Slack-style posture), there is no cap, but `[VERIFIED]` a project left in Testing status issues [refresh tokens that expire in 7 days](https://developers.google.com/identity/protocols/oauth2#expiration); the walkthrough must have them set the app to In production, unverified, and click through the warning once. Recommendation: bring-your-own client for now, matching the Slack posture; revisit shipping a verified client only if adoption demands it. Apple Calendar remains the primary calendar source either way.

---

## 5. Prioritized adoption plan

| # | Item | Effort | Phase slot (port plan §6) |
|---|---|---|---|
| 1 | Loopback auth token on the sidecar HTTP API. Closes the existing any-local-process exposure; prerequisite for the MCP server proxy | S | Phase 1 |
| 2 | Streaming compliance: `v1` header, `[DONE]`, transport pointed at the sidecar, Next proxy deleted; keep SSE, no WebSocket | S | Phase 1, with the Vite renderer |
| 3 | Tool-calling loop in the agent plus the taint gate enforced in the tool node (capability manifest, provenance-driven filtering, mid-turn re-filtering) | M | Straddles Phase 3 and 4: gate logic needs Phase 3 provenance; ship before any tool does |
| 4 | Tool-definition pruning: `classify_query()` selects tool groups; bind only the group | S | Phase 4, designed together with item 3 |
| 5 | MCP client with a curated allowlist of local stdio servers, off by default; `mcp>=1.24,<2` plus `langchain-mcp-adapters`; runtime bundling decided in Phase 2 packaging | M | Phase 5, alongside connectors |
| 6 | Origami-as-MCP-server: read-only stdio proxy entrypoint, trusted-only default scope, audit log, explicit toggle; `.mcpb` packaging optional later | M | Late Phase 5 or 6, after provenance exists to label results |
| 7 | Credentialed connectors: Todoist token (S), then Google Calendar bring-your-own client (M) with the 7-day caveat documented | S/M | Late Phase 5, per the integrations matrix |

Deliberate non-adoptions: no WebSocket migration, no streamable HTTP MCP endpoint mounted in the sidecar, no shipped shared Google OAuth client for now, and no `mcp` 2.0 until `langchain-mcp-adapters` declares support.

---

## Sources

- [MCP Python SDK releases (v2.0.0, v1.29.0)](https://github.com/modelcontextprotocol/python-sdk/releases)
- [mcp on PyPI](https://pypi.org/project/mcp/)
- [langchain-mcp-adapters on PyPI](https://pypi.org/project/langchain-mcp-adapters/)
- [MCP spec: Transports (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [MCP spec: Tools (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP blog: Tool Annotations as Risk Vocabulary](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)
- [MCP blog: 2026-07-28 release candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
- [MCP 2025-11-25 changelog](https://modelcontextprotocol.info/specification/2025-11-25/changelog/)
- [Reference MCP servers](https://github.com/modelcontextprotocol/servers)
- [Claude Desktop: local MCP servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [MCPB desktop extensions](https://github.com/modelcontextprotocol/mcpb)
- [AI SDK: Stream Protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)
- [Google: OAuth 2.0 for native apps](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Google: refresh token expiration](https://developers.google.com/identity/protocols/oauth2#expiration)
- [Google: unverified apps](https://support.google.com/cloud/answer/7454865)
- [Todoist API](https://developer.todoist.com/api/v1/)

Repo files read: `/Users/generalcorn/Desktop/Projects/Origami/Origami/docs/{ARCHITECTURE_V2,INTEGRATIONS_RESEARCH,COST_MODEL,ELECTRON_PORT_PLAN}.md`, `backend/services/agent.py`, `backend/main.py`, `backend/routes/chat.py`, `backend/config.py`, `backend/pyproject.toml`, `frontend/lib/api/chats.ts`, `frontend/app/api/chat/route.ts`, `frontend/components/chat/chat-panel.tsx`, `frontend/package.json`.
