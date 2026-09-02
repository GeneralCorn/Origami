# Screenshot pipeline: on-device OCR, collections, and the two-stage ingest

**Date:** 2026-09-02
**Status:** Built. 365 backend tests pass. The Apple Vision adapter has not yet run on a Mac; see §8.
**Reads with:** `PRODUCT_DIRECTION.md` for the constraints this obeys, `ARCHITECTURE_V2.md` §2 for the Item and Segment shape it writes, `COST_MODEL.md` §3 for why nothing here calls Anthropic.

---

## 1. What this is for

Drop a batch of iPhone screenshots on the app and, a few seconds later, each one is filed where it belongs: a show to watch, a library to try, a ticker to keep an eye on, a paper to read. The text on the screenshot is searchable, the screenshot is embedded in a note the user can edit, and the agent can cite it by what it shows rather than by a content hash.

The measure is speed to useful. A screenshot should be in the index and in its note before the user has dropped the next one, and anything slower than that must happen afterwards, over an Item that already exists.

## 2. What existed, and why it was slow

The prerequisite branch shipped a working screenshot path: one Ollama call to `qwen2.5-vl:7b` returned the readable text, a caption, and a category from a fixed list (news, meme, code, recipe, ...), and the result was appended to a weekly digest. Three things made it the wrong shape for the job above.

1. **The VLM did the reading.** A 7B vision model transcribing a dense phone screen takes tens of seconds, drops lines, and paraphrases where it cannot read. Text recognition is a solved, deterministic, local problem, and `STATUS.md` had already named splitting it out as the next phase.
2. **The categories described the picture, not the intent.** Nobody screenshots a thing because it is a meme; they screenshot it because they mean to come back to it. A list that cannot say "to watch" or "to read" cannot file anything into a note worth opening.
3. **It needed Ollama to do anything at all.** `MODEL_STRATEGY.md` records that the configured VLM was not even pulled on the maintainer's machine, so the one local path in the product had never run where it was built. A pipeline that does nothing without a 6 GB model is a pipeline that mostly does nothing.

## 3. Decisions

### 3.1 OCR runs on-device, behind one protocol, with two engines

`services/ocr.py` defines `OcrEngine` (`recognize(path) -> OcrResult`) and `OcrResult` (lines with confidence and normalised boxes, engine name, image size, elapsed time). `ORIGAMI_OCR_ENGINE=auto` tries the engines in order; the rest of the pipeline never learns which one ran except through the name recorded on every segment.

| Engine | Platform | Weights | Status | Notes |
|---|---|---|---|---|
| `apple_vision` | macOS | in the OS | `[UNVERIFIED]` on hardware | `VNRecognizeTextRequest` via `pyobjc-framework-Vision` 12.2.2 (Python 3.13 wheels exist `[VERIFIED]`, PyPI). Accurate level, language correction, automatic language detection where the OS offers it. Written against Apple's API and the ocrmac and RhetTbull wrappers `[SECONDARY]`. Darwin-only dependency marker, so Linux and CI resolve it to nothing. |
| `rapidocr` | any | 32 MB bundled in the wheel | `[VERIFIED]` here | RapidOCR 3.9.2 on ONNX Runtime, PP-OCRv6 det/rec/cls. Measured 2.1 s on a 1179×2556 render at 4 CPU cores, every line correct, mean confidence 0.98; 0.3 s model load on first call. Pulls `opencv-python` (70 MB), which is why it is the `ocr-fallback` extra rather than a core dependency: the packaged macOS app never needs it. |
| `vlm` | any with Ollama | 6 GB, out of band | existing | The pre-OCR path. Used only when no engine is installed. Recorded as engine `vlm` with confidence 0, because the source reports none. |

Rejected: Tesseract (a binary the app would have to bundle and notarise, and weak on anti-aliased UI text), EasyOCR and PaddleOCR proper (bring back the PyTorch or Paddle runtime that Phase 0 removed), and any hosted OCR API (`PRODUCT_DIRECTION.md`: "sending photos to a third-party OCR API contradicts the one claim the product makes").

