# Integrations Research

**Date:** 2026-07-26
**Status:** Research complete, no code written
**Supersedes:** an earlier draft of this document that was lost with a deleted cloud session

## How to read this document

Every factual claim carries a tag:

- `[VERIFIED]` means the claim was checked against a primary source, meaning vendor documentation or the vendor's own changelog. The source is linked inline.
- `[SECONDARY]` means the claim rests on credible reporting or community documentation, but the vendor's own page could not be retrieved directly.
- `[UNVERIFIED]` means the claim is a reasonable inference that nobody has confirmed. Do not build against an `[UNVERIFIED]` claim without testing it first.

The previous version of this document was produced without a single primary source being fetched. It read as authoritative and was not. The tags exist so that failure cannot repeat silently.

---

## 1. The ship / opt-in / never matrix

| Source | Verdict | Reason |
|---|---|---|
| Loose text snippets | **Ship** | No third party involved. Pure local capture. |
| Local files and PDFs | **Ship** | Already working today. Extends cleanly. |
| Screenshots and images on disk | **Ship** | Already working in the uncommitted vision/digest branch. |
| Apple Calendar and Reminders | **Ship**, with a hard TCC prerequisite | EventKit is a first-class local API. See §4 for the blocker. |
| Apple Photos | **Ship**, with the same TCC prerequisite | PhotoKit is local. Same blocker as Calendars. |
| iMessage | **Opt-in**, gated behind Full Disk Access | Local SQLite read. Legal and technically routine, but maximally sensitive. |
| Slack | **Opt-in**, bring-your-own app manifest only | A shared distributed app is rate-limited into uselessness. See §2. |
| Google Calendar | **Opt-in** | Standard OAuth, no restriction found. |
| Todoist and similar task apps | **Opt-in** | Standard REST APIs. |
| **Google Photos** | **Never** via API; **opt-in** as a Takeout import | The library-read scopes no longer exist. See §3. |
| **Discord** | **Never** for personal accounts | Automating a user account is a bannable offence. See §5. |
| **WhatsApp** | **Never** | No sanctioned path exists for personal message access. See §6. |

Three of the sources named in the product brief land in the "never" column. That is the single most important output of this research, and it is a change from the previous plan, which treated all of them as buildable.

---

## 2. Slack: the inherited claim survives, and understates the problem

The previous plan claimed that a distributed app on a shared `client_id` gets 15 messages per minute while a user's own internal app gets 1,000 per request. This was checked against Slack's own changelog and it is **correct**.

`[VERIFIED]` Slack's [rate limit changelog for non-Marketplace apps](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/) states that for commercially distributed apps outside the Marketplace, `conversations.history` and `conversations.replies` are limited to **1 request per minute returning a maximum of 15 objects**. The same document states that internal customer-built apps retain **"1,000 messages per request at 50+ requests per minute"**.

The practical ratio is worse than the original framing suggested:

| App type | Ceiling |
|---|---|
| Non-Marketplace distributed | 15 messages/minute |
| Internal customer-built | 50,000 messages/minute |

That is a factor of roughly 3,300. Backfilling a single busy channel of 100,000 messages would take **over four days** of continuous polling as a distributed app, and about two minutes as an internal app.

`[VERIFIED]` Marketplace-listed apps are also exempt from the reduction, per the same changelog.

`[SECONDARY]` Enforcement dates: new installations became subject to the new limits on 2025-05-29, and existing installations of unlisted distributed apps were moved onto them on 2026-03-03. The second date comes from search-surfaced summaries of Slack's changelog rather than a page fetched directly, so treat the exact day as `[SECONDARY]`. It is in the past either way, so the limits are fully in force today.

### Design consequence

Origami must **not** ship a Slack app that users install from a shared client ID. The user creates their own internal Slack app in their own workspace and pastes in the token. Origami ships the app manifest YAML and a walkthrough, not the app itself.

