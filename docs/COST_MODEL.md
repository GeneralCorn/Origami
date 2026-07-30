# Cost Model

**Date:** 2026-07-26
**Status:** Research complete, no code written

"Like OpenClaw and Hermes, but not so costly" is a stated product goal. This document establishes where the money actually goes, because the intuitive answer is wrong and optimising against it would waste the entire effort.

---

## 1. The headline finding: embeddings are not the cost

The instinct when building a retrieval product is that embedding a large personal corpus is the expensive part. It is not. It is close to free.

`[VERIFIED]` Current published pricing puts OpenAI `text-embedding-3-small` at **$0.02 per million tokens**, or $0.01 per million through the Batch API. `text-embedding-3-large` is $0.13 per million standard.

`[SECONDARY]` Self-hosted embedding on rented GPU lands near **$0.001 per million tokens**. Embedding locally on the user's own machine has no marginal cost at all.

`[SECONDARY]` At a scale of 100 million tokens per month, which is far beyond a realistic personal corpus, the most expensive mainstream option totals about **$18 per month**.

For calibration: a heavy personal knowledge base of 50,000 documents averaging 2,000 tokens each is 100 million tokens **in total**, not per month. Embedding that entire corpus once with `text-embedding-3-small` costs about **$2**. Re-embedding the whole thing after a model change costs $2 again.

`[SECONDARY]` Quality no longer argues for the paid option either. As of April 2026, BGE-Large, GTE-Large, Stella, and Nomic all match or exceed `text-embedding-3-large` on standard MTEB metrics within margin of error for English.

**Conclusion:** embedding choice is a decision about bundle size, latency, and privacy. It is not a cost decision. Any plan that frames the local embedding model as a cost-saving measure is optimising a rounding error.

---

## 2. Where the money actually goes: fixed per-request agent overhead

`[SECONDARY]` The dominant complaint against Hermes Agent is that **73% of every API call is fixed overhead**, with tool definitions alone consuming close to half of each request.

`[SECONDARY]` Measured overhead by interface: roughly **6,000 to 8,000 input tokens per request** through a CLI, rising to **15,000 to 20,000 per request** through messaging gateways such as Telegram or Discord, which is two to three times higher because of gateway-specific context.

`[SECONDARY]` The pathological case is instructive. A "heartbeat" check designed to poll every 30 minutes for pending tasks sent the **entire 120,000-token context window** on each firing. That is roughly **$0.75 per request, about $18.75 overnight, and on the order of $250 per week** for a feature that usually has nothing to report.

`[SECONDARY]` Reported real-world spend for OpenClaw and Hermes runs **$10 to $30 per month** for light use on budget models, and **$100 or more** for heavy use on frontier models. One user reported burning 4 million tokens in two hours of light usage, and 21,000 tokens to answer a question about the weather.

The shape of this is unambiguous. The cost is **not** in the tokens the user meaningfully sends. It is in what the system sends on the user's behalf, every single turn, whether or not it is needed.

---

## 3. The four levers, in order of impact

### Lever 1: Prune tool definitions per turn

Tool definitions are re-sent in full on every request and account for roughly half of fixed overhead. Most turns need a small subset.

Route the user's turn through a cheap classifier and attach only the relevant tool group. Origami already has the machinery: `classify_query()` in `backend/services/agent.py` exists and already runs. It is currently used only to choose a conversational or research path. Extending it to select a tool group is close to free.

Expected saving: on the order of 30 to 40% of input tokens per turn.

**Status after Phase 4: BLOCKED, and the premise does not hold for Origami.** Tool definitions are 0% of this backend's per-request overhead, because zero tool definitions are sent. `bind_tools`, `ToolNode`, `@tool`, `create_react_agent`, `StructuredTool`, and `tool_choice` have no occurrences anywhere in the backend, there is no MCP client, and every model call passes a plain rendered string to `ainvoke`. The graph is a fixed five-node pipeline with one conditional edge that chooses only between looping and finishing. The classifier half of the claim is true; there is simply no tool set for it to select from. Unblocked by Phase 5 connectors or an MCP client introducing something that ships a tool schema on the wire. Building a selector for an empty set would produce untestable code and a design that Phase 5's real tool shapes would immediately invalidate.

