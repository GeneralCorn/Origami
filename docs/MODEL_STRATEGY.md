# Model Strategy

**Date:** 2026-07-30
**Status:** Decision document. No code written.
**Question:** can Origami stop depending on frontier Anthropic and OpenAI models?

Evidence tags follow the convention in [COST_MODEL.md](COST_MODEL.md). `[VERIFIED]` means checked against the repo, the installed venv, or a primary source in this session. `[SECONDARY]` means a single external source, a vendor's own benchmark, or a figure I could not independently reproduce. `[UNVERIFIED]` means arithmetic or inference on top of assumptions, including my own.

---

## 1. The direct answer

**PARTIAL, and considerably smaller than it first looks.**

OpenAI: **YES, already done.** `[VERIFIED]` There is no OpenAI dependency in the backend. Grep for "openai" across `backend/` excluding the venv returns nothing in any `.py` or `.toml`. Embeddings run locally through `bge-small-en-v1.5` (`config.py:60`). `COST_MODEL.md` §1 discusses `text-embedding-3-small` as a priced comparison, not as something Origami calls. There is nothing to migrate.

Anthropic: **ONE call site of six can move today, and it should, but not for the reason the cost model suggests.** `contextualize` can run on local open weights. `classify` and `review` can move later, conditionally, and buy almost nothing. `analyze`, `fast_fact`, `final_response`, and the planned tool loop cannot move at any model size that fits a consumer Mac.

The conditions, stated up front because they change the shape of the decision:

1. **There is no recurring cost saving available.** `[VERIFIED]` `Purpose.CONTEXTUALIZE` is reachable only from `services/ingest.py:156` and `services/indexing.py:124`, both ingest paths. It never appears on the query graph. Once a user's library is loaded, moving contextualize local saves **$0.00 per month**. What it saves is a one-time library-loading charge of roughly $25 to $45. Section 3 works this through, and it is the single most important correction in this document.
2. **The privacy argument is therefore the whole argument, and it is strong enough on its own.** `[VERIFIED]` `contextualize` ships `document_prefix(whole_document)` truncated to `CONTEXT_DOC_CHARS = 24000` (`config.py:91`, `ingest.py:124`), once per chunk. A 43-page paper means 76 copies of the user's document leaving the machine. No other call site sends whole documents. Moving this one call site eliminates all whole-document egress. That is worth doing at zero cost saving.
3. **Every dollar figure in this document, including mine, is modeled rather than measured.** `[VERIFIED]` `backend/usage/usage-2026-07.jsonl` contains exactly one row and it is `"stub": true`. `cache_read_tokens` has never been non-zero in this repo's history. The 5.09x caching advantage that the whole economic argument rests on has never been observed. Section 4 Step 0 fixes this for about $0.13.
4. **"The corpus never leaves the machine" is currently false, and the README states it in a form that is worse than false.** `[VERIFIED]` `README.md:5` reads "Everything runs on your machine. No API key, no account, no data leaving your computer," while line 84 lists an Anthropic key as a hard requirement and line 144 says "Every agent and ingestion call uses it." The honest disclosure exists at line 29 but the headline contradicts it. This is a one-line fix and it should land before any migration work, not after.

The framing that matters most: **"stop depending on frontier models" and "the corpus never leaves the machine" are different goals, and only local inference serves both.** Third-party open-model hosting (Groq, DeepInfra, Together, Fireworks) serves the first while actively damaging the second. Section 7 treats that as a positioning regression, not a neutral tradeoff.

---

## 2. Per-call-site recommendation

| # | Call site | Today (verified in code) | Recommended | Local or hosted | Reasoning |
|---|---|---|---|---|---|
| 6 | **contextualize** | Haiku 4.5, `max_tokens=100`, temp 0.0, cached prefix | Gemma 4 E4B or 12B, or Qwen3-8B, decided by the §4 Step 2 eval | **LOCAL**, gated on eval and on a managed Ollama | The only call site that sends whole documents, and the only one where a bad output cannot produce a false citation. `rag.py:56` returns `metadata.get("original_chunk") or doc` as the citable `text` while the blurb lives only in `embedded_text`, so blurb quality affects recall and nothing else. Background work, so latency is absorbed. Zero recurring cost saving; do it for the egress. |
| 1 | **classify** | Haiku 4.5, `max_tokens=10`, temp 0.0 | **Keep Haiku** for now | HOSTED | Worth **2.8% of a `normal_rag` turn**. `[UNVERIFIED]` A ~700-token prompt at ~180 tok/s prefill is ~3.9s before the first token, against the 1-2s `COST_MODEL.md` §4 attributes to the current Haiku call, so a local swap is a latency regression on the hot path unless a ≤2B model stays permanently resident. On 16GB that conflicts with VLM co-residency. Revisit only at 24GB+ with measured p50. |
| 4 | **review** | Haiku 4.5, `max_tokens=256`, temp 0.0 | **Keep Haiku** | HOSTED | Output contract is two literal shapes (`COMPLETE` / `INCOMPLETE: <query>`), so malformed output is structurally preventable, but review *steers retrieval*: a weak refined query degrades the notes that reach synthesis. Runs only on `deep_research`, 2 calls per turn, **5.9% of that route**. Low reward, real risk, and no recurring money in it. |
| 3 | **analyze** | Haiku 4.5, `max_tokens=2048`, temp 0.0, up to 3/turn | **Keep Haiku** | HOSTED | This is the note stream `final_response` synthesizes. Its prompt carries a nuanced *negative* constraint ("Text marked WRITTEN BY A MODEL is a description of the source, not a quotation") that small models routinely drop, and violating it means Origami states model-written descriptions as source facts. It also runs in the long-context multi-turn regime where small models degrade hardest. |
| 2 | **fast_fact** | Haiku 4.5, `max_tokens=1024`, temp 0.3 | **Keep Haiku** | HOSTED | Closed-book conversational answering, so the open-model grounding regression does not bite, but it is user-visible, latency-sensitive, and worth $0.0028 per turn. A local model's knowledge cutoff is a real regression here. No economic reason to touch it. |
| 5 | **final_response** | Sonnet 4.6 with notes; **already downgrades to Haiku when `has_notes` is false, and on `normal_rag` behind `ORIGAMI_CHEAP_FINAL`** | **Keep Claude** | HOSTED | Emits one JSON object containing markdown, double-escaped LaTeX, and an action-routing decision that writes to the user's files. `_extract_json` already needs four recovery strategies against Sonnet. The binding reasons are long-context multi-turn synthesis and the attribution rule, not grammar compliance. See the correction in §8.4. |
| n/a | **vision** (existing) | `qwen2.5-vl:7b` via Ollama, `services/vision.py` | Keep, and **fix the dependency before adding a second local model** | LOCAL (already) | `[VERIFIED]` This path is unexercised on the maintainer's own machine: `ollama list` shows only `deepseek-r1:8b`, so `check_ollama_health()` returns False here today. Consolidating vision and contextualize onto one multimodal Gemma 4 is attractive on 16GB but is downstream of §4 Step 1, not a free win. |

### Model candidates for contextualize

