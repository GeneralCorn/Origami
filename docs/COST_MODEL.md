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

### Lever 2: Never poll with full context

The $250-per-week heartbeat is entirely self-inflicted. Any background or scheduled work must run against a summary and a cheap model, and escalate to full context only when the summary indicates there is something to do.

Rule to encode: **no scheduled task may send the conversation context window.** If a background job needs context, it earns it by first passing a cheap check.

Expected saving: eliminates the single largest failure mode outright.

### Lever 3: Route by difficulty, not by default

Most turns in a personal knowledge tool are retrieval and summarisation, which small models handle well. Frontier models should be reserved for synthesis across many sources and for multi-step reasoning.

Origami is already positioned for this. The stack carries `langchain-ollama`, so a local path exists. Note that `backend/services/ollama.py` was deleted in the current uncommitted working tree, so the local model path is presently in flux and the port should decide deliberately whether to restore it.

Expected saving: large but highly workload-dependent, plausibly 50 to 80% of generative spend.

### Lever 4: Cap the agent loop by difficulty

`backend/services/agent.py` runs a research loop bounded by `MAX_RESEARCH_LOOPS`. The current working tree already reads `state.get("max_loops", MAX_RESEARCH_LOOPS)`, making it per-request configurable, which is the right shape. What is missing is a policy that actually sets it lower for easy queries.

Every additional loop iteration re-sends the accumulated context. Iteration cost grows superlinearly with loop count.

Expected saving: proportional to how often easy queries currently run the full loop.

---

## 4. Where Origami already spends, today

Three existing behaviours are worth naming because they are live cost centres, documented in the repository's own concerns analysis.

**Per-chunk contextualisation at ingest.** `backend/services/ingest.py` calls Haiku once per chunk to contextualise it before embedding, with a concurrency semaphore of 4. This is a genuine quality win and it is also the largest per-document cost in the system. Unlike embedding, this one is real money, because it is a generative call per chunk. It also fails silently and falls back to the raw chunk with no retry, so some spend currently buys nothing.

**Classifier on every research query.** `classify_query()` calls Haiku unless weak heuristics match, adding 1 to 2 seconds and a call to most queries. Cheap per call, but it is on the hot path for every single interaction.

**Multi-tier JSON repair.** The final-response node attempts up to four parsing strategies to recover from LaTeX-in-JSON collisions. Failed parses that trigger a retry are pure waste, and the underlying cause is a prompt problem rather than a parsing problem.

---

## 5. Target

A defensible target for Origami, given the levers above, is **under $5 per month for typical personal use**, with a fully local mode at zero marginal cost.

This is achievable primarily because a personal knowledge base has a fundamentally cheaper shape than a general agent: the corpus is embedded once, retrieval is free, and the expensive generative step is invoked only when the user actually asks something. The expensive systems are expensive because they run continuously. Origami should not.

**The single most important design rule that follows: Origami must be event-driven, not polling.** Ingestion happens when a file changes. Generation happens when the user asks. Nothing runs on a timer with a full context window attached.

---

## 6. Unverified

1. The Hermes and OpenClaw overhead figures in §2 are `[SECONDARY]` throughout, drawn from community reporting and vendor-adjacent comparison blogs rather than published telemetry. The relative shape is consistent across independent sources and is almost certainly right. The precise percentages should not be quoted as fact.
2. The 50 to 80% saving estimate for model routing in Lever 3 is `[UNVERIFIED]`. It depends entirely on the observed easy-to-hard query mix, which nobody has measured for this product. Instrument before claiming it.
3. The under-$5 target in §5 is `[UNVERIFIED]` until the levers are implemented and real usage is measured.

---

## Sources

- [Embedding model pricing comparison, 2026](https://pricepertoken.com/embedding)
- [OpenAI embeddings pricing calculator, July 2026](https://costgoat.com/pricing/openai-embeddings)
- [Local vs OpenAI embeddings: RAG quality benchmark, 2026](https://localaimaster.com/blog/local-vs-openai-embeddings)
- [OpenClaw: token use and costs](https://docs.openclaw.ai/reference/token-use)
- [Cut your Hermes Agent token bill in half](https://lumadock.com/tutorials/cut-hermes-token-costs)
- [Hermes Agent cost breakdown, 2026](https://www.remoteopenclaw.com/blog/hermes-agent-cost-breakdown)
- [OpenClaw vs Hermes Agent: prompt and context compression](https://fp8.co/articles/OpenClaw-vs-Hermes-Agent-Prompt-Context-Compression)