### Lever 2: Never poll with full context

The $250-per-week heartbeat is entirely self-inflicted. Any background or scheduled work must run against a summary and a cheap model, and escalate to full context only when the summary indicates there is something to do.

Rule to encode: **no scheduled task may send the conversation context window.** If a background job needs context, it earns it by first passing a cheap check.

Expected saving: eliminates the single largest failure mode outright.

**Status after Phase 4: enforced, though it is a guardrail rather than a saving today.** No timer, interval, or scheduled job in this repo reaches a model call, so the rule was satisfied by accident. It is now structural: `complete()` requires a `Budget`, only `Budget.interactive()` grants permission to send session state, and `Prompt.carries_session_state` is derived from which placeholders were filled rather than declared by the caller. Tests in `backend/tests/test_budget_enforcement.py` fail if a background caller gains context, if a second file mints an interactive budget, if any file hand-builds a `Budget`, if a second file constructs `ChatAnthropic`, or if a new prompt placeholder goes unclassified.

Four ways the first version of this gate could be walked around, all now closed, because a gate whose bypasses are this easy is documentation with a raise in it:

- **Pre-interpolation.** Deriving `carries_session_state` from filled placeholders only binds a caller who *uses* placeholders. A prompt built as an f-string that pasted the conversation into the template carried no fields, derived `False`, and a background permit sent the whole conversation. `Prompt.render` now requires `template` to be one of the constants exported by `prompts/`, matched by value, so a string assembled at runtime cannot be rendered at all.
- **Capitalisation.** The placeholder pattern was `[a-z][a-z0-9_]*`, so `{History}` matched nothing: it tripped neither the unclassified-field check nor the session-state derivation. The pattern is now case-insensitive, and the test that scans `prompts/` uses the same pattern so the two cannot drift.
- **A settable permit.** `may_send_context` was a field on a mutable dataclass, mutable by necessity since `authorize` and `adopt_route` write to it, so `b = Budget.background(...); b.may_send_context = True` promoted a background permit in one line. It is now a read-only property derived from `origin`, and `Budget.background` refuses to claim the interactive origin.
- **An allowlist that looked in the wrong place.** The scan for `Budget.interactive(` covered `services/` and `routes/` only, missing `main.py`, where a job hung off the existing FastAPI lifespan hook would live and which is the single most likely home for the scheduled task this rule exists to stop. It now scans every backend module outside `tests/` and `.venv/`, and separately fails on any direct `Budget(` construction.

One thing that is deliberately *not* closed: a background job may still send arbitrary bytes as `whole_document` or `chunk_content`. That is the line the rule draws, stated in `CONTEXT_FREE_FIELDS`: background work may process the payload it was handed, and may not reach into the live conversation. Ingest depends on it.

A contextvar was considered and rejected: Starlette awaits `BackgroundTasks` inside the same request coroutine, so ingest would inherit "interactive", and the chat endpoint's `StreamingResponse` generator runs after the handler returns, so resetting a token in a `finally` would clear the flag before any node called a model.

### Lever 3: Route by difficulty, not by default

Most turns in a personal knowledge tool are retrieval and summarisation, which small models handle well. Frontier models should be reserved for synthesis across many sources and for multi-step reasoning.

Origami is already positioned for this. The stack carries `langchain-ollama`, so a local path exists.

Expected saving: large but highly workload-dependent, plausibly 50 to 80% of generative spend.

**Correction:** `backend/services/ollama.py` was not deleted in an uncommitted working tree. The deletion is committed, in `df2993e`. `OLLAMA_MODEL` in `config.py` is imported by nothing and `langchain-ollama` is dead weight in `pyproject.toml`. Restoring a local text tier is a separate deliberate decision and is explicitly out of scope for Phase 4; the `resolve_model()` seam introduced in `backend/services/llm.py` is what reduces it to a one-function change later.