Reading order: Vision returns it; RapidOCR returns detection order, so boxes are clustered into rows by their vertical centre against the median line height and sorted left to right within a row.

### 3.2 Two stages, fast first

```
read text      OCR engine (0.3–2 s), or the VLM when there is no engine
classify       keywords + embedding similarity, milliseconds, no model call
file           index (ocr segments), collection note, weekly digest, record
caption        VLM, 10–30 s [SECONDARY], optional, serialised
re-file        only what the caption changed: the caption segment, the title, the collection
```

The first three steps are what "quickly" means: they need the OCR engine and the embedding model the index already uses, and nothing else. The caption pass is `ORIGAMI_VLM_ENRICH` and runs only when Ollama is up with the model pulled. It upserts segment ordinal 0 and rewrites the note entry and digest line in place; a failed caption leaves an indexed, filed Item behind rather than a pending one.

Upload starts the pipeline in the background by default (`ORIGAMI_SCREENSHOT_AUTO_PROCESS`). `/screenshots/process` still exists for a parked batch and no longer returns 503 when Ollama is down.

A screenshot with no OCR engine and no Ollama stays pending with a job error that says so. Indexing a placeholder would have counted it as processed and lost the text forever.

### 3.3 Collections, backed by notes

`services/collections.py` stores user-defined collections in `DATA_DIR/collections.json`: id, name, description, keywords, and the id of the note that accumulates entries. Seven are seeded (shows to watch, tech to try, markets to watch, papers to read, places to go, recipes to cook, inbox); the inbox is the one fixed member and the classifier's honest fallback. `/collections` is the CRUD surface.

Each collection's note is an ordinary file in `NOTES_DIR`, created on first use so an unused default never litters the notes list. An entry is a markdown block: heading, source app and date, the image by its relative path, the caption if one exists, and up to twelve content lines of the OCR as a blockquote. The block sits between `<!-- origami:screenshot <name> -->` markers, which is the only thing the pipeline relies on: a recategorised screenshot moves with whatever the user typed inside the block, and everything the user typed outside it is untouched.

The weekly digest survives as the chronological view, headed by collection names instead of the old closed list, and still reads pre-collections digests (their "Needs Review" heading maps to the inbox).

### 3.4 The classifier spends no model calls

`services/classify_screenshot.py` combines three signals, each already on the machine:

| Signal | Weight | What it is |
|---|---|---|
| keywords | 0.55 | Distinct keyword hits per collection, saturating at three. Word-boundary matched for single words so `api` cannot fire inside `rapid`. Precise when it fires, silent when it does not. |
| embedding | 0.45 | Cosine similarity between the OCR text and each collection's `name + description + keywords`, through the same bge-small model the index uses, turned into a distribution by a softmax at temperature 0.02. Collection vectors are cached. |
| VLM vote | +0.5 | Added to the collection the caption pass named. It saw the picture, so it outranks either text signal alone, but lexical and semantic agreement (up to 1.0) still outranks it. |

Confidence is the winner's score minus half the runner-up's, so two collections scoring alike read as uncertainty. Below `ORIGAMI_CLASSIFY_MIN_CONFIDENCE` (0.35) the screenshot files into the inbox. In practice: two keyword hits, or one decisive embedding, or the VLM alone, is enough; one stray keyword is not.

`[UNVERIFIED]` The embedding signal has been tested only with an injected embedder. The build sandbox could not download the bge-small weights (Hugging Face is blocked by its egress proxy), so the softmax temperature and the 0.45 weight rest on the documented behaviour of bge-small cosine ranges `[SECONDARY]` rather than on screenshots. `scripts/eval_screenshot_classifier.py` runs OCR and the classifier over a folder-per-collection of real screenshots and prints a confusion matrix; run it before tuning anything.

Why not a Haiku call per screenshot: `PRODUCT_DIRECTION.md` rules out per-item model calls at ingest, and `COST_MODEL.md` §3 is where the reasoning lives. A local text-only classifier through Ollama was also considered and rejected for now: it would put a second model load between the drop and the note, and the VLM already votes when it runs.

### 3.5 Retrieval changes

