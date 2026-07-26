# Architecture V2: the multimodal layer

**Date:** 2026-07-26
**Status:** Design, no code written
**Reads with:** `INTEGRATIONS_RESEARCH.md` for what may be ingested, `COST_MODEL.md` for what may be spent

---

## 1. What has to change and why

Today Origami models one thing: a PDF, chunked, contextualised, embedded into Chroma. The pipeline in `backend/services/ingest.py` assumes a document with pages, extracted by PyMuPDF, split by a recursive character splitter.

The target product ingests loose text snippets, calendar events, chat messages, screenshots, and photos. None of these are documents. A calendar event has no pages. A photo has no text until a vision model gives it some. A chat message is meaningless alone and meaningful in a thread. Forcing all of them through a document-shaped pipeline produces bad retrieval and unmaintainable code.

The change is to introduce one shared abstraction beneath all sources, and to attach the security metadata at the same time, because retrofitting it later means re-ingesting everything.

---

## 2. The Item and Segment model

Two entities replace the current implicit document model.

**Item** is the addressable thing a human would name: one PDF, one calendar event, one screenshot, one chat thread, one captured snippet. It carries identity, source, timestamps, and the provenance record from §3.

**Segment** is a retrievable unit of meaning within an Item: a chunk of a PDF, one message in a thread, the OCR text of one screenshot region, the description of one photo. Segments carry the embedding.

```
Item
  id
  source_type        pdf | note | snippet | screenshot | photo | calendar | message
  source_id          stable per-source identifier for idempotent re-sync
  title
  created_at         when the content came into existence
  ingested_at        when Origami saw it
  provenance         see §3
  raw_ref            path or handle to the original bytes, never inlined

Segment
  id
  item_id
  ordinal            position within the Item
  modality           text | ocr | caption | transcript
  content            the text that gets embedded
  content_source     extracted | generated
  embedding_model    the model that produced this vector
  span               optional, page range / timestamp / bounding box
```

Three fields deserve comment because they solve problems the current code has today.

**`content_source`** separates text that came out of the artifact from text a model invented about it. A photo caption is a model's guess. A PDF paragraph is not. When a retrieval hit is a generated caption, the agent needs to know it is reasoning about a description rather than a source. Conflating the two is how a system confidently cites something nobody wrote.

**`embedding_model`** fixes a documented defect. The repository's own concerns analysis notes that embedding model choice is baked into the Chroma vector space with no migration path and no per-chunk record of which model produced which vector. Recording it per segment turns a full re-ingest into an incremental re-embed.

**`source_id`** makes re-sync idempotent. Every connector in the integrations research is a polling or incremental source. Without a stable per-source identifier, every sync duplicates.

---

## 3. Provenance and taint: the load-bearing decision

This is the one decision that cannot be deferred, and it survives from the previous plan unchanged.

Origami assembles all three legs of the lethal trifecta as described in `INTEGRATIONS_RESEARCH.md` §8: private data by definition, untrusted content the moment any connector ingests something written by another person, and external communication as soon as the agent gains a fetch or send tool. Because the mitigation is structural rather than promptable, the metadata that makes it enforceable has to exist on every segment from the first ingestion.

```
provenance
  origin            self | counterparty | public | unknown
  trust             trusted | untrusted
  channel           the connector that produced it
  author            where known
```

The rule is mechanical: **content Origami did not receive from the user directly is `untrusted`.** A note the user typed is trusted. An incoming iMessage, a Slack message from a colleague, the text inside a PDF someone emailed, the OCR of a screenshot of a web page: all untrusted. This is not a judgement about the person. It is a statement about whether the bytes could contain instructions aimed at the agent.

Taint then propagates. Any agent turn whose retrieved context includes an untrusted segment is a tainted turn, and a tainted turn loses access to the third leg. Concretely, on a tainted turn the agent may not fetch a URL, may not send a message, and may not write outside the user's own store.

This is the structural guarantee the trifecta model calls for: at least one leg missing on every execution path. Untrusted content is allowed in, and the exfiltration route is removed for exactly those turns.

`[UNVERIFIED]` Whether this degrades the product experience noticeably in practice. The failure case is a user asking the agent to research something mentioned in a message they received, which is a legitimate and plausible request that this rule blocks. The mitigation is an explicit per-action user confirmation that lifts the restriction for one step. This needs testing with real usage before the ergonomics can be called acceptable.

---

## 4. Ingestion: normalise, then converge

Each source gets a thin adapter whose only job is to emit Items and Segments. Everything after that is shared.