**Status after Phase 4: partially taken, and the headline figure is NOT claimed.** Everything except the final synthesis is locked to Haiku, `analyze` most deliberately: it is the most repeated call and carries the largest input block, so escalating it would multiply the biggest input term to improve the one call it feeds. The final synthesis never sees retrieved chunks, only distilled notes, so it splits three ways. With no notes it drops to Haiku by default, since there are provably no sources to synthesize and that case fires constantly on an empty or new knowledge base. `deep_research` with notes is a hard Sonnet floor. `normal_rag` with notes, which is the modal turn and where the 50 to 80% would come from, stays on Sonnet behind `ORIGAMI_CHEAP_FINAL`, because that node must emit one valid JSON object containing LaTeX and there is no way to A/B the result without a key. The recorded `json_strategy` distribution is the gate for flipping it on evidence.

### Lever 4: Cap the agent loop by difficulty

`backend/services/agent.py` runs a research loop bounded by `MAX_RESEARCH_LOOPS`. The current working tree already reads `state.get("max_loops", MAX_RESEARCH_LOOPS)`, making it per-request configurable, which is the right shape. What is missing is a policy that actually sets it lower for easy queries.

Every additional loop iteration re-sends the accumulated context. Iteration cost grows superlinearly with loop count.

Expected saving: proportional to how often easy queries currently run the full loop.

**Correction:** the per-route policy is not missing. It landed in `df2993e` and is enforced in `review_node`.

**Status after Phase 4: the policy is now tunable and structurally bounded.** The table lives in `config.LOOPS_BY_ROUTE`, overridable through `ORIGAMI_LOOPS_BY_ROUTE`, and clamped to `1..5` for the graph routes and `0..0` for `fast_fact`. The exact per-route model-call counts are pinned by `backend/tests/test_loop_bounds.py`:

| route | max_loops | analyze | review | final | classify | total calls |
|---|---|---|---|---|---|---|
| `fast_fact` | 0 | 0 | 0 | 0 | ≤1 | **2** |
| `normal_rag` | 1 | 1 | 0 | 1 | ≤1 | **3** |
| `deep_research` | 3 | 3 | 2 | 1 | ≤1 | **7** |

`review_node` increments before comparing, so `max_loops=N` yields N analyze passes and N-1 review calls. That is correct rather than an off-by-one: the last pass has no continue-decision to make, so paying a Haiku call to ask whether to loop again when no budget remains would be pure waste. `normal_rag` therefore never calls review, and the test asserts that absence so it reads as intentional.

Two structural backstops now sit under the single enforcement point in `review_node`: `Budget.max_calls`, which raises at the chokepoint, and an explicit `recursion_limit` of `4 * max_loops + 2` on `astream`. Verified by replacing `review_node`'s body so it never completes: the graph stops at 14 supersteps on `deep_research` instead of running to LangGraph's default 25.

Why the lower bound is 1 and not 0. `max_loops` is read in exactly one place, `review_node`, which runs *after* `retrieve -> analyze`. A graph route therefore makes two calls (classify and final_response) before the knob is consulted at all, so `max_loops=0` does not buy a cheaper turn: it sets a ceiling below the calls already made and drops `recursion_limit` below one pass. `ORIGAMI_LOOPS_BY_ROUTE=normal_rag=0` used to be accepted, because the clamp's lower bound was 0 for every route and any negative typo produced it, and every `normal_rag` turn then died with `CallBudgetExceeded` at `analyze`, returning the canned "hit its model-call limit" string forever. Two floors now hold that shut: the clamp refuses sub-1 values for the graph routes and logs the correction, and `max_calls_for` floors its review term so the formula can never return less than `classify + final_response`. `fast_fact` keeps 0 because it bypasses the graph entirely. Pinned by `test_env_override_floors_the_graph_routes_at_one_pass` and `test_a_zeroed_override_still_answers`.

Separately, `classify_query`'s `len(q) < 12` heuristic sent every short question ("why NaN?", "fix eq 3?") down the no-retrieval path, so the user's own documents were never consulted. That inflated the apparent `fast_fact` share, which is the numerator of every saving claim. It is removed.