`[VERIFIED]` License and redistribution: `google/gemma-4-12B`, `-E4B`, `-E2B`, `Qwen/Qwen3-8B`, `Qwen/Qwen2.5-VL-7B-Instruct` and `openai/gpt-oss-120b` are all Apache 2.0, ungated, with no region or use restrictions, checked against the Hugging Face API rather than the model cards. Gemma 4's move to Apache 2.0 is confirmed against Google's open source blog dated 2 April 2026. The entire §10 revisit path is also clean: Qwen3.5-9B/4B/0.8B, Qwen3.6-27B/35B-A3B, `ibm-granite/granite-4.1-8b`/`3b`, `allenai/OLMo-3-7B-Instruct` and `mistralai/Ministral-3-8B-Instruct-2512` are Apache 2.0; `zai-org/GLM-4.6` is MIT. **The concern about Chinese model licenses carrying use restrictions or region clauses does not bite for any model considered here, recommended or rejected.**

`[VERIFIED]` Gemma 4 thinking is **off by default**, and it has native system-prompt and tool-calling support. This matters concretely: Qwen3.5/3.6 ship thinking **on** by default, which fails `classify` outright at `max_tokens=10` because the `<think>` block consumes the entire budget before the label appears. `strip_think_tags` in `services/text_utils.py` cleans the output but cannot recover a spent budget.

**Do not pick the model on a leaderboard.** `[VERIFIED]` The Vectara HHEM figures are real (`qwen3-8b` 4.8%, `gemma-4-26b-a4b-it` 5.2%, `qwen3.5-27b` 12.1%, `ministral-3-8b-2512` 21.7%, Phi-4 3.7% at an 80.7% answer rate), and they do show a real 2026-generation faithfulness regression. But HHEM measures whether a model introduces unsupported facts when summarizing. The contextualize task is: given a 24,000-char prefix and one 1,200-char chunk, emit one or two sentences that make the chunk findable in isolation. **A blurb can be perfectly faithful and useless for retrieval.** HHEM cannot rank models on the capability the acceptance gate tests, and it does not score Gemma 4 E2B, E4B, or 12B at all, which are the primary candidates. Treat HHEM as a weak prior for excluding obviously bad models (GLM's small tier at 9.3% to 10.1%; Phi-4's answer rate) and let §4 Step 2 decide.

`[VERIFIED]` Do not build on Llama: `meta-llama`'s newest base release dates to May 2025.

`[SECONDARY]` One artifact-size check to run before pulling anything: Ollama's `gemma4` library reportedly lists `gemma4:e4b` at 9.6GB / 128K context and `gemma4:12b` at 7.6GB / 256K context, which would make the 12B *smaller on disk* than the E4B with double the context. If that holds, the intuitive "small machine gets the small model" tiering is inverted. Check `ollama show` before committing to a tier table.

---

## 3. The money, and why it is not the reason to do this

All figures recomputed in-session by calling `services.pricing.cost_usd` directly, with the repo's real constants (`CHUNK_SIZE=1200`, `CHUNK_OVERLAP=300`, `CONTEXT_DOC_CHARS=24000`, `max_tokens=100`).

`[VERIFIED]` Marginal steady-state cached chunk: **$0.001320**. Uncached: **$0.006720**. Ratio **5.09x**. First chunk against a cold cache: **$0.008220** (the 1.25x write multiplier).

### A finding that falls out of the arithmetic

`[VERIFIED]` `ingest.py:259` runs contextualize behind `asyncio.Semaphore(4)`. Four concurrent slots against a cold cache means **four cache writes per document, not one**. Reproduced exactly:

| Corpus | Chunks | 4-slot (as shipped) | 1-slot | Uncached |
|---|---|---|---|---|
| 10-page paper | 18 | $0.051 | $0.031 | $0.121 |
| 43-page paper | 76 | **$0.128** | $0.107 | $0.511 |
| 200-page book | 445 | $0.615 | $0.594 | $2.990 |
| 500-document library | 22,500 | **$43.50** | $33.15 | $151.20 |

**The shipped concurrency costs 19.3% of the ingest bill on a 43-page document**, purely in duplicated cache writes. This is a hosted-path finding, independent of any local migration, and it is the cheapest cost win in this document: serialize the first chunk, then fan out.

`[SECONDARY]` A caveat that makes the "cached" column unreliable for small documents: `document_prefix()` truncates at 24,000 chars but does not pad, and `config.py:83-90` records Anthropic's minimum cacheable prefix for Haiku 4.5 as 4,096 tokens, below which "the cache silently never engages and no error is returned." 4,096 tokens is roughly 16,400 chars of prose. The 10-page row above implies about 16,500 chars. It sits exactly on the floor. Short documents plausibly pay the uncached rate throughout with no signal in the ledger.

### Query path

| Route | Cost/turn | Calls | Distribution |
|---|---|---|---|
| `fast_fact` | $0.00352 | 2 | classify 20.6%, fast_fact 79.4% |
| `normal_rag` | $0.02593 | 3 | classify 2.8%, analyze 19.7%, **final 77.5%** |
| `deep_research` | $0.04412 | 7 | classify 1.6%, 3x analyze 38.8%, 2x review 5.9%, **final 53.7%** |

Call counts are the ones pinned by `tests/test_loop_bounds.py`.

### The correction that changes the recommendation

An earlier draft of this analysis led with "local contextualize captures 71% of a heavy user's monthly bill." **That number is real arithmetic and a misleading claim**, and I am recording why rather than quietly dropping it.

`[VERIFIED]` The heavy-user query bill (200 `fast_fact` + 300 `normal_rag` + 50 `deep_research`) is **$10.69/month and is entirely independent of ingest volume**. The 71% figure is therefore 100% the ingest line, and it requires ingesting 200 forty-three-page documents, about 8,600 pages, **every month in perpetuity**. Contextualize share by documents ingested per month:

| Docs/month | Total/mo | Ingest | Contextualize share |
|---|---|---|---|
| 200 | $36.27 | $25.58 | 70.5% |
| 100 | $23.48 | $12.79 | 54.5% |
| 50 | $17.09 | $6.40 | 37.4% |
| 20 | $13.25 | $2.56 | 19.3% |
| 5 | $11.33 | $0.64 | 5.6% |
| 0 | $10.69 | $0.00 | **0.0%** |

**Ingest is one-time per document. Query cost recurs.** For any user with a stabilizing corpus the share asymptotes to zero. The same document cannot simultaneously argue that a 500-document library is a one-time $43.50 (which is the right way to think about it) and that a heavy user ingests two-thirds of that library every month forever.

**Consequences for the decision:**

- The honest cost claim is: **localizing contextualize saves a one-time $25 to $45 at library-load time and $0.00/month thereafter.**
- The argument "the remaining 9 percentage points are not worth the product" **does not survive**, because the percentages were an artifact of the ingest assumption. The correct version is stronger and simpler: **there is no recurring cost saving available from localizing anything, because 100% of the recurring bill sits on call sites that cannot move.** Keeping `analyze`, `fast_fact`, and `final_response` on Claude is not a $3.48/month concession. It is the entire steady-state bill, and it buys the answer quality the product is for.
- **Move contextualize for the egress, not for the money.** If the privacy case were absent, the cost case alone would not justify the work.

---

## 4. Migration sequence, ordered by value over risk

### Step 0: two things that cost almost nothing and gate everything else

