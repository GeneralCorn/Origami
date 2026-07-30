# Editor Decision: CodeMirror 6

**Date:** 2026-07-30
**Status:** Decision made, spike built and adversarially evaluated, no production code
**Resolves:** `ELECTRON_PORT_PLAN.md` §4 open question, and §8 question 3
**Reads with:** `ELECTRON_PORT_PLAN.md`, `ARCHITECTURE_V2.md`

---

## 1. Verdict

**CONFIRMED. CodeMirror 6, markdown on disk as the source of truth.** A working spike (`74461e5` on `claude/spike-codemirror`, dev route only) put block-level image widgets in front of a real note file bound to the real backend, and the decisive evidence is that the document never stopped being a string. A 183-line adversarial markdown fixture containing YAML front matter, five list-marker styles, tab and three-space nesting, four fence styles, twelve image forms, escapes, hard breaks, GFM tables, HTML comments, footnotes and a unicode torture block loaded byte-identical, and every edit produced a diff hunk containing exactly the typed characters and nothing else. The same fixture parsed and re-serialized through `mdast` with **zero user edits** changed 90 of its 183 lines. That gap is the whole decision: a text editor pays no round-trip tax because there is no round trip, and a tree editor pays it on every save forever.

The verdict is confirmed on the axis that matters for this product, not on every axis. The question as written in §4 asked whether CodeMirror 6 handles mixed media "as cleanly as a ProseMirror-based editor would," and the honest answer to that literal comparison is **no**. A ProseMirror atom node has a defined selection model; a CodeMirror block widget is a decoration painted over text, and caret semantics at the widget boundary have to be hand-built. The spike got that wrong in a way that silently corrupts markdown, and Obsidian, with a funded team, was still shipping image-widget interaction fixes in July 2026, roughly four and a half years after Live Preview launched. The decision holds because fidelity dominates cleanliness for a knowledge base whose files must stay portable and greppable, not because CodeMirror won on ergonomics.

---

## 2. What the question actually decomposed into

The §4 question conflated four separable things. Splitting them is why the answer came out clean.

| Sub-question | Answer | Confidence |
|---|---|---|
| Can CM6 render block media between paragraphs at all? | Yes, first-class API, mainstream pattern | `[VERIFIED]` |
| Does the file on disk stay exactly markdown? | Yes, exactly, by construction | `[VERIFIED]` |
| Is it fast enough on real documents? | Yes, by a wide margin | `[VERIFIED]` |
| Does it feel as clean as a tree editor at the media boundary? | No, and this is a permanent structural gap | `[VERIFIED]` |

The fourth answer does not reverse the decision because the third and second are worth more here. It does set the scope of Phase 6, which is bigger than the plan implied.

---

## 3. What was measured

Every number below came from running something. The spike was driven headless with Puppeteer against the Vite dev server and the real Python backend, and was then re-run independently in an isolated git worktree by an adversarial pass that re-tested each claim rather than trusting it.

### 3.1 Markdown fidelity `[VERIFIED]`

Tested by byte-diffing the file on disk after saves that went through the real path, `updateNote` to `PUT /api/notes/{id}` to `path.write_text` in `backend/routes/notes.py`.

- Load is lossless. Editor document string equals disk content, 3439 characters each, first differing index -1.
- One 44-character edit mid-document, saved: `diff -u` against the original is a single hunk containing exactly those 44 characters. Undo, save: sha256 identical to the original.
- Five targeted edits inside whitespace-sensitive constructs (a trailing two-space hard break, a tab-indented list child, a fenced code line with internal space runs, a GFM table row, a whitespace-only line) produced five hunks, each exactly the typed characters. Nothing was realigned, renumbered, re-marked, trimmed or re-escaped. Zero-width space, soft hyphen, BOM, form feed and vertical tab all survived.
- Block widgets never write to the document. Across eight edit operations and six saves, no diff ever contained anything that was not typed.
- Paste discards rich text. A clipboard carrying both `text/html` and `text/plain` inserted the plain text verbatim; the HTML flavour was dropped entirely.
- Still greppable: `grep '!\['` on the saved file returns every image line, including the ones sitting behind rendered widgets.
- Correctly conservative: images inside a fenced block and inside an indented code block were not turned into widgets.