---

## 4. Where Origami already spends, today

Three existing behaviours are worth naming because they are live cost centres, documented in the repository's own concerns analysis.

**Per-chunk contextualisation at ingest.** `backend/services/ingest.py` calls Haiku once per chunk to contextualise it before embedding, with a concurrency semaphore of 4. This is a genuine quality win and it is also the largest per-document cost in the system. Unlike embedding, this one is real money, because it is a generative call per chunk. It also fails silently and falls back to the raw chunk with no retry, so some spend currently buys nothing.

*Addressed in Phase 4, and it turned out to be the largest measurable win available.* The document prefix prepended to every chunk request is byte-identical across a document's chunks. Measured on a real 43-page paper: 76 chunk requests, one distinct prefix, and the repeated prefix is 93.8% of total request characters. It is now sent as a `cache_control: ephemeral` block. `CONTEXTUALIZER_PROMPT` was already document-first, so no prompt text changed and the bytes the model sees are identical, making this a zero-quality-risk change. One correction to note for anyone re-deriving this: Anthropic's minimum cacheable prefix for Haiku 4.5 is **4,096 tokens**, and the old hardcoded 12,000-char truncation was near 3,000 tokens, below the floor — where the cache silently never engages and no error is returned. `CONTEXT_DOC_CHARS` is therefore 24,000, which is ~6,000 tokens. The old 12,000 figure was justified by a comment about 7B models with 4-8k context, a constraint that left with the local text path. Failed contextualisations are now counted per document, so the spend that buys nothing is at least visible. No retry was added.

**Classifier on every research query.** `classify_query()` calls Haiku unless weak heuristics match, adding 1 to 2 seconds and a call to most queries. Cheap per call, but it is on the hot path for every single interaction.

*Worse than described.* Its usage was never extracted at all, so every token total the UI reported understated by one Haiku call on every single turn. The classifier now runs through the same chokepoint, its tokens land on the turn's `turn_id`, and `classify_query` returns its `ModelResult` so the caller folds it into the turn's running totals. It remains Haiku at `max_tokens=10`; the real lever there is the free heuristics, not the model.

That fix originally landed only half way, which is worth recording because the half that was missing is the half the user sees. The ledger row was written, but `classify_query` discarded the returned `ModelResult` and never called `_account`, so `state["total_cost_usd"]` and the token totals began at zero while `total_calls` came from `budget.calls_made`, which the classifier does increment. The chat footer rendered "3 calls" beside a dollar figure covering 2 of them, understating the modal turn by one Haiku call, exactly the defect this section claimed to have fixed. `backend/tests/test_cost_reporting.py` now asserts per-route that the footer's cost, input tokens, output tokens, and call count all equal the ledger's own sum over that turn, against both stub rows and a fake priced provider.

**Multi-tier JSON repair.** The final-response node attempts up to four parsing strategies to recover from LaTeX-in-JSON collisions. Failed parses that trigger a retry are pure waste, and the underlying cause is a prompt problem rather than a parsing problem.

*Now measured rather than guessed.* `_extract_json` reports which of `direct`, `fence`, `braces`, `regex`, or `failed` recovered the payload, and the distribution is written per turn and reported by `GET /api/usage`. This is the concrete gate for Lever 3's remaining `normal_rag` downgrade: it may be defaulted on when a Haiku sample shows no worse a `regex`-or-`failed` rate than the Sonnet baseline over turns recorded with a real key.

---

## 5. Target

A defensible target for Origami, given the levers above, is **under $5 per month for typical personal use**, with a fully local mode at zero marginal cost. The local mode is aspirational, not built: see §6 item 4.

This is achievable primarily because a personal knowledge base has a fundamentally cheaper shape than a general agent: the corpus is embedded once, retrieval is free, and the expensive generative step is invoked only when the user actually asks something. The expensive systems are expensive because they run continuously. Origami should not.

**The single most important design rule that follows: Origami must be event-driven, not polling.** Ingestion happens when a file changes. Generation happens when the user asks. Nothing runs on a timer with a full context window attached.

---