**0a. Fix `README.md:5`.** `[VERIFIED]` The headline claims "No API key, no account, no data leaving your computer" while line 84 requires a key. Line 29 tells the truth. This is the largest privacy-integrity defect in the project today and it is a one-line edit. Do it before any migration work, because the migration is justified as protecting a claim the README currently states in an untrue form.

While editing, add the undisclosed egress. `[VERIFIED]` `agent.py:276` and `agent.py:556` both ship `state["current_note"][:2000]` to `analyze` and to `final_response`, and `agent.py:809/830` passes `current_note` into `classify`. Line 29 discloses that retrieved passages are sent. **It does not disclose that the note the user is actively writing is sent on every routed turn.**

**0b. Spend $0.13 and measure the cache.** `[VERIFIED]` The ledger holds one stub row. `cache_read_tokens` has never been non-zero. `COST_MODEL.md` §6 already names this as the blocker ("A key, one PDF, then `cache_read_tokens` from the ledger"). What §4 actually measured was character counts and prefix identity from dumped stub requests, not billed tokens.

This single number decides whether the rest of this document describes a $36/month problem or a $10/month one, and it cuts both ways: **if the cache does not engage, the true ingest baseline is the uncached column and §7's dismissal of third-party hosting collapses**, because "the 5x lever is already pulled" would be false. Ingest one real PDF with a real key and read the row. It is cheaper than every other step here.

**0c. Do NOT re-point `SONNET_MODEL` to Sonnet 5.** `[VERIFIED]` Three reasons that compound:

1. The introductory rate ($2/$10 vs $3/$15) expires **2026-08-31**. Today is 2026-07-30. That is a 32-day window.
2. Claude 4.7 and later use a newer tokenizer producing **~30% more tokens for the same text**. Sonnet 4.6 uses the previous one. If Sonnet 5 falls under that rule, the effective rate is ~$2.60/$13.00 now (13% below 4.6) and **~$3.90/$19.50 after 1 September, 30% *more expensive* than staying put.**
3. `services/pricing.py:16-20` has no `claude-sonnet-5` entry. Re-pointing the config without adding the rate makes every final synthesis report `priced=False` and land in `unpriced_calls`, which is exactly the "stale price table shows as a gap" signal that entry exists to produce.

`[VERIFIED]` A fourth reason found during privacy review: Anthropic documents Covered Models (Claude Fable 5, Claude Mythos 5) requiring mandatory 30-day retention with ZDR unavailable. A future model re-point can pull the project into mandatory retention with no code change. Model version is a privacy decision here, not only a cost one.

### Step 1: decide whether Ollama is a managed dependency. This gates everything local.

**This step did not exist in the original plan and it is the largest unpriced risk in it.**

`[VERIFIED]` Today Ollama is optional and unmanaged:

- `README.md:84` lists it as "only for screenshot vision"; setup §3 is titled "Screenshot vision, optional".
- `grep -rin "ollama" desktop/main/` returns **zero matches**. The Electron main process does not install, launch, health-check, or version-pin it.
- `ollama list` on the maintainer's own machine shows only `deepseek-r1:8b`. The configured `qwen2.5-vl:7b` is absent, so `check_ollama_health()` (`services/vision.py:29`, prefix-matches `"qwen2.5-vl"`) returns False here. **The one existing local path is unexercised on the machine it was built on.**
- `desktop/resources/bundle-manifest.json` reports `sizeBytes: 464375808`, shipped as a signed notarized DMG. Weights cannot go through that pipeline. `[VERIFIED]` An 8B Q4 model measures 5.2GB on this machine (`deepseek-r1:8b`), so Qwen3-8B is roughly a 5GB out-of-band pull and a co-resident VLM another ~6GB. **The user downloads ten to twenty times the app's own size through a tool the app does not manage.**

And the failure mode is silent. `[VERIFIED]` `ingest.py:265-279` catches every contextualize exception, substitutes the raw chunk, sets `context_status = "failed"`, logs a warning, and returns a success count. `indexing.py:122-131` does the same. **With Ollama down or the model unpulled, a user ingests their entire library un-blurbed, the UI reports success, and repair requires a full re-ingest and re-embed.** The proposed "local failures cost nothing, so add a retry" does not help against an absent daemon.

Given that fragility is the stated top cause of abandonment for tools in this category, promoting an unmanaged external daemon in front of the core ingest path is not acceptable as-is. **Required before Step 3:**

1. A preflight check that fails the ingest loudly rather than degrading it, when the local provider is selected and the daemon or model is missing.
2. A decision on whether the desktop app manages the Ollama lifecycle, or whether local inference stays an explicitly opt-in power-user path with the download cost stated up front.
3. First-run disclosure of the weight download size.

If the answer to (2) is "opt-in power-user path," that is a legitimate answer, but then the privacy claim in §1 must be scoped to users who opted in, and the README cannot claim it by default.

### Step 2: build the contextualize retrieval eval

`[VERIFIED]` The repo is well shaped for this. `services/rag.py:56` separates the citable `text` (`metadata.get("original_chunk") or doc`, written at `ingest.py:313` and `indexing.py:153`) from `embedded_text`. **Because of that separation, blurb quality can only affect recall**, so the acceptance criterion is unambiguous:

1. Take ~200 chunks from 5 real documents already in the corpus.
2. Generate blurbs twice: once through the current Haiku path, once through the candidate local model.
3. Embed both sets into two Chroma collections.
4. Run a fixed query set (30-50 questions with known ground-truth chunks) against each.
5. Compare recall@5 and MRR. Ship local when it is within noise of Haiku.

`segment_metadata` already records `context_status` per segment, so a per-segment A/B is possible in place.

**Three prerequisites the "one day" estimate omits:**

- `[VERIFIED]` An `ANTHROPIC_API_KEY`, to generate the Haiku baseline arm. This is the same thing `COST_MODEL.md` §6 records as having blocked Phase 4 from measuring anything.
- `[VERIFIED]` A running local model, which is what Step 3's seam exists to provide. Generating the candidate arm outside `complete()` means the eval does not exercise the shipped path, and blocker 4 below changes the message shape on the local branch specifically.
- `[VERIFIED]` No retrieval harness exists. `tests/test_retrieval_labels.py` is a prompt-assembly test over `_excerpt_block`, not recall or MRR. `services/chroma.py` binds a module-level `_client`/`_ef` and `get_collection()` always returns `CHROMA_COLLECTION`, so a two-collection harness must bypass it.

The human half, authoring 30 to 50 questions with known ground-truth chunks, is the real cost. Budget two to three days, not one.

**What quality this actually costs is unknown, and no amount of further reading will answer it.** `[UNVERIFIED]` No published benchmark measures off-the-shelf small local models against Haiku on the contextual-retrieval blurb task. `[SECONDARY]` The closest proxy puts the faithfulness knee at 3B (a Qwen2.5 sweep at 0.62 / 0.73 / 0.79 / 0.80 for 0.5B / 1.5B / 3B / 7B), so a 4B-to-8B base should land within a few points of the 7B ceiling. `[VERIFIED]` Anthropic's own contextual-retrieval reference implementation uses Claude 3 Haiku, a small model, for exactly this task, and specifies the blurb at 50-100 tokens. **The bar a local model must clear is lower than the current model choice suggests.** But it must be measured.