```
source adapter  ->  Item + raw Segments
                      |
                      v
              modality processing        vision / OCR / transcript, only when needed
                      |
                      v
              contextualisation          existing Haiku step, now conditional
                      |
                      v
              embedding                  local by default
                      |
                      v
              Chroma
```

Two changes to the existing pipeline matter.

**Contextualisation becomes conditional.** Today every chunk gets a Haiku call. Per `COST_MODEL.md` §4 this is the largest per-document generative cost in the system. It earns its keep on a dense PDF, where a chunk stripped of surrounding context retrieves poorly. It is waste on a calendar event, a single chat message, or a short snippet, all of which are already self-contained. Gate it on segment length and modality.

**Contextualisation must stop failing silently.** The current implementation falls back to the raw chunk with no retry and no record. That means some fraction of spend buys nothing and nobody can tell which segments are degraded. Add retry with backoff, and record the outcome on the segment so retrieval can account for it.

---

## 5. Embedding strategy

Local by default, for three reasons that are about product rather than cost: no personal corpus leaves the machine, ingestion works offline, and there is no API key in the onboarding path.

`COST_MODEL.md` §1 establishes that this is not a cost decision. Embedding the entire corpus costs single-digit dollars either way.

The current model is `bge-small-en-v1.5` at 384 dimensions, and the port plan moves it from `sentence-transformers` to `fastembed` to drop the Torch dependency.

**A correction to the inherited plan.** The previous plan asked whether `fastembed` produces vectors identical to the `sentence-transformers` build, and treated a "yes" as meaning the existing Chroma store survives untouched. BAAI documents that the **unquantized** ONNX export matches the Torch output. `fastembed` ships **quantized** ONNX models. Quantization is not output-preserving. The likely answer is therefore that the vectors are close but not identical.

This matters less than it appears, and the reason is worth internalising. Because §2 records `embedding_model` per segment, a change in embedding is no longer a catastrophe requiring a full re-ingest. It is an incremental re-embed of segments whose recorded model does not match the current one, reading `content` that is already stored. The raw artifacts do not need reprocessing, and no vision or contextualisation calls are repeated.

The metadata field turns a blocking migration question into a background job. That is the entire argument for adding it now.

---

## 6. Retrieval

Retrieval gains three things beyond the current similarity search.

**Filter before search.** Item-level metadata makes source, time range, and trust level cheap pre-filters. "What did I discuss last week" should not be a semantic search problem.

**Trust-aware results.** Retrieved segments carry their provenance into the agent's context, both to drive the taint rule in §3 and so the agent can distinguish what the user wrote from what someone sent them.

**Modality-aware presentation.** A hit on a generated photo caption should surface the photo, not the caption text. `content_source` and `raw_ref` make this possible.

---

## 7. Migration order

The ordering is chosen so that each step leaves a working system, and so that the irreversible decision comes first.

1. **Schema first, with provenance.** Introduce Item and Segment, and write provenance on every write path. Do this before any new connector exists. This is the step that cannot be reordered, because every later step writes data that would otherwise need re-ingesting.
2. **Migrate the existing PDF path onto the schema.** No behaviour change, no new sources. Existing documents become Items with `origin: self`. This proves the schema against the one pipeline that already works.
3. **Add `embedding_model` and backfill it** with the current model for all existing segments. Cheap now, and it unblocks the `fastembed` swap.
4. **Fold in the uncommitted screenshot and vision work.** That branch already produces exactly the shape §2 describes: an artifact with generated text about it. It is the natural first non-document Item and it is already written.
5. **Snippet capture.** The simplest new source, no third party, no permissions. Validates the ingest path end to end.
6. **First permissioned local source: Calendar.** This is where the macOS TCC work in the port plan gets proven, and per `INTEGRATIONS_RESEARCH.md` §4 the failure mode is silent, so it needs to be first among permissioned sources rather than later.
7. **Everything else**, in the order the integrations matrix allows.

Note that steps 1 through 5 involve no third-party integration at all. The riskiest external dependencies are deliberately last, and the one irreversible schema decision is deliberately first.

---

## 8. Open questions

1. `[UNVERIFIED]` Whether the taint rule in §3 is ergonomically acceptable. §3.
2. `[UNVERIFIED]` The magnitude of divergence between quantized `fastembed` vectors and the current `sentence-transformers` vectors. One script answers it, and §5 explains why the answer is no longer blocking.
3. `[UNVERIFIED]` Whether Chroma remains the right store once metadata filtering becomes a hot path rather than an afterthought. Not urgent, but the answer should be known before the corpus grows large enough to make migration painful.
4. `[UNVERIFIED]` How threads should map onto Items for message sources. One Item per thread with one Segment per message is the obvious reading, but it makes Items unbounded in size and never final, which nothing else in the model does.