## 6. Unverified

1. The Hermes and OpenClaw overhead figures in §2 are `[SECONDARY]` throughout, drawn from community reporting and vendor-adjacent comparison blogs rather than published telemetry. The relative shape is consistent across independent sources and is almost certainly right. The precise percentages should not be quoted as fact.
2. The 50 to 80% saving estimate for model routing in Lever 3 is `[UNVERIFIED]`. It depends entirely on the observed easy-to-hard query mix, which nobody has measured for this product. Instrument before claiming it.
3. The under-$5 target in §5 is `[UNVERIFIED]` until the levers are implemented and real usage is measured.
4. The "fully local mode at zero marginal cost" in §5 is `[NOT BUILT]`. The local text path was deleted in `df2993e` and Phase 4 did not restore it.

### What Phase 4 left unmeasured

Instrumentation exists and every mechanism above is proven by a test that needs no API key. That proves the mechanism, not the money. No `ANTHROPIC_API_KEY` was available, so the following remain unmeasured and must not be quoted as achieved:

| Claim | Unblocked by |
|---|---|
| Dollars saved by ingest caching | A key, one PDF, then `cache_read_tokens` from the ledger |
| Dollars per turn, and the month-to-date figure | A key, then `GET /api/usage` after real use |
| Lever 3's 50 to 80% | The observed route mix, plus the `json_strategy` gate before `ORIGAMI_CHEAP_FINAL` may default on |
| The under-$5 target | One month of recorded real use |

Rates in `backend/services/pricing.py` were verified against the published pricing page on 2026-07-29. An unknown model reports `priced=False` and is counted in `unpriced_calls`, so a stale table shows as a gap rather than as a silently understated total.

Three things the ledger deliberately refuses to report as money, because a plausible number is worse than an absent one:

- **Stub calls cost nothing.** `_stub_response` estimates its token counts as `char_count // 4`. Those estimates were being priced at the real per-token rate under the real model id, so `ORIGAMI_MODEL_STUB=1`, a documented keyless development mode, wrote fabricated dollars into the same monthly file a real key writes to, indistinguishable from real spend except for one boolean. A stub row is now `priced=False` at `$0.00`. The routed model id is still recorded, because which model a route picks is a claim the stub exists to verify; only the money is withheld. Its estimated tokens do still land in the totals, so `month_to_date` reports a `stub` subtotal alongside `total` and a blended month stays subtractable rather than merely flagged.
- **A response with no usage block is unpriced, not free.** Zeroed counts against a model that *is* in the price table returned `priced=True` at `$0.00` with no log line, so any systematic loss of usage metadata would have reported the pipeline as free and read as an enormous saving. It now logs an error and reports `priced=False`.
- **A call that raised still appears.** `Budget.authorize` spends the slot before the request goes out, so a failure used to leave the budget decremented and no ledger row, meaning a turn's `total_calls` could exceed its own rows and ingest's `[COST]` line understated a document by exactly the failed chunks its own comment calls billed. Failures now write a `failed=True`, `priced=False`, zero-token row and are counted in `failed_calls`.

`unpriced_calls` counts only real calls, so it keeps meaning "a model with no price entry" rather than blending in every call of a stubbed run.

---

## Sources

- [Embedding model pricing comparison, 2026](https://pricepertoken.com/embedding)
- [OpenAI embeddings pricing calculator, July 2026](https://costgoat.com/pricing/openai-embeddings)
- [Local vs OpenAI embeddings: RAG quality benchmark, 2026](https://localaimaster.com/blog/local-vs-openai-embeddings)
- [OpenClaw: token use and costs](https://docs.openclaw.ai/reference/token-use)
- [Cut your Hermes Agent token bill in half](https://lumadock.com/tutorials/cut-hermes-token-costs)
- [Hermes Agent cost breakdown, 2026](https://www.remoteopenclaw.com/blog/hermes-agent-cost-breakdown)
- [OpenClaw vs Hermes Agent: prompt and context compression](https://fp8.co/articles/OpenClaw-vs-Hermes-Agent-Prompt-Context-Compression)