### Step 3: land the local provider seam. Ten blockers, not three.

| # | Blocker | Location | Fix |
|---|---|---|---|
| 1 | `ModelSpec` carries only `model` / `max_tokens` / `temperature`, no provider dimension | `llm.py:201-205` | Add a `provider` field |
| 2 | `complete()` hardcodes `ChatAnthropic` | `llm.py:555` | Branch on `spec.provider`. `ChatOllama` is a drop-in at the same `await llm.ainvoke(prompt.to_messages())` call shape |
| 3 | **Local calls land in `unpriced_calls`, and the obvious fix conflicts with a shipped convention** | `pricing.py:28-34` | See below. Do **not** simply return `(0.0, True)` |
| 4 | `to_messages()` returns list-of-block content carrying `cache_control` whenever `cache_prefix` is set, which is always on the contextualize path | `llm.py:160-176` | Flatten to a single string on the local branch. `cache_prefix + text` is byte-identical to the whole rendered prompt by construction in `_split_template`, so flattening is lossless |
| 5 | `test_single_client_construction_site` scans only for `"ChatAnthropic("` | `tests/test_budget_enforcement.py:194-202` | Extend to `ChatOllama(` |
| 6 | `asyncio.Semaphore(4)` + `gather` is correct for a hosted API and wrong by default for local | `ingest.py:259` | Make configurable, default 1 on the local path |
| 7 | **A second contextualize call site with its own `Semaphore(4)`** | `indexing.py:115` and `:124` | Apply blockers 2, 4 and 6 here too. This is the path all screenshots, snippets and chat captures flow through |
| 8 | **The chokepoint already has one documented exception** | `services/vision.py` | `llm.py`'s docstring claims it is "the single chokepoint every model call in this backend routes through." `vision.py` calls Ollama by raw `httpx` and writes its own ledger row. Test 5 cannot see it. The §6 taint-gate argument rests on this chokepoint, so either route vision through `complete()` or state the exception explicitly |
| 9 | `max_calls_for()` has no term for tool calls at all | `llm.py:255-272` | Blocks §6 |
| 10 | `Prompt.render`'s `_REGISTERED_TEMPLATES` allowlist cannot cover framework-assembled agent messages | `llm.py:86-89, 140-146` | Blocks §6 |

**Blocker 3 in full, because the obvious fix is wrong twice.**

`[VERIFIED]` `pricing._lookup` returns `None` for unknown models and `cost_usd` returns `(0.0, False)`, so every local call lands in `unpriced_calls`. The tempting fix is a zero-rate entry returning `(0.0, True)`. Do not do that:

- `[VERIFIED]` **It contradicts a convention already shipped.** `services/vision.py:100-101` records local Ollama calls with `cost_usd=0.0` and `priced=False`, docstring "They cost nothing," and `services/usage.py:225` increments `unpriced_calls` on `not row.get("priced", False)`. Local vision calls already land in that bucket today. The maintainer already chose the opposite convention, and adopting `(0.0, True)` for local text without changing `vision.py` puts two contradictory meanings of a local call in one ledger.
- `[VERIFIED]` **It creates a privacy-instrumentation hole.** `_lookup` is longest-*prefix* matching, so an entry keyed `"gemma4"` matches `"gemma4:31b-cloud"`. `config.py:54-56` takes both `OLLAMA_URL` and the model tag from env with **no locality validation**. `[SECONDARY]` Ollama ships `gemma4:cloud` and `gemma4:31b-cloud` in the same registry namespace as `gemma4:e4b`, and routes them through the identical local API. A whole-document contextualize call that egressed 24,000 chars x 76 chunks to Ollama's servers would be recorded `priced=True` at $0.00, asserting both "genuinely free" (false, Ollama cloud is a paid subscription) and implicitly "local." That inverts `COST_MODEL.md:168` verbatim: "A response with no usage block is unpriced, not free... any systematic loss of usage metadata would have reported the pipeline as free and read as an enormous saving."

**Recommended fix:** add an explicit `local: bool` to the ledger row rather than overloading `priced`, keep `priced=False` for local calls consistent with `vision.py`, and gate the local branch on a loopback `OLLAMA_URL` with an explicit rejection of any tag matching `-cloud` or `:cloud`.

**Blocker 6 in full, and honestly about its uncertainty.**

`[VERIFIED]` Four concurrent slots against a local runtime is close to worst-case, because each parallel slot holds its own KV cache partition, so the ~6,000-token document prefix gets prefilled once per slot instead of once per document.

`[UNVERIFIED]` Arithmetic on published llama.cpp base-M2 figures (180 tok/s prefill, 22 tok/s decode), for a 76-chunk document:

- **No prefix reuse:** 6,420 tok prefill + 60 tok decode = 38.4s/chunk. **76 chunks = 48 minutes.** Product-fatal.
- **Serial, warm prefix:** one 33s prefill, then 5.0s/chunk. **76 chunks ≈ 7 minutes.** Tolerable for background ingest.

**Two honest caveats on that 7-versus-48 figure, which is the strongest local-specific argument here:**

1. `[UNVERIFIED]` The prefix-residency behaviour it depends on is a **llama.cpp slot/KV-cache property**, while blocker 2 prescribes `ChatOllama`. Ollama's cross-request prompt-cache behaviour under concurrency is a different mechanism and is not established here. The 180/22 tok/s pair are also 7B-class numbers applied to a 4B-class recommendation.
2. `[VERIFIED]` **Nothing in this repo has ever timed a local model.** The only local model present is `deepseek-r1:8b`.

Since the entire tolerability of Step 4 turns on this ratio, **measure it before building the seam, not alongside it.** `[SECONDARY]` And add the fanless-Air caveat: sustained multi-minute GPU load throttles, with reported degradation of 15-30%, so the tail chunks run slower than the head.

One thing that is not in doubt: `[VERIFIED]` `CONTEXTUALIZER_PROMPT` is document-first and `cache_after="whole_document"` guarantees a byte-identical prefix across a document's chunks. **The `_split_template` machinery is not inert on the local path.** The Anthropic `cache_control` *declaration* becomes inert, but the byte-identical-prefix property it enforces is exactly what local prefix caching requires. Phase 4's caching work is a precondition for the local path, not wasted on it.

### Step 4: flip contextualize to local, behind a setting

`[SECONDARY]` Memory tiers, derived from the ~66% Metal wired limit at or below 36GB:

| RAM | GPU budget | Verdict |
|---|---|---|
| 16GB | ~10.6GB | 7B-class Q4 only, and `qwen2.5-vl:7b` may already consume it. Consolidate onto one multimodal model or stay hosted. |
| 24GB | ~15.8GB | Comfortable. 12B Q4 plus headroom. |
| 36GB+ | ~23.8GB | Everything below 32B Q4. |

`[SECONDARY]` Quantization floor: Q4_K_M or Q4_K_S. The llama.cpp quantization study reports Q4_K_S IFEval 80.26% and Q4_K_M 79.06% against an F16 baseline of 78.93%, with Q3_K_S dropping to 73.89%. **Two caveats that were previously overstated:** the study covers **one dense model, Llama-3.1-8B-Instruct**, and says nothing about MatFormer effective-parameter models (Gemma 4 E2B/E4B) or MoE architectures. And it measures GSM8K, HellaSwag, IFEval, MMLU, TruthfulQA and perplexity, with **no JSON emission and no tool calling**, so the common claim that "structured output and tool calling degrade before prose does" is not supported by it. Note also that Q4_K_S scoring *above* the FP16 baseline is a within-noise inversion, which is evidence the benchmark cannot resolve the difference rather than evidence Q4 is safe.