`services/rag.py` layers three adjustments over cosine ranking, all from `PRODUCT_DIRECTION.md`'s "keep the bytes, fix the ranking":

- **Chrome demotion.** A line that recurs across at least three screenshots (or 5% of them) is interface furniture, whatever application it belongs to. An OCR hit loses up to half its score in proportion to how much of it is such lines. Line frequency is a cached scan of OCR segments, invalidated when a screenshot is indexed.
- **Length penalty.** Segments under 40 characters take 0.85×; a few words match everything nearly as well as anything.
- **Exact-token recall.** Tickers, version strings, paper ids and package names (`NVDA`, `qwen2.5-vl`, `2401.12345`) embed badly and match exactly, so a query carrying one also runs a `$contains` lookup and the hits join the candidates at a floor score of 0.8.

Static chrome filtering also happens at index time (`services/screen_text.py`): the status bar, control labels ("Back", "Done", "Play") and icon glyphs never reach the embedder. Nothing is lost; the full OCR is in the record.

Search now takes `source_types` and `modalities` filters, over-fetches three candidates per result before reranking, and returns `title`, `collection`, `source_app`, `ocr_engine` and `raw_ref` on every hit. The agent's excerpt header uses them: `shot.png (screenshot "Severance episode page", filed under shows-to-watch) — text read out of an image by apple_vision, verbatim from the source`. The library gains a `collection` facet.

### 3.6 What gets stored

Per segment, in Chroma metadata, in addition to the Phase 3 schema: `collection`, `source_app`, `ocr_engine`, and on the segment's own span `ocr_confidence` (OCR segments) or `generated_by` (the caption). `content_source` stays `extracted` for OCR and `generated` for the caption, including the VLM's own transcription on a machine without an engine, because that field answers "did this come out of the artifact", and the engine name is what says how well.

Per screenshot, one JSON record in `DATA_DIR/ocr/<name>.json`: the OCR lines with confidence and boxes, the classification with its scores and method, the VLM result, the content lines, the note id, the digest week, and timestamps. It is the readable form of what was in the image, it is what `/screenshots/{name}/text` serves as plain text, and it is what a store rebuild would re-index without running OCR again. `.gitignore` covers it alongside the screenshots.

### 3.7 The VLM call

`services/vision.py` now sends the OCR text in the prompt and asks only for title, description, collection and source app; the transcription field is requested only when no OCR ran. The response is constrained by a JSON schema through Ollama's `format` field `[VERIFIED, Ollama API docs]`, with the collection as an enum of ids that exist, so normalisation downstream is a safety net rather than the mechanism. The image is downscaled to 1280 px on its longest side before encoding, `keep_alive` holds the model resident across a batch, and the health check is cached for 30 s because the status endpoint polls it.

One latent bug came out in testing: the old call constructed the usage ledger row without the `failed` field that `CallRecord` requires, so the first real VLM call would have raised inside the ledger write. It had never run.

## 4. API

| Route | What it does |
|---|---|
| `POST /api/screenshots/upload?process=` | Save by content hash, dedupe, start the pipeline (default) or park as pending |
| `GET /api/screenshots/pending` | On disk, not in the store, with the job stage if one is running |
| `GET /api/screenshots/status` | In-flight and recent jobs, pending count, which engines exist |
| `POST /api/screenshots/process` | Run every pending screenshot and wait; per-file results |
| `GET /api/screenshots/{name}` | The record, the store's view, the job |
| `GET /api/screenshots/{name}/text` | The extracted text as `text/plain` |
| `PATCH /api/screenshots/{name}/collection` | Move it: store, note, digest, record |
| `DELETE /api/screenshots/{name}` | Segments, record, note entry, digest line, file |
| `GET/POST /api/collections`, `PATCH/DELETE /api/collections/{id}` | The user's collections |
| `PATCH /api/digests/{week}/recategorize` | Kept for older clients; the same move |

## 5. Renderer

`#/capture` is a full-page drop target: drop anywhere, watch each screenshot go through reading, classifying, indexing and captioning in a live strip, then see it appear under its collection with the source app, date and an inline move control. A rail lists collections with counts (the inbox flags in amber) and states which engines this machine has. Extracted text opens in a side panel. The header gains an icon for it next to the digest.

