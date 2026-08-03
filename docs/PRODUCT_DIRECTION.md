# Product direction

Decided 2026-07-30. This is the framing the rest of the work is measured against. `STATUS.md` says where the build actually is; this says what it is for.

## The shape

Everything you encountered, held locally, organised by how it arrived, with a briefing on top.

The core loop, in order: **private local ingestion, then embed, index, connect, and brief.** Ingestion is the part that has to be right, because it is the only part nothing else can do for you.

## Why this and not the other framings

Two earlier framings were considered and rejected.

**"A better Obsidian" loses by construction.** Obsidian is a decade of editor refinement plus a plugin ecosystem. `EDITOR_DECISION.md` shows what parity costs on a single feature: the CodeMirror spike found caret semantics at widget boundaries are hand-built, and the prototype got them wrong in a way that silently corrupts markdown. Editor work is a race already lost, and the user research says people abandon these tools over fragility rather than polish.

**"An academic brain" is too narrow, and points at the blocked half.** It also invites comparison with Zotero, which owns reference management and citation export into Word and LaTeX. Read Zotero's library as a source instead of competing with it.

**Organising by source type is a genuinely different axis.** Obsidian organises by folders and links, Notion by databases and pages, and both assume you wrote the thing. A corpus you did not author wants to be organised by where it came from. The schema already carries this: `source_type` on every Item, `modality` on every Segment. The library view is a view over data that exists, not a new model.

## What only this product can do

An Obsidian plugin cannot read a photo library, a calendar, or a message database. macOS binds TCC grants to a signed bundle and the usage-description keys in its `Info.plist`, and a plugin inherits its host's permissions and cannot declare its own. That ceiling is structural, not a matter of effort, and it is the whole reason a standalone app is worth building.

Everything else in the vision is reachable by other tools. This is not.

## Constraints that are not negotiable

**Ingestion stays local.** Cloud OCR was considered and rejected. Sending photos to a third-party OCR API contradicts the one claim the product makes, and does so on the most sensitive material in the corpus. On-device options exist and should be evaluated in this order: the macOS Vision framework first, since it is on-device, free, and already present; PaddleOCR if a cross-platform path is needed later.

**No per-item model calls at ingest beyond what already exists.** `COST_MODEL.md` §3 and `MODEL_STRATEGY.md` both land here. Semantic auto-categorisation on every import is the expensive shape. Categorisation that costs nothing (source type, modality, dates, provenance, folder) comes first, and anything model-driven is something the user triggers.

**Nothing is discarded at ingest.** See retention below.

## Retention, and what actually costs

Measured against the real store on 2026-07-30: 105 records occupy 5.2 MB, so roughly **50 KB per record**, with documents averaging 995 characters and metadata 1,918.

A screenshot produces about three segments, so ten thousand screenshots is on the order of **1.5 GB of index**. The originals behind them, at around 800 KB for a retina PNG, are closer to **8 GB**, and up to 20 GB if they are large.

The images outweigh the index by roughly ten to one. That settles the retention question: the index is not what gets expensive, so a discard system that prunes index entries solves the wrong problem. What can be pruned is originals, which `raw_ref` already points at rather than inlining, so a thumbnail plus the extracted text can outlive the source file without breaking a citation.

**Usefulness is not decidable at ingest.** It is query-dependent, and the three words that look like noise today are what you search for in eight months. Mem0 and Supermemory work by extracting salient facts and discarding the source, which is exactly what the provenance schema exists to prevent. `research/competitive-landscape-2026-07.md` reached the same verdict: the corpus is the memory.

So the rule is **keep the bytes, fix the ranking.** Signal-to-noise on screenshots is a retrieval problem, and it has cheap local answers:

1. Skip embedding segments below a length floor.
2. Demote lines by how often they recur across the corpus. Interface chrome repeats in every screenshot of an application while real content appears once, so document frequency identifies it with no model and no rules, and it tunes itself to whichever applications the user actually runs.
3. Prefer the caption when the OCR is mostly chrome. The VLM caption is already a salience signal, which is why it sits beside the OCR rather than replacing it.

**Staleness is a separate axis from salience**, and it is the one case where deletion is defensible: a framework that no longer exists, an application long since removed. The schema is bi-temporal (`created_at` for when the content came into existence, `ingested_at` for when Origami saw it), so age is answerable without guessing. This is worth building only once a corpus is large enough to have a tail, and it should target originals before index entries.

## Deliberately deferred

**The programmable view layer.** Canvas, tables, graphs, plugins, a query language. This is Notion's entire product and it is where this stalls if started early. The schema is already faceted, so a filterable library view delivers most of the feel without any of it.

**MCP and the Obsidian bridge.** Designed, and parked until real users exist. The right shape is a bridge rather than a port: Origami holds the corpus and owns the permissions, and a thin plugin queries it over loopback. That avoids competing with Smart Connections, which already does local vault embeddings free and with zero configuration, and it sidesteps the permission ceiling entirely.

**Anything requiring a cloud vector store.** Chroma runs locally and has never been the bottleneck.

## How this is judged

Not against Obsidian's editor. Against whether your own photos, PDFs, articles, and screenshots are searchable in one place, and whether the answers cite what they came from and say whether a human wrote it or a model guessed it.

The bar to clear is not Obsidian, it is Smart Connections plus Copilot plus Ollama, which together cover most second-brain use cases locally and free. The gap is that all of them operate on a vault of things you typed.