One free improvement this unlocks: `[VERIFIED]` `ingest.py` counts failed contextualisations and falls back to the raw chunk with no retry, because a retry costs money. Local failures cost nothing, so add the retry on the local path, on top of the Step 1 preflight (which handles the case a retry cannot).

### Step 5: the tool loop, on Claude, on the installed LangGraph. See §5 and §6.

### Step 6: leave alone, indefinitely

`classify`, `review`, `analyze`, `fast_fact`, `final_response`, and tool selection. Revisit only against §9.

---

## 5. Tool calling: the answer is no, on narrower evidence than first claimed

**`[VERIFIED]` No open-weight model that fits a consumer Mac is a safe substrate for a multi-turn agentic tool loop today. Keep the tool loop on Claude.**

The conclusion holds. Two pieces of the supporting evidence do not, and both were load-bearing in the original draft.

**Correction 1: the headline agentic citation contradicts itself.** `[UNVERIFIED]` TinyLLM (arXiv 2511.22138) was cited as showing Qwen3-4B at 82.58% single-turn non-live AST collapsing to 35.25% multi-turn. Its Table I and Table IV assign the same multi-turn values to **different models**, a full row shift (Table IV puts 35.25% on `xLAM-2-1b-fc-r` and 16.88% on Qwen3-4B), and Table III repeats the shift on non-live accuracy. **The figures cannot be quoted as verified.** Worse for the argument they were used to make, the paper evaluates nothing above 4B, so it contains no large-model control and **cannot support "the size cliff is on multi-turn, not single-turn" as a scaling claim at all.** Its abstract headline (55.62% multi-turn) belongs to a purpose-built function-calling model after hybrid optimization.