Collection notes embed screenshots by `../screenshots/<name>`; the editor preview resolves that to the served image with the launch token (`urlTransform` in `markdown-editor.tsx`). The digest viewer files under collections and the library view gains a Collection facet.

## 6. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ORIGAMI_OCR_ENGINE` | `auto` | `auto`, `apple_vision`, `rapidocr`, or `off` (VLM does the reading) |
| `ORIGAMI_OCR_MIN_LINE_CHARS` | `3` | Lines shorter than this never reach the embedder |
| `ORIGAMI_VLM_MAX_SIDE` | `1280` | Longest side of the image sent to the VLM |
| `ORIGAMI_VLM_ENRICH` | `1` | Run the caption pass when Ollama is up |
| `ORIGAMI_CLASSIFY_MIN_CONFIDENCE` | `0.35` | Below this the screenshot files into the inbox |
| `ORIGAMI_SCREENSHOT_AUTO_PROCESS` | `1` | Start the pipeline on upload |
| `OLLAMA_KEEP_ALIVE` | `10m` | How long Ollama keeps the VLM resident |

Install: the Vision framework binding comes with `uv sync` on macOS. Elsewhere, `uv sync --extra ocr-fallback` adds RapidOCR and HEIC decoding.

## 7. Timings

| Step | Measured | Where |
|---|---|---|
| RapidOCR, 1179×2556 render | 2.1 s (0.3 s first-call load) | this sandbox, 4 cores, `[VERIFIED]` |
| Apple Vision, same size | not measured | expected well under a second on Apple silicon `[SECONDARY]` |
| classify, keywords | < 1 ms | `[VERIFIED]` |
| classify, embedding | one bge-small forward pass, tens of ms | `[UNVERIFIED]` here, model not downloadable |
| VLM caption, `qwen2.5-vl:7b` | not measured | 10–30 s on 16 GB Apple silicon `[SECONDARY]` |

## 8. What is not done

1. **Run the Vision adapter on a Mac.** `tests/test_ocr.py` has the shape of the smoke test (render, recognise, assert order and boxes); the RapidOCR version of it passes here. Until `AppleVisionEngine.recognize` has run once on hardware, treat `auto` as `rapidocr` in practice and expect to touch `performRequests_error_`'s return shape or `topCandidates_`.
2. **Evaluate the classifier on real screenshots** with `scripts/eval_screenshot_classifier.py`, then tune the weights, temperature and floor. The defaults are reasoned, not measured.
3. **HEIC** decodes only with the `ocr-fallback` extra (pillow-heif). iPhone screenshots are PNG, so this only matters for photos.
4. **Scanned PDFs.** The OCR engine could give PyMuPDF's empty pages text. Not wired.
5. **Photos via PhotoKit** (`INTEGRATIONS_RESEARCH.md`) would land on exactly this pipeline: Item per photo, OCR and caption segments, a collection. It waits on signing, not on this code.
6. **An agent action to file a screenshot** ("put this under papers") is a small route call the tool loop could make once one exists.
7. **Live Text** (`VKCImageAnalyzer`) reads some layouts better than `VNRecognizeTextRequest` on Sonoma+. Worth a comparison once the Vision path runs.

## 9. Sources

- RapidOCR on PyPI, 3.9.2, Python 3.8–3.13 classifiers: https://pypi.org/project/rapidocr/
- RapidOCR repository: https://github.com/RapidAI/RapidOCR
- pyobjc-framework-Vision 12.2.2 on PyPI: https://pypi.org/project/pyobjc-framework-Vision/
- ocrmac, a PyObjC wrapper over `VNRecognizeTextRequest`: https://github.com/straussmaximilian/ocrmac
- RhetTbull's Vision text-detection gist: https://gist.github.com/RhetTbull/1c34fc07c95733642cffcd1ac587fc4c
- Ollama API reference (`format`, `images`, `keep_alive`): https://github.com/ollama/ollama/blob/main/docs/api.md
- Ollama structured outputs: https://ollama.com/blog/structured-outputs