`[VERIFIED]` Slack supports exactly this flow. [App manifests](https://docs.slack.dev/app-manifests/configuring-apps-with-app-manifests/) are a single YAML file describing display info, scopes, events and settings, which is precisely the artifact to ship. `[VERIFIED]` [User tokens](https://api.slack.com/authentication/token-types) (`xoxp-`) represent the same access the user already has to the workspace, which is the correct permission model for a personal knowledge tool.

`[UNVERIFIED]` Whether a personal internal app created in a workspace the user does not administer will be approvable by that workspace's admins. In many corporate workspaces app installation is restricted. This affects onboarding conversion, not technical feasibility, and needs a real-world test.

---

## 3. Google Photos: the requirement as stated is not buildable

This is the finding that most directly contradicts the product brief, and the previous plan missed it entirely.

`[VERIFIED]` Per Google's own [Updates to the Google Photos APIs](https://developers.google.com/photos/support/updates), the `photoslibrary.readonly`, `photoslibrary.sharing`, and `photoslibrary` scopes **were removed on 2025-03-31**. Calls using them now return `403 PERMISSION_DENIED` for all clients.

`[VERIFIED]` The surviving scopes are `photoslibrary.appendonly`, `photoslibrary.readonly.appcreateddata`, and `photoslibrary.edit.appcreateddata`. Per the same page, an app can "only list, search, and retrieve albums and media items that were created by your app."

An app can therefore read back only what it itself uploaded. There is no longer any API by which Origami can enumerate, search, or embed a user's existing Google Photos library.

`[VERIFIED]` The sanctioned replacement is the [Picker API](https://developers.googleblog.com/en/google-photos-picker-api-launch-and-library-api-updates/), in which the user manually selects specific photos or albums through the Google Photos interface, per session.

### Design consequence

"Ingest my Google Photos" becomes "import a selection from Google Photos," which is a materially different product promise and a much worse one for an ambient personal knowledge base. A picker-based flow cannot support background sync, and it cannot support "search everything I have ever photographed."

**Decided 2026-07-26: Apple Photos is the primary photo surface, and Google Photos is served by Takeout import only.** PhotoKit still grants full local library access on macOS, which preserves the ambient, background-sync behaviour the product needs. Google Photos users get a one-time Takeout bulk import, which sidesteps the API entirely and is the only remaining route to library-wide coverage.

The Picker API is explicitly **not** being built. It cannot sync in the background, so it would add a whole OAuth surface in exchange for a promise materially weaker than the one Takeout already delivers.

`[UNVERIFIED]` Whether Google Takeout exports are practical to ingest at personal-library scale, meaning tens of thousands of images with sidecar JSON metadata, has not been tested. Since Takeout is now the sole Google Photos path rather than one option among several, this spike is load-bearing and should run before the photo work is scheduled.

---

## 4. macOS TCC: the sidecar question is answered, and the failure is silent

The previous plan flagged this as an open question: does a spawned Python sidecar inherit the Electron bundle's TCC grant, or does it need its own? It correctly identified this as deciding the process architecture. Here is the answer.

`[VERIFIED]` Child processes do **not** inherit the parent's TCC permissions. Per the [VS Code issue tracking this exact problem](https://github.com/microsoft/vscode/issues/307364), macOS "traces up the process tree and identifies VS Code as the responsible process." The system then checks whether that **responsible process** carries the corresponding `NS*UsageDescription` keys in its `Info.plist`.

`[VERIFIED]` The resources affected, per the same issue, are: Photo Library, Speech Recognition, Contacts, **Calendars**, **Reminders**, Location Services, Local Network discovery, and Media Library. Camera, Microphone, and Apple Events were previously fixed and behave correctly.

`[VERIFIED]` When the usage description key is absent, "access is silently denied with no dialog or error message."

Read that last point twice. Calendars and Reminders are both on the affected list and both are named in the product brief. A Python sidecar calling EventKit inside an Electron app whose `Info.plist` lacks `NSCalendarsUsageDescription` will not error, will not prompt, and will return empty results. That is the worst available failure mode, because it is indistinguishable from an empty calendar.

### The two remedies

1. **Declare the keys on the Electron app.** Add every `NS*UsageDescription` key the sidecar will ever need to the Electron `Info.plist` at the build signing step. The prompt is then attributed to Origami, which is also the correct user-facing behaviour.
2. **Disclaim responsibility so the sidecar answers for itself.** `[VERIFIED]` Electron's [`utilityProcess`](https://www.electronjs.org/docs/latest/api/utility-process) accepts a macOS-only `disclaim` option which causes "the utility process will disclaim responsibility for the child process," making the OS treat it as a separate entity for TCC. `[VERIFIED]` The underlying primitive is `responsibility_spawnattrs_setdisclaim()`, named as the long-term fix in the VS Code issue.

Remedy 1 is correct for Origami. Remedy 2 exists for launching untrusted third-party code, which the sidecar is not, and it fragments the permission story across two bundle identities.

### Code signing

`[VERIFIED]` TCC associates a grant with the app's code signature, bundle identifier, and on-disk path. `[SECONDARY]` Ad-hoc and unsigned builds regenerate their signature on every build, so TCC treats each rebuild as a new application and grants do not persist. OpenClaw's own [macOS permissions documentation](https://docs.openclaw.ai/platforms/mac/permissions) states that all builds must use real Apple Development or Developer ID certificates, and that permissions should be granted to a signed bundle with its own identifier rather than to a shared runtime such as `node`.

**Correction to the inherited claim.** The previous plan asserted that Full Disk Access is "revoked on every update." That is true for unsigned and ad-hoc builds, where the identity changes each rebuild. It is **not** true for a build signed with a stable Developer ID, where grants survive updates normally. The operative requirement is a stable signing identity, not a property of updates as such.

`[UNVERIFIED]` Whether Full Disk Access, which is path-based rather than mediated by an `NS*UsageDescription` key, behaves the same way for child processes as the API-gated permissions above. FDA is the mechanism iMessage ingestion depends on, so this needs its own test rather than an assumption. See §7.

---

## 5. Discord: bot accounts only, which excludes the interesting data

`[SECONDARY]` Discord's support documentation on [automated user accounts](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots) prohibits automating a normal user account outside the OAuth2 bot API, and states this can result in account termination. The page returned HTTP 403 to direct fetching, so this rests on the search-surfaced summary and on corroborating community documentation rather than a directly retrieved vendor page.

The sanctioned path is a bot account, which can only see servers it has been explicitly invited to. It cannot read the user's direct messages, and it cannot read servers where the user lacks permission to add a bot, which in practice is most of them.

### Design consequence

Discord cannot deliver the "everything I have ever discussed" promise. A bot integration is buildable for servers the user controls, and that is a narrow and much less valuable slice. Recommend deferring Discord entirely rather than shipping something that reads as broken relative to the pitch.

---

## 6. WhatsApp: no legitimate path exists

`[SECONDARY]` Automating the WhatsApp consumer app through unofficial clients or scripts violates the terms of service, and the WhatsApp Business API is the only sanctioned automation route. Third-party clients such as GB WhatsApp and WhatsApp Plus are detected and result in account bans, frequently permanent. This is well attested across multiple independent sources but was not confirmed from a Meta-published policy page directly.

The Business API serves business accounts messaging customers. It is not a route to a personal account's message history.

### Design consequence

WhatsApp is a hard "never." Building it would put the user's own primary messaging account at risk of permanent ban, which is an unacceptable thing to ship to a user regardless of demand. If WhatsApp coverage is important, the only defensible route is the user's own manual chat export, which WhatsApp offers natively, handled as a file import rather than as an integration.

---

## 7. iMessage: technically routine, ethically the sharpest edge

`[SECONDARY]` The Messages database is a SQLite file at `~/Library/Messages/chat.db`, and reading it requires Full Disk Access. Multiple mature open-source tools read it this way, and it is a well-trodden path.

There is no terms-of-service problem here. This is the user's own local file on their own machine.

The problem is that a message database is inherently **two-party** data. Every ingested message has a sender who never consented to being embedded into an AI system. This does not make ingestion wrong, but it does make silent or default-on ingestion wrong.

### Design consequence

iMessage must be off by default, enabled through an explicit flow that states plainly what is being read, and it should support per-contact exclusion. It should never be part of a "connect everything" onboarding sweep.

---

## 8. The lethal trifecta: confirmed, with one leg misdescribed

`[VERIFIED]` The concept is Simon Willison's, published 2025-06-16 as [The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/). The three legs are: **access to private data**, **exposure to untrusted content**, and **the ability to communicate externally**.

**Correction to the inherited claim.** The previous plan described the third leg as "an agent with tools." That is imprecise in a way that matters. The dangerous capability is *external communication*, meaning the ability to move data outward. An agent with tools that cannot reach the network or otherwise emit data is not carrying the third leg. This distinction changes the mitigation: the goal is to break the exfiltration path, not to reduce tool count.

`[VERIFIED]` The mitigation posture is structural. The recommended approach is to audit every tool against the three capabilities and guarantee that at least one leg is missing on any execution path. Prompt hardening alone cannot resolve it, because models cannot reliably separate instructions from data.

### Why this is acute for Origami specifically

Origami is a maximally exposed instance of this pattern. Leg one is the entire product: a personal corpus of documents, messages, photos, and calendar. Leg two arrives the moment any connector ingests content written by someone else, which is every connector in §1 except loose snippets. Leg three appears as soon as the agent gains a web-fetch tool or any send capability.

The previous plan's conclusion, that provenance and taint tagging must exist before the first connector rather than after, is **correct and should be kept**. It is the load-bearing architectural decision in this whole effort. Retrofitting provenance onto an existing store means re-ingesting everything, and the cost only grows.

---

## 9. What remains unverified

Carried forward deliberately. None of these should be built against without a test first.

1. Whether Full Disk Access behaves like the `NS*UsageDescription` permissions with respect to child-process responsible-process attribution. Decides whether iMessage ingestion works from the sidecar. §4.
2. Whether `fastembed`'s default quantized ONNX build of `bge-small-en-v1.5` produces vectors identical to the `sentence-transformers` build. BAAI documents that unquantized ONNX matches Torch output, but `fastembed` ships a quantized model, and quantization is not output-preserving. Decides whether the existing Chroma store survives the Torch removal. See the architecture document.
3. Whether Google Takeout photo exports are practical to ingest at personal-library scale. §3.
4. Whether internal Slack app creation is permitted in the workspaces target users actually belong to. §2.
5. The exact enforcement date on which Slack moved existing unlisted installations onto the reduced limits. Immaterial to the design, since it has passed. §2.

---

## Sources

- [Updates to the Google Photos APIs](https://developers.google.com/photos/support/updates)
- [Picker API launch and Library API updates](https://developers.googleblog.com/en/google-photos-picker-api-launch-and-library-api-updates/)
- [Slack: Rate limit changes for non-Marketplace apps](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/)
- [Slack: Configuring apps with app manifests](https://docs.slack.dev/app-manifests/configuring-apps-with-app-manifests/)
- [Slack: Token types](https://api.slack.com/authentication/token-types)
- [VS Code issue 307364: child processes cannot access TCC-protected resources](https://github.com/microsoft/vscode/issues/307364)
- [Electron utilityProcess API](https://www.electronjs.org/docs/latest/api/utility-process)
- [OpenClaw macOS permissions](https://docs.openclaw.ai/platforms/mac/permissions)
- [Simon Willison: The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- [Discord: Automated user accounts (self-bots)](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots)