**Correction 2: the Ollama runtime defects mostly do not apply to the recommended path.** `[VERIFIED]` The cited streaming-drops-tool-calls defect (ollama#12557) is real, but it is in the **`/v1/chat/completions` OpenAI-compat shim**; the native `/api/chat` endpoint has supported streaming with tool calls since May 2025. The same is true of the missing `tool_choice`. And this document's own architecture does not use `/v1`: I confirmed in the installed venv that `langchain_ollama.chat_models` imports `AsyncClient` from the `ollama` package and that `ollama._client` posts to `/api/chat`. **The `/v1` bugs should not be counted in the evidence for the verdict**, and it was inconsistent to half-notice this for `tool_choice` while still counting the rest.

**What survives, and it is still sufficient:**

`[SECONDARY]` The size knee is real in BFCL v4, which does have large-model controls: the Qwen3.5 series drops from 0.661 at 9B to 0.503 at 4B, a 15.8-point fall against 6.8 points across the entire 397B-to-9B range. Vendors advertise single-turn numbers; Origami's plan is a loop.

`[SECONDARY]` Per-step reliability compounds geometrically. tau-bench pass^k decay puts GPT-4o under 50% at pass^1 and below 25% at pass^8. A local model at 70% per-step is roughly 17% reliable over a 5-step loop.

`[UNVERIFIED]` At Mac-runnable sizes, even purpose-built agentic post-training reaches only ~50-60% multi-turn task completion against ~90% for the frontier.

`[SECONDARY]` The model-template layer of Ollama, as distinct from the `/v1` shim, still has open defects that do apply: Qwen3 tool definitions rendered as Go struct strings rather than JSON (#14601, open since March 2026, unfixable in a Modelfile), and Qwen 3.5 27B routed through the wrong tool format with multi-turn history corrupted by unclosed `</think>` tags (#14493). `[VERIFIED]` mlx-lm, the natural Apple Silicon runtime, has **no tool parser** for non-Coder Qwen3.5/3.6 (#1293), Gemma 4 (#1096), or Kimi (#1262), and returns empty content rather than erroring.

`[SECONDARY]` Only llama.cpp with `--jinja` has credible evidence of clean multi-tool episodes, and adopting it means owning per-model template verification and template drift across GGUF re-uploads as ongoing maintenance. For a solo maintainer that is the wrong surface.

### The trap worth knowing about even while the loop is on Claude

`[VERIFIED]` **Never enable JSON-schema structured output and tool calling on the same generation pass.** The Constraint Tax paper (arXiv 2606.25605, Table 7) found tool invocation dropping from 100% to 0% on seven open-weight model instances while JSON compliance stayed at 100%, because the grammar mask makes tool-call tokens unreachable. A transparent two-pass split restores invocation to 100% and end-to-end success from 0% to 100%.

`[VERIFIED]` **Precision on scope, corrected:** the paper's mechanism is JSON Schema constraints compiled into grammar-based token masks in the serving stack (SGLang/vLLM guided decoding), and the one closed-source cloud model tested (GPT-5.4-mini) was unaffected. Origami's `final_response` uses prompt-instructed JSON with `_extract_json` recovery and **no grammar at all**, so this is not a present-tense property of the codebase. It becomes live the moment constrained decoding is adopted anywhere, which §2 previously proposed for `classify` and `review`. Record it as a design constraint, not a current bug.

`[VERIFIED]` A second silent-zero mode to guard against: a chat-template asymmetry between training and inference drove a fine-tuned Qwen3-8B to 0/6 tool calls at loss 0.16 with all training metrics healthy. **Any eval harness must assert a non-zero tool-invocation rate as a first-class check**, not just answer quality.

### Harness requirements, model-independent

`[SECONDARY]` Static analysis of 6,549 repositories found 68 confirmed infinite agentic loops across 47 projects, with LangGraph accounting for 33.8%; unbounded retry feedback 25.0%, unbounded tool-call iteration 23.5%, unbounded multi-agent chat 20.6%, and API cost exhaustion in 95.6% of findings. (A widely-circulated "62.9% infinite-loop rate for Llama-3.1-8B" attributed to this paper does not appear in it. That paper is static code analysis with no per-model measurement. Do not cite it.)

Origami is already better defended than most: `Budget.max_calls` raises at the chokepoint and `astream` carries an explicit `recursion_limit`. Extend both to cover tool calls rather than adding a parallel mechanism.

`[SECONDARY]` Three concrete additions: validate tool names against the registry before dispatch, cap iterations at 10-15 with a hard cost ceiling, and keep the exposed tool count under 10. `[SECONDARY]` Design for **sequential single tool calls, not parallel fan-out**: parallel calling is the first capability small models lose, and sequential-only also simplifies the taint gate, since each call's provenance is trackable without reconciling concurrent results. `[SECONDARY]` If the loop is ever pointed at a local model, present tool documentation as JSON, not XML or Python; BFCL v4 format-sensitivity testing across 39 models found a consistent JSON > Python > XML hierarchy with small models most vulnerable.

### Fallback if the tool loop must run locally

Split it. Keep tool *selection* on Claude and run only tool *execution* locally, which is where the taint gate already lives. That preserves the one capability open models are worst at while keeping untrusted content off the network. A fully local tool loop is not a shippable default at any size that fits a consumer Mac.

---

## 6. Framework: build on the installed LangGraph

**`[VERIFIED]` Recommendation: build on `langchain` 1.2.10 / `langgraph` 1.0.9, already installed. Zero new dependencies.**

Confirmed in `backend/.venv` this session: `from langchain.agents import create_agent` and `from langgraph.prebuilt import ToolNode` both import; `AgentMiddleware` exposes `wrap_tool_call` and `awrap_tool_call`; `langchain-ollama` 1.0.1 and `langchain-anthropic` 1.3.4 are installed, and `ChatOllama.bind_tools` exists.

**The decisive argument is the security gate.** `wrap_tool_call(self, request, handler) -> ToolMessage | Command` receives the tool call plus `request.state` and decides whether to invoke `handler`, so it can refuse a call and return a synthetic `ToolMessage` in its place. Middleware compose outermost-first. That is exactly the taint gate's shape: a state field marks the turn tainted once untrusted document content enters, and an outermost middleware denies egress-capable tools while the flag is set. Every alternative means hand-rolling that interception point, **and a hand-rolled security boundary maintained by one person is the worst line item in the plan.**

Usefully, the gate does not need `tool_choice`. Denying egress is achieved by not binding the tool and by refusing in `wrap_tool_call`, both host-side.

`[VERIFIED]` The rest of the field disqualifies itself on Origami's constraints, not on quality:

| Framework | Status | Why not |
|---|---|---|
| **Pydantic AI** | MIT, 2.21.0 | Best typed tool ergonomics, worst churn profile. 1.0 to 2.0 in under a year against LangGraph 1.0's public no-breaking-changes-until-2.0 commitment. |
| **smolagents** | MIT, 1.26.0 | `CodeAgent` executes generated Python. Inverts the threat model the gate exists to enforce. A tool allowlist is enforceable; a Python interpreter is not. |
| **Letta** | Apache-2.0, 0.16.8 | Requires PostgreSQL + pgvector. Violates the no-servers constraint outright. |
| **OpenAI Agents SDK** | MIT, 0.19.1 (pre-1.0) | Vendor-neutral path is the beta path; telemetry defaults to a hosted dashboard. Direct conflict with the positioning. |
| **Hermes Agent** | MIT | An end-user runtime with its own CLI and memory system, not an embeddable library. |
| **DSPy** | MIT, 3.2.1 | Wrong layer (an optimizer, not a runtime). Relevant to §7 as an alternative to fine-tuning. |

### Two collisions with existing invariants

**`[VERIFIED]` Collision 1: `max_calls_for()` has no tool-call term, so the first tool loop dies with `CallBudgetExceeded`.** The formula at `llm.py:272` is `1 + max_loops + max(0, max_loops - 1) + 1`, yielding exactly 3 for `normal_rag` and 7 for `deep_research`, both pinned by `tests/test_loop_bounds.py`. Any tool call is a model call beyond that ceiling. Hard blocker, must be resolved before the first tool lands.

Resolution: **keep `Budget` authoritative** (it derives `may_send_context` from origin and is pinned by `test_budget_enforcement.py`), extend `max_calls_for` with an explicit tool-call term, and do **not** enable LangChain's `ToolCallLimitMiddleware` / `ModelCallLimitMiddleware` as a second source of truth.

**`[VERIFIED]` Collision 2: `create_agent` bypasses `Prompt.render` entirely.** `_REGISTERED_TEMPLATES` restricts renderable templates to module-level constants in `prompts/`, and `carries_session_state` is derived from which placeholders were filled. A framework-assembled message list goes through neither, so Lever 2's gate does not cover the tool loop's internal turns.

This is not a reason to reject `create_agent`. The two gates sit on different axes and are complementary:

- **Lever 2 governs what a prompt may carry** (may background work send session state?), derived from placeholders.
- **The taint gate governs what a turn may do after reading untrusted content** (may a turn that ingested a document still reach the network?), derived from state.

Recommended shape: use `create_agent` with middleware for `wrap_tool_call`, and route the model invocation through `complete()` via `wrap_model_call` so `Budget.authorize`, the usage ledger, and the single-construction-site test all still hold. Then extend `Prompt` with a variant for framework-assembled message lists whose `carries_session_state` derives from the state taint flag rather than from placeholders. **If that looks like too much surface, the fallback is an explicit LangGraph `ToolNode` with `complete()` as the invocation point**. More code, but it preserves every existing invariant without modification.

---

## 7. Third-party open-model hosting: a positioning regression

**Flagged option: routing any call site to Groq, DeepInfra, Together, Fireworks, Cerebras, Novita, Hyperbolic, or OpenRouter. This is labelled a positioning regression, not a neutral tradeoff.**

**`[VERIFIED]` The cheapest call site to move is also the most sensitive payload, and the correlation is inverted from the intuition.** `contextualize` sends `document_prefix(whole_document)` truncated to 24,000 chars, once per chunk. A single 43-page paper means **76 copies of the user's document** shipped to that provider. `analyze` sends only 5 retrieved chunks; `classify` and `review` send almost nothing. **A router that moves only the cheap call sites is precisely a router that moves the most sensitive one.**

Three reasons this does not become attractive on closer inspection.

**1. The policies are genuinely fine, and it still does not help.** `[VERIFIED]` Fireworks is zero-retention by default on open models ("We do not log or store prompt or generation data for any open models without explicit user opt-in"). Cerebras states it retains nothing. Novita's ToS §9 contains an unusually strong non-retention clause. Groq's Services Agreement has a clean no-training clause and self-serve ZDR, though the precise wording is "**Eligible Customers** may enable Groq's zero data retention setting," not all customers, and the dedicated ZDR doc page 404s. Together's ZDR is plain opt-in with retention by default; it is not, as previously described, self-contradictory. OpenRouter's free-tier training exposure is a **settable default**, not an inherent property.

`[VERIFIED]` Anthropic's own default posture is equivalent: commercial API inputs and outputs are not retained by default and retained data is never used for training without permission. Its self-serve ZDR is *worse* than Groq's (it requires contacting sales), but the default is the same.

**So the privacy argument for staying on Anthropic was never about policy text.** It is about single-vendor surface area, and about a solo maintainer being able to defend one vendor relationship more credibly than six.

**2. The economics mostly evaporate against the cached baseline.** `[SECONDARY]` `gpt-oss-120b` on DeepInfra is ~5.9x cheaper than *already-cached* Haiku, not the 27x the headline rates imply. Groq is ~2.6x. Cerebras at $0.35/$0.75 is **more expensive** than cached Haiku for this workload. And `[SECONDARY]` most open providers publish no cache-read discount at all: of 19 `gpt-oss-120b` endpoints, only Groq (0.5x), Parasail (0.55x) and DigitalOcean (0.29x) discount cache reads, and **none support implicit caching.** Anthropic's 0.1x cache read is a first-class feature Origami's ingest path is already built around; most open providers mean paying full rate on 76 near-identical prefixes per document. **This entire argument is contingent on Step 0b: if the cache does not actually engage, it collapses.**

**3. Free tiers cannot ship.** `[VERIFIED]` Groq's `gpt-oss` free tier is 200K tokens/day. One 43-page document's contextualize input is roughly 490K tokens. **The free tier cannot ingest a single medium document per day.**

`[SECONDARY]` Reliability compounds the case: measured 24-hour uptime on `gpt-oss-120b` endpoints ranges from Groq at 99.98% down to SiliconFlow at 65.87%. A provider outage partway through a 445-chunk book ingest is a bad experience Origami would own.

`[VERIFIED]` One architectural note if this is ever revisited: a third-party provider adds a second network egress path the taint gate must cover. Today an egress policy is a single-destination allowlist; a multi-provider router turns it into a per-call, taint-aware routing decision. **If a provider abstraction is ever built, build it before the tool loop lands.**

**Recommendation: do not route any call site through a third-party open-model host.** Not on the grounds that their policies are bad, because mostly they are not, but on the grounds that (a) the only call site worth moving is the one carrying whole documents, (b) six vendor relationships is more surface than one maintainer can defend, and (c) if a call site is worth moving off Anthropic, it is worth moving all the way to the user's machine. Stated as a design rule rather than a prohibition: **anything that leaves Anthropic goes local, not sideways.**

### The privacy fact that most strengthens the local move

`[VERIFIED]` Anthropic's retention documentation includes a carve-out that survives ZDR entirely: "Even with ZDR or HIPAA arrangements in place, Anthropic may retain data where required by law or where it has been flagged by Anthropic's automated trust and safety systems. As a result, if a chat or session is flagged, Anthropic may retain inputs and outputs for up to 2 years."

For a personal knowledge base holding arbitrary private documents, **a medical, legal, or journal document that trips an automated classifier can be held for two years, and no retention arrangement prevents it.** This applies to every hosted provider with a trust-and-safety pipeline, which is all of them. It is the single strongest published argument for moving whole-document egress off the network, and it is independent of cost entirely.

### What remains hosted after the full migration

`[VERIFIED]` **"The corpus never leaves the machine" is still false after Step 4, and the residual should be stated plainly rather than rounded off.** `agent.py:269` ships joined `retrieved_excerpts` to `analyze`. `agent.py:276` and `:556` ship `state["current_note"][:2000]`, the user's active Markdown note, to `analyze` and `final_response`. `agent.py:809/830` passes `current_note` into `classify`. The accurate claim after migration is "whole documents never leave the machine; retrieved passages and your active note still do on routed turns."

---

## 8. Corrections to earlier analysis

Recorded rather than silently fixed, because several of these would otherwise propagate.

1. `[VERIFIED]` **"71% of the monthly bill" is an artifact of an untested assumption.** Full treatment in §3. The share is 70.5% only at 200 documents ingested per month forever; it is 19.3% at 20 docs/month, 5.6% at 5, and 0% in steady state. This changed the recommendation's justification from cost to privacy.
2. `[VERIFIED]` **Nothing has been measured.** One stub ledger row, `cache_read_tokens` never non-zero. The "repo-measured" 76-chunk figure was measured in characters, not billed tokens. Step 0b now precedes everything.
3. `[UNVERIFIED]` **The TinyLLM citation self-contradicts across its own tables** and contains no model above 4B, so it cannot support a scaling claim. Downgraded from `[VERIFIED]`; the tool-loop conclusion now rests on BFCL v4 and tau-bench.
4. `[VERIFIED]` **The Structured Output Benchmark figure does not discriminate between the options.** "17-31% of leaf values wrong at >97% schema compliance" is real (best Value Accuracy 83.0% on text across 21 frontier and open-weight models), but 83.0% **is the frontier ceiling**, so the band describes Claude as well as a local model. Removed as support for keeping `final_response` on Claude. That decision now rests on long-context multi-turn synthesis and the attribution rule.
5. `[VERIFIED]` **Ollama's `/v1` defects do not apply to the recommended `ChatOllama` path.** Full treatment in §5.
6. `[VERIFIED]` **HHEM is the wrong metric for a recall@5 gate.** Full treatment in §2.
7. `[VERIFIED]` **`mistral-3-large 14.5%` is not on the Vectara leaderboard.** Removed. The GLM range is GLM-4.5-AIR-FP8 9.3%, GLM-4.6 9.5%, glm-5 10.1%, not "9.3% to 11.7%."
8. `[VERIFIED]` **A second contextualize call site exists** at `indexing.py:124` with its own `Semaphore(4)` at `:115`. Now blocker 7. It also gates on `_should_contextualize` (draft_count > 1, non-empty whole_text, text modality, length >= `CONTEXTUALIZE_MIN_CHARS = 600`), which the cost model does not account for.
9. `[VERIFIED]` **The `(0.0, True)` pricing fix was wrong twice**. It contradicts `vision.py`'s shipped `priced=False` convention, and longest-prefix matching plus an unvalidated `OLLAMA_URL` would let Ollama *cloud* inference report as verified-free local inference. Full treatment in §4 Step 3.
10. `[VERIFIED]` **`llm.py` is not the single chokepoint its docstring claims.** `vision.py` calls Ollama by raw `httpx` and writes its own ledger row, invisible to `test_single_client_construction_site`. Now blocker 8, and material because §6's taint-gate argument rests on that chokepoint.
11. `[VERIFIED]` **Ollama is optional, unmanaged, and unexercised on the maintainer's own machine.** Now Step 1, ahead of the eval.
12. `[VERIFIED]` **The Reor anecdote was doing too much work.** `reorproject/reor` was archived 2026-03-07 and the quoted complaint is a real Hacker News comment, but it is **one comment from February 2024**, from a user testing an open Hermes model on a small knowledge base, and the same comment calls Q&A mode "surprisingly helpful" for overviews and expects improvement with better model selection. A single anecdote two years before archival is not evidence of cause of death. Removed as the load-bearing risk argument.
13. `[VERIFIED]` **The Semaphore(4) costs four cache writes per document**, a 19.3% ingest overhead on the hosted path. New finding, §3.
14. `[VERIFIED]` **The 500-document library figure was understated.** $43.50 as shipped, not $29.73, which omitted cache writes entirely.
15. `[VERIFIED]` **`review` is `max_tokens=256`, not ~1024**; `fast_fact` is 1024, `contextualize` is 100.
16. `[VERIFIED]` **`final_response` is not unconditionally Sonnet.** `resolve_model` (`llm.py:250`) already splits three ways: Haiku when `has_notes` is false, a Sonnet floor on `deep_research` with notes, and Sonnet on `normal_rag` with notes unless `ORIGAMI_CHEAP_FINAL` is set.
17. `[VERIFIED]` **The quantization study is one dense Llama-3.1-8B** and measures no JSON emission or tool calling. §4 Step 4 now says so.
18. `[VERIFIED]` **`langchain-ollama` 1.0.1 is already a declared dependency** and populates `usage_metadata` from `prompt_eval_count` / `eval_count`, so `_to_result`'s "no usage metadata" error path will not fire spuriously. It also sets `response_metadata["model_name"]`, which is what routes local calls into the unpriced bucket in correction 9.

### On licensing, which survived review intact

`[VERIFIED]` One caveat to add. "Origami pulls weights through Ollama rather than bundling them, so even the Apache NOTICE obligation does not attach" is correct twice over: no distribution occurs, and the Gemma 4 repos ship no NOTICE file at all. But the README roadmap commits to a signed macOS desktop application, and **the moment weights are bundled for one-click install, Apache 2.0 §4(a) (include a copy of the License) and §4(b) (state changes) attach regardless of NOTICE.** `Qwen/Qwen3-8B` and `openai/gpt-oss-120b` do ship LICENSE files. The obligation returns as soon as the product does what the roadmap says it will.

`[VERIFIED]` A copy-discipline note: Apache 2.0 weights are **not** "open source AI" under OSI's definition, which additionally requires data information and complete training code. Nothing in this document claims otherwise, and `frontend/out/404.html` already carries "Open source knowledge base" which is true of the MIT code. Keep the distinction: **"open weights" for models, "open source" for the app.**

`[SECONDARY]` Gemma 4 12B's modality list is narrower than stated: the launch material describes text, image and audio inputs for the 12B, with video described for the 26B-A4B and 31B. If the vision-consolidation plan depends on video, verify first.

---

## 9. Distillation for contextualize: not worth it

**`[VERIFIED]` Do not build a distillation pipeline. Localize contextualize with an off-the-shelf model.**

**The cost case does not exist.** `[VERIFIED]` At $1.32 per 1,000 cached chunks, a 500-document library is a one-time $43.50. A 20-hour pipeline at a nominal $50/hour must amortize over ~758,000 chunks, roughly 17,000 documents. Note the framing correction: the maintainer's build cost amortizes across **all** users, not per user, so the break-even is a fleet-wide figure rather than a per-user one. The conclusion survives regardless, because **the recommended alternative is free**: off-the-shelf weights through a dependency the project already declares.

`[SECONDARY]` **The tooling is worse than assumed.** Unsloth does not run on macOS; its own docs require Windows or Linux and direct Mac users to Colab. torchtune was wound down in 2025 and receives only critical fixes. That leaves MLX-LM locally or a rented Linux GPU, and MLX-LM's own docs demonstrate Mistral 7B on a 32GB Mac only at batch-size 1 with tuned layers cut from 16 to 4, which are exactly the degraded settings that weaken the resulting adapter.

**There is legal exposure that should be a deliberate decision.** `[VERIFIED]` Anthropic Commercial Terms D.4 prohibits accessing the Services "to build a competing product or service, including to train competing AI models." Harvesting Haiku contextualize outputs to train a local replacement for an internal step of a PKB is defensible. **Publishing the resulting LoRA adapter under MIT alongside an MIT app is a materially higher-exposure act** for a maintainer with no legal budget.

**If the §4 Step 2 eval fails**, escalate in this order and stop at the first success:

1. A larger off-the-shelf model (Gemma 4 12B, Qwen3-8B). Free.
2. Prompt optimization against a retrieval metric (DSPy GEPA/MIPROv2). One dev-only dependency, no weights, no legal exposure.
3. LoRA on a 3-4B base, 500-2,000 pairs, 1-3 epochs, $3-$10 of rented GPU. Only if 1 and 2 both fail, and keep the adapter unpublished.

---

## 10. What would change this decision

| Decision | Concrete trigger to re-evaluate |
|---|---|
| **Step 0b cache measurement** | If `cache_read_tokens` comes back zero on a real ingest, the ingest baseline is the uncached column ($151.20 for a 500-doc library, not $43.50), §7's economic dismissal of third-party hosting collapses, and the priority order in §4 changes. **This is the highest-information cheapest check in the document.** |
| **contextualize** | Ship local when recall@5 and MRR are within noise of the Haiku arm on a 30-50 question set, **and** Step 1's Ollama dependency question has an answer. Reverse if measured 76-chunk local ingest exceeds ~10 minutes on a 16GB Air. |
| **contextualize concurrency** | Independent of any migration: if the Step 0b ledger row shows four cache writes per document, serialize the first chunk. Worth 19.3% of the ingest bill on the hosted path. |
| **classify** | User is on 24GB+, a ≤2B model stays resident alongside the VLM, and **measured** p50 latency beats the current Haiku call. Prefill on a ~700-token prompt is the binding term, not throughput. |
| **review** | The Step 2 harness extended to measure whether a locally-refined query retrieves the same ground-truth chunks as Haiku's, over ≥30 `deep_research` turns. |
| **analyze** | An eval that specifically tests the "WRITTEN BY A MODEL" attribution rule, plus a long-context multi-turn measurement. Not a general benchmark delta. |
| **fast_fact** | A local model whose knowledge cutoff is within ~6 months, at a size that leaves the VLM resident, with measured p50 under the current Haiku latency. |
| **final_response** | A local model clearing a LongMemEval-style faithfulness eval on this exact JSON-plus-LaTeX-plus-action contract, with a `json_strategy` distribution no worse than the recorded Sonnet baseline. The instrumentation already exists and is reported by `GET /api/usage`. Note this is a higher bar than `ORIGAMI_CHEAP_FINAL`, which only asks whether Haiku matches Sonnet. |
| **tool loop** | Multi-turn (not single-turn) reliability above ~90% pass^1 at a size that fits 16GB, **plus** a runtime whose tool parser is correct for the chosen model. Recheck when mlx-lm #1293 and #1096 close, when ollama #14601 and #14493 close, and when Vectara scores Qwen3.6 / Granite 4.1 / OLMo 3. |
| **Sonnet 5** | Revisit after 2026-08-31 when the post-introductory rate is published, and only alongside a `pricing.py` entry and a check on whether it is a Covered Model with mandatory retention. |
| **third-party hosting** | Only if the design rule in §7 is consciously overturned. The trigger would be a provider offering both contractual ZDR *and* implicit prefix caching at a rate that beats cached Haiku, which no provider currently does. Even then the answer is probably still local. |
| **distillation** | Only if §9's escalation ladder reaches step 3, and then unpublished. |

---

## 11. Bottom line

**Origami cannot stop depending on frontier Anthropic models, and the honest version of that is more useful than a migration plan that pretends otherwise.** OpenAI is already gone. Of six Anthropic call sites, one can move today.

Do these, in order:

1. **Fix the README headline** so the product does not claim something the code contradicts, and disclose that the active note is sent.
2. **Spend $0.13 measuring the cache.** Every figure in this document, including the ones I recomputed, is modeled. This one number decides which document is right.
3. **Decide whether Ollama is a managed dependency**, because promoting an unmanaged external daemon in front of the core ingest path, on a machine where the existing local path has never run, is a larger risk than anything the migration saves.
4. **Build the retrieval-recall eval**, budget two to three days rather than one.
5. **Land the ten-point local seam**, including the second call site in `indexing.py` and the `local: bool` ledger field.
6. **Flip contextualize to local.**

That eliminates 100% of the whole-document egress and 100% of the two-year trust-and-safety retention exposure for the corpus, at the cost of one bounded risk (retrieval recall) that `rag.py` already prevents from becoming a false citation. It saves a one-time $25 to $45 and **$0.00 per month**.

Then build the tool loop on the LangGraph already installed, put the taint gate in `wrap_tool_call`, extend `max_calls_for` before the first tool lands, and keep Claude on `classify`, `review`, `analyze`, `fast_fact`, `final_response`, and tool selection.

**Do it for the egress. The money was never there.**