**The comparison number.** The same fixture through `mdast-util-from-markdown` plus `mdast-util-to-markdown` with GFM extensions, no user edits: 90 of 183 lines changed, 3439 to 3488 characters. Front matter destroyed (`---` became `***`, the closing fence turned the last key into a setext H2), entities decoded, `\\` collapsed to `\`, setext headings converted to ATX, `_em_` to `*em*`, bullets normalised, an ordered list renumbered, a three-level nested list flattened to one, `~~~js` to backticks, the indented code block converted to a fence, a two-space hard break rewritten as a trailing backslash, tables re-padded, a bare URL autolinked.

`[SECONDARY]` That 90-line figure is a **charitable floor** for what a tree model costs, not a measurement of ProseMirror. `mdast` is markdown-native and therefore strictly more faithful than a ProseMirror or Lexical document schema, which has no node type at all for front matter, reference definitions, HTML comments or footnotes without plugins. No ProseMirror or Lexical editor was built and none was measured.

### 3.2 Feasibility and performance `[VERIFIED]`

- Block widgets are stable public API: `Decoration.replace({block: true})` in `@codemirror/view`, current 6.43.7.
- Viewport virtualization works with them. On a document with 1500 image widgets, `widgetsInDOM` stayed at 1 to 3 and `contentHeight` reported 261,852px. No DOM is built for off-screen media.
- The whole-document `StateField` rebuild, which the architecture forces because a `StateField` cannot see the viewport, is not the problem it looks like: 0.4ms at 27KB, 0.7ms at 135KB, 1.4ms at 407KB, 2.4ms at 815KB and 12,002 lines, 4.3ms with 1500 images. Independently re-measured at 1.12ms per scan on a 1MB / 800-image document, with typing p50 4.1ms and max 6.7ms.
- `npm run typecheck`, `build:main`, `build:renderer` and `smoke` all pass. Backend `pytest`: 212 passed.

### 3.3 Editing and undo `[VERIFIED]`

- Deleting a widget line three different ways removed 48 to 50 characters each with no `![alt](` residue.
- Undo restored 1871, 1862, 1853, 1853, 1853 characters back to the exact baseline; redo restored byte-exact.
- Vertical motion treats the block as atomic: `ArrowDown` visited lines 7, 8, 10, 11, 12, never landing on the image line. `ArrowRight` skipped all 46 characters as one unit.
- Click-to-reveal works and the document is unchanged while revealed.

### 3.4 Height stability `[VERIFIED]`

This is the one genuinely hard problem, and it is solvable with a caveat. Twenty images, 400ms simulated latency, true document height 15,415px, measuring `contentHeight` wobble across a full scroll pass.

| Configuration | Height wobble | Wrong-way scrolls | Max jump |
|---|---|---|---|
| Nothing | 6,105px (51.9%) | 3 to 5 | 1,650px |
| `estimatedHeight` only | 3,258px (21.7%) | 0 | 1,638px drift |
| Reserved box only | 3,411px (29.0%) | 0 | none recorded |
| **Reserved box + `estimatedHeight`** | **403px (2.6%)** | **0** | **0** |
| Reserved box + `estimatedHeight`, **cold cache** | 3,389px (27.9%) | 3 to 5 | 1,650px |

Both knobs are required and neither alone works, because they fix different halves: `estimatedHeight` covers content that has not been drawn, reserved width and height attributes cover content that is drawn but not yet decoded. `requestMeasure` on load is redundant once the box is reserved, and it increases redraw churn.

`[VERIFIED]` Vertical CSS margins on a block widget permanently desync the height map and `requestMeasure()` does not repair it: `margin: 40px 0` on two widgets left the content DOM 160px taller than `view.contentHeight`, unchanged after an explicit remeasure. Padding on an inner element gives a delta of 0. This is documented in one clause of the CodeMirror source and nowhere else.

**The caveat is the whole risk.** The mitigation is a dimension cache, and the cache is cold exactly once per image, which for a screenshot-capture product is the moment the screenshot is pasted in. Measured cold on a 24-image note: `scrollHeight` reported 2837px against a true 16338px, a 5.7x understatement, and setting `scrollTop` to the nominal middle landed on image 21 of 24 before the position was silently re-indexed.

### 3.5 Bundle cost `[VERIFIED]`

Three real production builds with `node_modules` held constant.

| Measurement | Raw | Gzip |
|---|---|---|
| Branch as committed, JS delta | +14 B | +9 B |
| Branch as committed, fixture PNGs shipped | +89,029 B | n/a |
| CM6 as an isolated chunk | 525,347 B | 181,213 B |
| **Net if MDEditor is swapped out for CM6** | **+446,114 B (+21.9%)** | **+153,773 B (+23.8%)** |
| CSS delta on that swap | -7,221 B | -1,267 B |

The `import.meta.env.DEV` guard genuinely works: a production build contains zero CodeMirror, and grepping `dist/renderer` for `cm-content`, `cm6-image-block` and `spike-cm6` returns nothing. The 89KB of fixture PNGs in `renderer/public/` are the branch's only real production delta.

**The counter-intuitive result deserves emphasis.** In isolation CM6 is much smaller than what it replaces: over a bare React baseline, CM6 adds 224,448 B gzip against `@uiw/react-md-editor`'s 534,883 B, and dropping to `commonmarkLanguage` instead of `markdownLanguage` cuts CM6 to 141,210 B. But swapping does **not** remove the markdown dependency, because `@uiw/react-markdown-preview` is a separate direct dependency that renders every AI chat message in `animated-text.tsx`. Only about 79KB of MDEditor-specific code actually leaves. So the adoption is a net **+154KB gzip on the startup path** unless the chat renderer is migrated in the same workstream. Plan for both or plan for the regression.

### 3.6 Dependency and security posture `[VERIFIED]`

- Six new direct dependencies pull in 21 packages, all CodeMirror and Lezer ecosystem. `npm audit` reports 32 vulnerabilities, all of them pre-existing dev-only `@electron-forge` transitive issues; none of the 21 new packages appears in the list. `npm audit --omit=dev` finds 0.
- No XSS was found in the widget. `![x](javascript:...)` produced `ERR_UNKNOWN_URL_SCHEME` and a quote-injection payload did not parse, because `paint()` uses `setAttribute` rather than string concatenation.

---

## 4. What broke

The spike found real defects. Some are spike bugs with cheap fixes, some are properties of the model that the editor work inherits. The distinction is the useful part.

### 4.1 Model-level, and the expensive one

**Caret semantics at the widget boundary are not sound.** `[VERIFIED]` For a widget spanning `[from, to]`, the caret position reported by the state, the caret drawn on screen, and the position typed text actually lands in are three different places. Measured on an image line at `from=24, to=60`:

- Caret at 24: state reports head 24, the drawn caret is a 193px bar spanning the widget's full left edge, and typing lands at position 61, on the line **below** the image.
- The same position typed through the multi-cursor path instead inserts **into** the image line, producing `![one](/spike-media/wide-banner.png)!!` and destroying the widget.
- Paste with a selection ending at `from` yields `REPLACED![one](...)`. Paste at `to` yields `![one](...)PASTED`. Text dropped onto the rendered image yields `DROPPED![one](...)`. All three destroy the image.
- Click-to-reveal parks the caret at `from + 1`, so click-then-type yields `!Z[one](...)`.

The root cause is a genuine tension, not carelessness. The spike's `selectionEnters` requires a **strictly interior** overlap (`range.from < to && range.to > from`), and that rule is what fixed an earlier and worse bug where a single forward-Delete from the line above dismissed the decoration and ate the markdown one character at a time. Loosening it re-breaks deletion; keeping it leaves the boundary positions typed-into. ProseMirror does not have this problem because an atom node has a `NodeSelection`: clicking selects the node as a unit and typing replaces it. Reproducing that on top of a text model means owning a hand-built selection state machine. **This is the real cost of the CodeMirror choice and it should be scheduled explicitly, not discovered.**

### 4.2 Spike bugs with known fixes

- `[VERIFIED]` **The content-width bridge is dead after the first resize.** `contentWidthBridge` calls `view.dispatch` from inside `ViewPlugin.update()`, CodeMirror throws `Calls to EditorView.update are not allowed while an update is in progress`, and the plugin is **permanently deactivated**. Measured across four viewport widths, the field stayed frozen at its mount value of 720 while the real content DOM went 494, 674, 720, 434. The downstream effect on a cached 600x900 image is a 924px estimate against a true 677px, a 37% over-estimate on every undrawn widget. So the height-stabilisation machinery the spike exists to validate was **not actually running** during part of the evaluation, which makes the §3.4 numbers a floor rather than a ceiling. The constructor already does this correctly with `queueMicrotask`; `update()` needs the same.
- `[VERIFIED]` **CRLF is silently normalised to LF**, by both layers independently. The backend's `read_text` strips CR before the editor sees the content, and `EditorState.lineSeparator` is never set. A one-character edit on a 3657-byte CRLF file wrote back 3475 bytes with all 183 line endings changed. A git diff would report every line changed for a one-character edit. Two-line fix: set `lineSeparator` from the loaded content, and open with `newline=""` in `backend/routes/notes.py`.
- `[VERIFIED]` **The dimension cache has no invalidation.** Serving a 600x2400 image, then replacing the file on disk with a 600x150 one, left the cached 600x2400 in `localStorage` forever: reserved 2426px against a real 176px, a 39% document-height error that only corrects once the widget is drawn. The cache is also global, keyed only on `src`, unbounded and never evicted.
- `[VERIFIED]` **Any image URL in note content is fetched automatically**, with no allowlist, no local-only check and no referrer policy. A note body containing `![pixel](https://tracker.example.net/p.gif?note=secret-note-id)` produced a real outbound request with a `referer` header. Merely opening a note is enough. For a product that ingests untrusted content and whose pitch is local-first, this is a working tracking-pixel channel and needs a policy decision before shipping, not after.
- `[VERIFIED]` **Any external value change destroys undo history.** The reconcile effect cycles the history compartment, which is correct for a note switch and data loss for anything else. In the real app, `handleTitleChange` rewrites line 1 on **every title keystroke** and the AI `edit_current` branch refetches and replaces the whole note, so both would wipe the user's undo stack.
- `[VERIFIED]` **The incremental parser stalls and does not advance while idle.** On a 795KB fixture the parse frontier sat at 21% with 107 of 500 images detected, unchanged across 12 samples over 4.8 seconds. The symptom is document height growing 28% when the viewport finally reaches unparsed regions, not visibly unrendered source.
- `[VERIFIED]` **Cursor-reveal costs a 171px content-height jump** as a 192px widget collapses to a 21px text line. This is Obsidian's known complaint, reproduced exactly.
- `[VERIFIED]` Minor: angle-bracket image destinations render broken; reference-style and empty-URL images never render; a failed image load gets a 48px empty strip with no `onerror` affordance; the line-number gutter loses the number for every image line; the 89KB of fixture PNGs ship in production builds.

### 4.3 What did not break

Worth recording, because these were the predicted failure modes. `[VERIFIED]` The cross-wired `updateDOM` hazard the research warned about does fire, one to two times per fast scroll, but never produced a widget showing an image that disagreed with its source line across 160 samples. No reading-position jump was reproducible under 400ms simulated latency scrolling **downward**; the failure is scrolling upward through undrawn content. No React round-trip race on an 80-character zero-delay burst. The existing `@uiw/react-md-editor` is untouched and renders the same note identically.

---

## 5. What the prototype did not test

Stated plainly, because a spike's blind spots are the part that costs money later.

`[UNVERIFIED]` **The packaged Electron shell.** Everything ran against the Vite dev server in headless Chrome. Same Chromium engine, but no verification under the real shell, no GPU compositing path, and critically **no macOS momentum scrolling**. `page.mouse.wheel` cannot reproduce kinetic scroll, and kinetic scroll is precisely where the atomic-editor author reported the worst height-map symptom ("on iOS that reads as an anchor conflict and halts kinetic scroll"). This is the single highest-value thing to re-test first in Phase 6.

`[UNVERIFIED]` **Whether the residual 2.6% wobble is perceptible.** It was measured, not watched. No human used it.

`[UNVERIFIED]` **Retina.** No `deviceScaleFactor: 2` run.

`[UNVERIFIED]` **Real remote images.** Fixtures were 5 to 23KB local PNGs with artificial latency.

`[UNVERIFIED]` **IME composition, spellcheck and autocorrect rewrites.** Untested, and all three write to the document through paths that interact with widget boundaries.

`[UNVERIFIED]` **The existing editor's actual contract.** The spike reproduces exactly two of its behaviours, the four-prop interface and a title input. Untouched: `$$` block-math auto-expansion, KaTeX rendering, GFM task lists, the derive-title-from-first-H1 rule enforced independently in the renderer and the Python backend, the 1s autosave debounce, and the known lost-update race between the renderer's whole-file PUT and the backend's read-append-write.

`[UNVERIFIED]` **Windows line-ending behaviour.** `write_text` with default `newline=None` translates to `os.linesep`, which is LF on the test machine. Out of scope while the plan is macOS-only, but it is a landmine if that changes.

`[UNVERIFIED]` **Regression safety in general.** There is no renderer test suite anywhere in the repository. No `*.test.*`, no vitest or playwright config, no test script in `desktop/package.json`. "Nothing broke" is a weak claim when nothing tests the editor today. A CM6 swap would land with zero regression net.

---

## 6. Cost of adoption

### 6.1 Feature surface that has to be rebuilt

The spike is a demo of one feature, not a replacement editor. `@uiw/react-md-editor` currently supplies, for free, everything in this list, and CM6 supplies none of it.

| Surface | Detail |
|---|---|
| Toolbar | 17 commands plus 5 extra (bold, italic, strikethrough, hr, 6-entry title group, link, quote, code, code block, comment, image, table, three list types, help, plus edit/live/preview/fullscreen) |
| Keyboard | 23 shortcuts |
| Editing behaviours | Tab and Shift-Tab indent at tabSize 2, Enter continuation of `-`, `*`, `- [ ]` and numbered lists, Ctrl-D line duplication |
| Preview | Live side-by-side pane, editor-to-preview scroll sync, preview-only and fullscreen modes |
| Render pipeline | remark-gfm, rehype-raw, rehype-slug, autolink-headings, rehype-prism |
| Math | KaTeX via remark-math and rehype-katex, plus the hand-written `$$` auto-expansion handler with synchronous scroll restoration |
| Theming | Three-into-two theme mapping. The spike's theme wiring is inert: two of its three CSS custom properties are never defined anywhere, and the `data-cm6-theme` attribute it sets is read by nothing |
| Media resolution | A resolver for real note images. Fixtures use hardcoded `/spike-media/` public URLs; there is no path from a screenshot in the ingestion pipeline to a widget |

Also in scope: roughly 38 `!important` CSS rules in `globals.css` lines 218 to 291 become dead, but the roughly 90 lines at 292 to 380 styling `.wmde-markdown` must be **re-scoped, not deleted**, because the chat renderer still needs them.

### 6.2 Only one full-line syntactic form renders

`[VERIFIED]` Of twelve image forms in the fidelity fixture, five rendered as widgets. Not rendered: inline-in-a-sentence, reference-style, link-wrapped, inside a list item, inside a blockquote. Nothing is lost from the file in any case, but a screenshot pasted into a list or a quote stays as raw text. Extending coverage is more decoration work, and inline images cannot use `block: true` at all.

### 6.3 The metadata encoding problem is unsolved

`[VERIFIED]` `ARCHITECTURE_V2.md` §2 gives every Item provenance, a trust taint, and OCR segments. Markdown's `![alt](src "title")` carries three fields. Encoding more means either HTML blocks or `remark-directive` syntax such as `:::screenshot{item-id=...}`. Directives are maintained and real, but non-CommonMark, so the files stop being portable to arbitrary markdown tools, which cuts directly against the stated reason for markdown on disk. **This is not answered by the spike and is a genuine open design question for Phase 3 and Phase 6 jointly.** Note that a tree editor does not solve it either; it has the same problem plus a serializer.

---

## 7. Corrections to the reasoning in §4 of the plan

Three of the sentences supporting the original decision were wrong or stale. The decision survives all three, but the record should be accurate.

1. `[VERIFIED]` **Obsidian on CM6 is first-party fact, not report.** The official developer docs state "Obsidian uses CodeMirror 6 (CM6) to power the Markdown editor," `obsidian.d.ts` imports `@codemirror/state` and `@codemirror/view` and exports `editorLivePreviewField` as a `StateField<boolean>`, and the sample plugin externalizes the whole CodeMirror package set. The 1.13.0 changelog of 2026-05-28 confirms it is still CodeMirror. The `[SECONDARY]` tag on that sentence was too weak.

2. `[VERIFIED]` **The TipTap and Lexical effort figures were vendor marketing, and one was misattributed.** Both trace to `eddyter.com`, a comparison published by a company selling a competing commercial editor. That page's own table says TipTap 2 to 4 weeks, Lexical 4 to 6 weeks, ProseMirror 2 to 3 months; the plan appears to have taken TipTap's number verbatim and attached ProseMirror's "months" to Lexical. The methodology is informal and measures the wrong scope: it covers a toolbar, slash commands and mobile UX, and excludes the markdown bridge entirely, which is the only cost driver that matters here. `[UNVERIFIED]` A defensible re-estimate is 6 to 10 weeks for TipTap to something trustworthy with a user's existing files, and 3 to 6 months for Lexical direct, for a different reason than the plan gives.

3. `[VERIFIED]` **"Choosing one means the document model stops being markdown" is out of date as written.** Tiptap shipped a first-party MIT `@tiptap/markdown` in October 2025 and Lexical merged an experimental `@lexical/mdast` on 2026-07-08. Markdown-on-disk with a tree in memory is now a supported configuration in both. The claim is still true in substance, restated correctly: the model stops being markdown **in memory**, and you pay a permanent conversion tax at every save. `@tiptap/markdown` currently has 18 open markdown issues including escaped block syntax losing its escape on serialize, so an untouched `\# not a heading` silently becomes a heading on the next load. Lexical's stable markdown package is worse and its documented defects were closed by pointing at the experimental package rather than fixing the stable one.

4. `[SECONDARY]` **The Obsidian precedent supports the technology, not a cheap schedule.** Obsidian is still shipping image-widget interaction changes in 1.13.0 and 1.13.2 (May and July 2026), has an open unresolved report of scroll jumps of hundreds to thousands of lines with `Viewport failed to stabilize` and `Measure loop restarted more than 5 times` in documents with embedded media, has never shipped in-place editing of embeds after five years of requests, and reverts an entire callout to raw markdown when the cursor enters it. Its live-preview layer is proprietary, undocumented and deliberately not exposed to plugins, and it runs **two** rendering pipelines rather than one, re-hosting reading-view DOM inside CM6 widgets. Choosing CM6 "like Obsidian" buys the text engine and none of the live-preview work.

---

## 8. What the editor work should watch out for

In rough order of how expensive it is to discover late.

1. **Own the caret at the widget boundary before anything else.** §4.1 is the real work. Build an explicit selection state for a widget line, decide what `from`, `to`, click, paste and drop each mean, and write the tests first. Everything else in this list is a bug; this one is a design.
2. **Record image dimensions at capture time.** The residual risk is entirely the cold cache, which is the common case for a screenshot product. Origami already owns the ingestion pipeline, so width and height can be recorded when the screenshot is stored and read back as `estimatedHeight` on first paint, instead of being discovered at paint time. This converts the single unmitigated failure mode into a solved one, and no other project in the survey had this option.
3. **Reserve the box and supply `estimatedHeight`. Both. Always.** Neither alone works. Use padding on an inner element, never vertical margin.
4. **Pin the exact `@codemirror/view` patch version and test it.** The content drawing engine that hosts widgets was rewritten starting 2025-11-14 and shipped in 6.39.0; 6.43.3, .4, .6 and .7 in June and July 2026 are all still fixing tile-tree corruption and widget-update bugs.
5. **Never dispatch from inside `ViewPlugin.update()`.** One violation deactivates the plugin permanently and silently, and the spike shipped exactly that bug.
6. **Never provide block decorations from a `ViewPlugin`.** It throws and kills the editor constructor. The same guard catches any inline replace decoration spanning a line break, so multi-line figures and fenced blocks are affected too.
7. **`WidgetType.ignoreEvent` defaults to true** and is checked before any handler runs, so `EditorView.domEventHandlers` never fires on a widget. Clicking an image is inert until this is overridden.
8. **Fix line endings and the reconcile path in the same change.** Set `EditorState.lineSeparator`, open with `newline=""` in the backend, and stop cycling the history compartment for anything short of a real note switch. Both are small and both are silent data loss today.
9. **Decide the remote-image policy before ingest gets richer.** Local-only by default is the posture the product's own pitch implies.
10. **Budget the chat renderer into the same workstream** or the bundle regresses by 154KB gzip instead of shrinking.
11. **Write a renderer test suite as part of Phase 6, not after.** There is none today, and a round-trip corpus harness over real user files is the highest-value test in this entire project.

---

## 9. The condition that would reverse this

One question, and it is not tree versus text.

**Do the media blocks need to be editable in place, meaning resize, caption, re-crop, re-run OCR, drag to reorder? Or merely rendered?**

`[VERIFIED]` If rendered, the decision stands as written and this document closes the question. CodeMirror plus block widgets is proven, fast, byte-exact, and cheaper than what it replaces.

`[UNVERIFIED]` If editable, the tree model earns its cost, because a media block that is a real document node with attributes, selection, drag and undo integration is what TipTap's atom nodes and Lexical's `DecoratorNode` are for, and reimplementing that over a text model is the §4.1 problem multiplied by every interaction. In that case the shortest credible path is **Milkdown**, not TipTap direct: it is ProseMirror plus remark with markdown-as-source-of-truth already solved and `remark-directive` available for the §6.3 metadata problem. The price is a dependency on a project with 2,458 commits from essentially one maintainer, on a desktop app expected to last years. Building that bridge in-house is not a 2-to-4-week job; Milkdown took five years and 1.3MB of TypeScript, and MDXEditor took three and a half years and 739KB, both single-maintainer.

The current product brief says rendered. Nothing in the spike argues for changing that, and one thing argues against: `[SECONDARY]` ProseMirror has no built-in virtualization, and that was the stated reason the atomic-editor author chose CodeMirror after hitting lag on long documents synced from multiple sources. That is exactly Origami's ingestion model.

---

## 10. Artifacts

| Thing | Where |
|---|---|
| Spike commit | `74461e5` on `claude/spike-codemirror` |
| Block widget implementation | `desktop/renderer/src/components/editor/cm6/image-block.ts` |
| Editor component | `desktop/renderer/src/components/editor/cm6/cm6-markdown-editor.tsx` |
| Dev route | `desktop/renderer/src/pages/spike-cm6.tsx`, reachable at `#/spike/cm6`, DEV-gated in `app.tsx` |
| Fixtures | `desktop/renderer/public/spike-media/`, 8 PNGs, 89,029 bytes |

The spike is a dev route and is not on any production path. It should be **deleted, not promoted**, when Phase 6 starts. Its value is the measurements in this document and the four CodeMirror behaviours documented in its commit message, none of which appear in the official documentation.
