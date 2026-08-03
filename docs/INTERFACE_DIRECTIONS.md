# Interface directions

Written 2026-08-03. Three directions for the desktop interface, the evidence behind them, and a recommendation.

This is a plan. No application code was changed to produce it. Every number below that is tagged `[VERIFIED]` was measured on this machine today, against this repository's own dependency tree, with the method stated inline so it can be re-run and disagreed with.

The interface has to serve [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md): everything you encountered, held locally, organised by how it arrived, with a briefing on top. It does not have to serve the current three-pane layout, which was built for a different product.

The brief from the user is three sentences long and all three are load-bearing. The current interface is "too text-heavy". They want to explore "semi-glassmorphism and neumorphism with minimal animations". And the hard priority is "clean but most importantly fast and smooth". Speed is the requirement; the aesthetic has to fit inside it.

### State of play, reconciled 2026-08-03

Work landed on `main` while this was being written, in commit `006f078`, and the document has been reconciled against it rather than left to describe a repository that no longer exists. `[VERIFIED]` by reading the tree:

- `backend/routes/library.py` is merged. The measurements in this document that cite it as being on a branch now refer to `main`.
- `desktop/renderer/src/components/library/library-view.tsx` exists, with a facet rail and a `/library` route. It is **not virtualised**: line 178 maps over the whole `items` array, and the filter runs client-side over the full corpus. It shows no images.
- A dev-only `/design` route skins that view four ways, plain, paper, frosted and soft, guarded the same way as the CodeMirror spike so it does not ship.

That is most of stage 1 already built, which is good news for the build order in section 7 and changes nothing in sections 1 to 6. Two notes on the skins. `frosted` already confines blur to the rail and header and bans it behind the list, which is the same rule section 2.1 arrives at independently. `soft` puts neumorphic shadow pairs on tiles, which is the one thing sections 2.2 and 5 both rule out, and the reason is in 2.2: the pair is the tile's only boundary cue and the canonical version of it measures 1.40:1 against a 3:1 requirement.

---

## 1. What is actually true today

### 1.1 The renderer is one chunk and half of it is a syntax highlighter

`[VERIFIED]` The committed build output `desktop/dist/renderer/assets/index-CDwumJTO.js` is **2,034,938 bytes**, a single chunk, alongside 134,685 bytes of CSS and roughly 1.4 MB of KaTeX font files. There is no code splitting except the dev-only CodeMirror spike, which is stripped from production by the `import.meta.env.DEV` guard in `app.tsx`.

`[VERIFIED]` Per-package cost, measured with the esbuild already present in `desktop/node_modules` (version 0.28.1), bundling each import against the repository's own `node_modules`, minified, ESM, `NODE_ENV=production`. Each row is the whole bundle for that import as esbuild resolves it, including whatever React it drags in, so the rows are not additive and the `react` plus `react-dom` row is there for scale rather than as a subtrahend:

| Package | Minified KiB |
|---|---:|
| `@uiw/react-md-editor` | 1069 |
| `@uiw/react-markdown-preview` | 993 |
| `ai` + `@ai-sdk/react` | 592 |
| CodeMirror 6 (view, state, lang-markdown) | 457 |
| `katex` + `rehype-katex` + `remark-math` | 296 |
| `react` + `react-dom` | 189 |
| `motion/react` | 134 |
| `react-dropzone` | 69 |
| `react-resizable-panels` | 41 |
| `radix-ui` (ScrollArea + Separator) | 35 |
| `cva` + `clsx` + `tailwind-merge` | 27 |
| `lucide-react`, 13 icons | 13 |

These sum higher than the shipped chunk because they overlap; the shipped 1.94 MiB is after Rollup deduplicates and tree-shakes. The ranking is what matters, and the ranking is unambiguous.

`[VERIFIED]` Breaking `@uiw/react-markdown-preview` down by package, from the esbuild metafile:

| Inside the markdown renderer | Minified KiB | Share |
|---|---:|---:|
| `refractor` | 582 | 58% |
| `parse5` | 123 | 12% |
| `entities` | 51 | 5% |
| everything else | 237 | 24% |

`refractor` is Prism's full grammar set. `parse5` is a complete HTML5 parser. Neither is optional through configuration: `node_modules/@uiw/react-markdown-preview/esm/index.js` hardcodes `rehypeRaw` and `rehypePrism` into its plugin array at lines 15 and 19, ahead of any `rehypePlugins` the caller passes. `[VERIFIED]` by reading the file.

So roughly **705 KiB of the 1.94 MiB renderer, about 35 percent, is syntax-highlighting grammars for languages the app never shows and an HTML parser used to render raw HTML embedded in ingested markdown.** That second one deserves a note: the CSP in `vite.config.ts` blocks remote `img-src` and `connect-src`, so the exfiltration channel that comment was written to close is already closed. Raw HTML passthrough is therefore a fidelity and surface-area question rather than a proven hole, but it is surface area that buys nothing.

`[VERIFIED]` Measured replacements. These are net of the react and react-dom baseline of 188.7 KiB, and so is the comparison figure: measured the same way, `@uiw/react-markdown-preview` is 986.

| Alternative | Minified KiB, net |
|---|---:|
| `react-markdown` + `remark-gfm` | 153 |
| `markdown-it` + `dompurify` | 139 |
| `marked` + `dompurify` | 69 |
| `marked` alone | 41 |

This finding is independent of which direction is chosen. It is the cheapest large win available and it should be taken regardless.

### 1.2 The corpus is images, and images are the whole cost

`[VERIFIED]` per PRODUCT_DIRECTION's own measurement against the real store: about 50 KB of index per record, so ten thousand screenshots is roughly 1.5 GB of index against roughly 8 GB of originals. The images outweigh the index about ten to one.

`[VERIFIED]` measured today, in headful Chrome at 1440x900 with `devicePixelRatio` 2 on Apple Silicon, images served over loopback, using `HTMLImageElement.decode()`:

| Set | Count | Decode ms | Decoded bitmap MB |
|---|---:|---:|---:|
| 320px WebP thumbnails | 24 | 20 | 6 |
| 2880x1800 PNG originals | 24 | **355** | **475** |
| 320px WebP thumbnails | 60 | 31 | 15 |
| 2880x1800 PNG originals | 60 | **753** | **1187** |

One viewport of a grid, twenty-four tiles, costs **355 ms of decode and 475 MB of decoded bitmap** if it loads originals, against **20 ms and 6 MB** if it loads 320px thumbnails. That is eighteen times the decode time and seventy-nine times the memory, and the memory figure is what kills the process rather than the frame rate. Decoded bitmap size is `width * height * 4` regardless of how well the file compressed, so this ratio does not improve with a better image format on the source side.

This is the single most important number in the document. A grid that loads originals does not stutter, it runs the renderer out of memory.

### 1.3 The DOM is not the bottleneck people assume

`[VERIFIED]` measured today, `innerHTML` of plain sized `div`s with no images, no shadows and no event handlers, same window:

| Nodes | Mount ms |
|---:|---:|
| 200 | 7 |
| 1,000 | 4 |
| 5,000 | 24 |
| 10,000 | 47 |
| 30,000 | 144 |

Ten thousand trivial nodes mount in 47 ms. This is a **floor**, not the real cost: it excludes React element creation and reconciliation, per-row event handlers, images, shadows and the memory those hold for the lifetime of the view. It is stated here so the virtualisation argument is made for the right reason. Virtualisation is needed because of memory, image decode and React reconciliation, not because the browser cannot append ten thousand elements.

### 1.4 The blur tax did not show up on this hardware

`[VERIFIED]` measured today: 400 rows of 6 cells, 2400 elements, programmatic scroll at 14 px per frame for 2.5 seconds after a warm-up pass, 1440x900 at `devicePixelRatio` 2, headful Chrome on Apple Silicon. Frame intervals recorded with `requestAnimationFrame`.

| Configuration | mean ms | p50 | p95 | max |
|---|---:|---:|---:|---:|
| no effects | 16.67 | 16.7 | 16.8 | 16.8 |
| one small shadow per cell | 16.67 | 16.7 | 16.8 | 16.8 |
| neumorphic shadow pair per cell | 16.67 | 16.7 | 16.8 | 16.8 |
| blurred 56px header only | 16.67 | 16.7 | 16.8 | 16.8 |
| blurred header plus shadow pair | 16.67 | 16.7 | 16.8 | 16.8 |
| **full-viewport `backdrop-filter: blur(16px)` over the scrolling list** | 16.67 | 16.7 | 16.8 | 16.8 |
| full-viewport blur plus shadow pair | 16.67 | 16.7 | 16.8 | 16.8 |

Not one dropped frame in any configuration, including the one this document was expected to condemn. The honest reading is that **an M-series Mac has enough compositing headroom that the blur tax is invisible at this scale**, and any claim that glassmorphism will make this app stutter on the developer's own machine is not supported by measurement.

Three caveats keep this from being a licence:

`[UNVERIFIED]` The measurement pinned at vsync in every configuration, which means it measured whether the budget was exceeded, not how much of the budget was consumed. A configuration using 4 ms of a 16.7 ms frame and one using 14 ms both read as 16.67. An attempt to recover the margin from a Chromium trace failed: the categories captured are renderer-main-thread events and raster happens in the GPU process, so the totals came back at fractions of a millisecond and moved in the wrong direction between configurations. That instrument does not measure the thing. The margin is therefore unmeasured, and the way to settle it is a GPU-process trace or a run on the oldest Intel Mac the project intends to support.

`[VERIFIED]` The W3C Filter Effects Level 2 draft is explicit that the Backdrop Root concept exists specifically to bound this cost, because relaxing it "would double the required rendering time, and would potentially require twice the memory usage and GPU bandwidth", and that each level of nesting doubles the required repaint cycles again. The cost model is real even where the headroom hides it.

`[VERIFIED]` Chromium's own Skia build config defines `SK_AVOID_SLOW_RASTER_PIPELINE_BLURS` by default, a workaround introduced after a blur performance regression in the 2024 Skia refactor. Blur cost has regressed inside Chromium within the last two years and can regress again.

The conclusion is not "blur is free". It is that **blur is not the constraint this app will hit, and designing around it while shipping a grid that decodes 475 MB of originals per viewport would be optimising the wrong layer.**

---

## 2. The two idioms the brief asks for

### 2.1 Glassmorphism: yes, on small fixed surfaces, with a stated rule

The rule is about what the compositor has to re-sample, not about taste.

`backdrop-filter` makes the element sample a Backdrop Root Image: everything painted between the nearest backdrop root and the element, flattened, then clipped to the element's border box, then blurred. Two properties follow. The cost scales with the **area** of the blurred element, because that is how many output pixels need a blur kernel run. And it scales with how often the backdrop **invalidates**, because a scrolling backdrop invalidates every frame while a static one does not.

That gives a rule that can be checked in review rather than argued about:

**Permitted.** A surface that is small, fixed in the layout, and whose blur is not animated. The 48px title bar. A floating command bar. A popover, menu or tooltip. A modal scrim, which is large but appears over a backdrop that is not scrolling underneath it. The launch site already does exactly this on its 64px fixed header and turns the blur off entirely at scroll top, in an unlayered rule with a comment explaining why, which is the correct instinct.

**Banned.** Any blurred surface that spans the content area while a list scrolls behind it. Any blurred surface inside a virtualised row, cell or tile, because the count is unbounded and each one is its own backdrop root. Any blur on an element that is itself animating. Nested blur, at any depth, because the spec says each level doubles the repaint cycles.

**Already violating this.** `database-viewer.tsx` lines 200 and 346 put `backdrop-blur-sm` on a `sticky` table header over a scrolling `tbody`. That is the exact banned case: a blurred surface whose backdrop invalidates every frame of every scroll. It did not show up in the benchmark, and it should still be replaced with an opaque `bg-muted` because it costs a real repaint for an effect nobody can see behind a solid `95%` background anyway.

One further constraint, from the CSP and from experience: the blurred surface must be legible if the blur never renders. `backdrop-filter` is a progressive enhancement. Every glass surface needs a background colour opaque enough to carry its own text on its own, with the blur adding depth rather than contrast.

### 2.2 Neumorphism: no, and the argument is arithmetic

`[VERIFIED]` by independent recomputation using the WCAG relative-luminance formula: the canonical neumorphic recipe, a `#bec3c9` shadow edge on an `#e0e5ec` surface, has a contrast ratio of **1.40:1**.

`[VERIFIED]` WCAG 2.2 Success Criterion 1.4.11, Non-text Contrast, Level AA, requires 3:1 for "visual information required to identify user interface components and states". The Understanding document narrows this usefully: a control does not need a visible boundary, but "when a boundary is the only way to identify a control's presence, it must meet the 3:1 contrast requirement".

That is precisely and only the neumorphic case. The entire idiom is a control that has no border, no fill difference and no background difference, whose sole existence cue is a soft shadow pair. The canonical recipe is short of the requirement by more than a factor of two, and it cannot be tuned into compliance, because raising the shadow contrast to 3:1 is the same operation as making it stop looking soft. The style and the criterion are in direct opposition by construction.

`[SECONDARY]` Contemporary design writing has converged on the same verdict for data-dense interfaces specifically, with one 2026 survey recommending neumorphism be reserved for "closed, low-stakes, hardware-flavored surfaces" and explicitly ruled out for dense tables and text-heavy pages, and reporting its share of design-tool output falling from 0.69% to 0.41% between January and May 2026. Vendor-reported analytics, so treat the numbers as directional and the verdict as consensus rather than proof.

There is also a second problem specific to this app. Neumorphism requires the surface and its background to be the same colour, which is what makes the shadow pair read as extrusion. Origami has **three** themes, light, dark and palenight, and the app is going to hold user images. A shadow pair tuned to look extruded on `oklch(1 0 0)` will not on `oklch(0.28 0.006 265)`, and neither survives sitting next to a screenshot with its own bright background. Three themes times every surface is three times the tuning work for an effect that fails an accessibility criterion in all three.

**The verdict.** Neumorphism is rejected as an idiom. The user asked for it, and this is the honest no the brief invited.

**What survives, and it is not nothing.** The part of neumorphism worth keeping is its *restraint*: no hard borders everywhere, surfaces that read as raised or recessed rather than outlined, and a palette with almost no contrast between panel and page. That is achievable with a single soft shadow plus a hairline, where the hairline carries the 3:1 and the shadow carries the feel. The one narrow permission: a pressed or selected state may use an inset soft shadow **in addition to** a colour and, where it exists, a label change, never instead of them. If the shadow is removed and the state is still unambiguous, the shadow is decoration and is allowed. If removing it makes the state ambiguous, it is the boundary cue and it is banned.

### 2.3 macOS native vibrancy: do not, and here is the specific reason

This was deliberately skipped in Phase 2 packaging as unverified. It should now be closed as a decision rather than left open.

`[VERIFIED]` from the installed `electron@43.2.0` type definitions in `desktop/node_modules/electron/electron.d.ts`: `vibrancy` is `@platform darwin` and accepts fifteen values including `sidebar`, `under-window`, `header`, `content` and `hud`; `visualEffectState` exists and must be used with it; `setVibrancy()` accepts an `animationDuration`. **`backgroundMaterial` is `@platform win32`** and accepts `auto`, `none`, `mica`, `acrylic`, `tabbed`. So `backgroundMaterial` is not a cross-platform route to the same feel; it is the Windows Mica and Acrylic API and has no macOS code path.

`[VERIFIED]` Electron's own documentation is stale on the value list. PR #27125 changed the wording on `light`, `dark`, `medium-light` and `ultra-dark` from "will be removed" to "are deprecated and have been removed in macOS Catalina". `appearance-based` still appears in the constructor options doc, and in the type definition above, despite Apple having no live `NSVisualEffectMaterial` case for it.

Four findings, together, close this:

**Vibrancy and CSS `backdrop-filter` do not coexist.** `[VERIFIED]` The bug where `backdrop-filter` renders incorrectly on a vibrant window has recurred across five Electron eras: issue #19765 on Electron 6 in 2019, an Electron 16 era report, #39529 on Electron 25 in 2023, and #44720 on Electron 34 in November 2024 against macOS 15.2 beta. #44720 was closed **"not planned"**. This is not a bug awaiting a fix, it is a durable incompatibility between AppKit's `NSVisualEffectView` compositing and Chromium's own. Choosing vibrancy therefore means giving up CSS blur everywhere in the app, which is the opposite of what the brief asks for.

**Vibrancy requires a transparent window, and transparency costs.** `[VERIFIED]` Electron PR #31493 made vibrant windows force a transparent background after issue #31461 found vibrancy rendering as a white box without `transparent: true`. `[VERIFIED]` Electron's own documentation states that "the native window shadow will not be shown on a transparent window". `[SECONDARY]` Electron issue #6344 documents the loss of subpixel text antialiasing on transparent surfaces, with the reporter's mechanism unconfirmed by a maintainer. Subpixel antialiasing requires a known opaque final background, which a transparent window does not have. For an app whose whole job is holding and showing text, degrading text rendering to gain a background effect is a bad trade.

**It has a confirmed live defect.** `[VERIFIED]` Electron issue #46164, filed March 2025 against Electron 35.0.2 and labelled `status/confirmed`: vibrancy is lost entirely, not merely dimmed, when the window becomes inactive, unlike Safari which keeps the material visible. An effect that vanishes every time the user clicks another app is not a foundation to design a visual identity on.

**Its blast radius reaches outside the app.** `[SECONDARY]`, converging across three independent reports: on macOS 26 Tahoe, Electron's override of the private AppKit method `_cornerMask` on vibrant views is believed to have broken WindowServer's shadow memoisation, causing system-wide GPU spikes whenever a vibrant Electron window was visible. It affected Slack, Discord, VS Code, Figma and others, and was fixed by removing the override in Electron 36.9.2, 37.6.0 and 38.2.0. `[VERIFIED]` The tracking issue is electron/electron#48311, filed September 2025. This project is on Electron 43.2.0 and therefore has the fix, so this is not a live risk. It is cited as evidence about the class of risk: native vibrancy couples the app to private AppKit behaviour, and when that coupling breaks, it degrades the whole machine rather than one window.

**And the premise is unproven.** `[UNVERIFIED]` No controlled comparison of Electron vibrancy against CSS `backdrop-filter` on the same scene and hardware appears to exist. `[SECONDARY]` The closest real data is Mozilla's own profiling of Firefox vibrancy, which found WindowServer spending 18.8% of its time in `gl_composite_inactive_backdrops` with vibrancy enabled, and per-composite time rising from 1.96 ms to 2.32 ms. That is nine-year-old data on Yosemite hardware, and its direction is informative rather than transferable: vibrancy is a measurable line item paid by WindowServer, not free work that happens somewhere nobody is billed for.

**The verdict.** Do not enable `vibrancy`. Keep the window opaque, keep `backgroundColor` set, and get the translucency from a small number of CSS blurred surfaces governed by section 2.1. The one thing worth taking from the native route is the *palette*: sampling what `NSVisualEffectMaterial` sidebar and header actually produce, and hard-coding those values as theme tokens, gets the macOS-native feel with none of the coupling.

---

## 3. What actually makes it fast

This is part of the design, not an implementation note appended to it. Two of the three directions below are only viable because of this section.

### 3.1 Virtualisation

Any list that grows with the corpus is virtualised. That is the library grid, the facet result list, the segment list inside an item, and the chat message list. It is not the facet rail, which is bounded by the number of source types, or the theme menu.

`[VERIFIED]` measured cost of the candidates, minified, isolated from a react baseline:

| Virtualiser | Version | Minified KiB | Installed MB |
|---|---|---:|---:|
| `react-window` | 2.3.0 | 12.2 | 0.23 |
| `virtua` | 0.50.0 | 12.4 | 1.5 |
| `@tanstack/react-virtual` | 3.14.9 | 23.7 | 0.54 |

**Take `@tanstack/react-virtual`.** The 11 KiB it costs over `react-window` is noise against the 700 KiB section 1.1 removes, it is the ecosystem default by a wide margin, and a grid is expressed as two `useVirtualizer` instances, one per axis, which is exactly the composability a variable-aspect-ratio tile grid needs. `react-window` v2 is current and healthy, and its own documentation says dynamic row heights are "not as efficient as predetermined sizes", which is the case a screenshot grid is made of. `virtua` is pre-1.0.

The measurement in section 1.3 says why: not because ten thousand nodes cannot be appended, but because ten thousand React rows means ten thousand element objects, ten thousand sets of handlers, and, fatally, up to ten thousand image elements holding decoded bitmaps.

### 3.2 Thumbnails, not originals

This is not optional in any of the three directions.

**What generates them.** `[VERIFIED]` Pillow 12.3.0 is already in `backend/uv.lock` as a transitive dependency of `fastembed` 0.8.0, which lists `pillow` in its dependency block. It is therefore already inside the bundled Python runtime and adding thumbnail generation costs **no new dependency and no change to the 718 MB install size.**

`[VERIFIED]` measured with that Pillow, on a 2880x1800 source, single-threaded on this machine:

| Output | LANCZOS resize plus encode |
|---|---:|
| 160px WebP q80 | 19.8 ms |
| **320px WebP q80** | **24.9 ms** |
| 320px JPEG q78 | 21.7 ms |
| 640px WebP q80 | 41.9 ms |

**Where they live.** Beside the original, not in the index. `Item.raw_ref` already points at the original rather than inlining it, which is what makes this clean: add a sibling `thumb_ref` under a `thumbnails/` directory in `ORIGAMI_DATA_DIR`, generated once at ingest and regenerable from `raw_ref` at any time. Nothing in Chroma changes, so this is not a schema migration.

This also lands exactly where PRODUCT_DIRECTION's retention section already points. "A thumbnail plus the extracted text can outlive the source file without breaking a citation" is stated there as the pruning strategy; the thumbnail it depends on does not exist yet. Building it for the interface builds it for retention too.

**Why 320px.** A grid tile at 220 CSS pixels on a `devicePixelRatio` 2 display wants 440 device pixels. 320px is deliberately below that: the tile is a recognition aid, not a reading surface, and a slightly soft thumbnail is the correct trade against decode time and memory. Section 1.2 measured what the alternative costs.

**Serving them.** `screenshotUrl()` in `lib/api/screenshots.ts` already builds a loopback URL and `withToken()` appends the per-launch auth token as a query parameter, which the CSP's `img-src 'self' data: blob: http://127.0.0.1:*` permits. A `GET /api/items/{id}/thumb` endpoint follows the same shape. The token in the query string is already the established pattern for browser-loaded URLs and is not made worse by this.

**One rule for the grid.** Every `<img>` gets `loading="lazy"` and `decoding="async"`, and every tile has a fixed intrinsic size from the item metadata so the grid never reflows when an image lands. Originals load only in the single-item view, one at a time.

### 3.3 Not re-rendering, and what belongs in React

The current renderer has three habits that will not survive a corpus.

**Polling that replaces whole arrays.** `workspace-layout.tsx` refetches the entire notes list every 5 seconds and `setNotes` on the result; `chroma-document-list.tsx` refetches every 3 to 10 seconds. Each poll replaces every element identity, so every row re-renders whether or not anything changed, forever, in the background. At a hundred notes this is invisible. At ten thousand items it is a re-render storm on a timer. The fix is not a library: compare and set only on change, and key rows by a stable id so React can bail out.

**Everything in one component's state.** `workspace-layout.tsx` holds `editorContent` in state and passes a debounced copy to the chat panel, so every keystroke re-renders the layout, both panels and the pull tab. The chat panel already works around this with module-level refs and a comment about the React compiler, which is a symptom rather than a solution.

**The state that should be in React** is: which route is active, which item is selected, which facets are on, and what the user has typed. That is a handful of scalars and a small set.

**The state that should not be** is: the corpus itself. Ten thousand item records are data the view reads, not state the view owns. They belong in a module-level store the components subscribe to with `useSyncExternalStore`, holding a compact projection rather than the full record. `[VERIFIED]` The `/library` endpoint on branch `claude/faceted-library` documents its own cost in a docstring: roughly 1.9 KB of metadata per segment, so ten thousand screenshots at three segments each moves **about 57 MB per call**, and it returns items and facets unpaged in one response. That endpoint is the right shape for a small corpus and is the first thing to page for a large one. The client should hold `{id, title, source_type, modality, created_at, thumb_ref}` per item, which is on the order of 150 bytes, and fetch the rest on selection.

**Motion.** `[VERIFIED]` There is not one occurrence of `prefers-reduced-motion`, `useReducedMotion` or `MotionConfig` anywhere in `desktop/renderer/src`. The requirement is currently unmet in the app, while the launch site honours it carefully. That is a one-block fix in `globals.css` and should be made in stage zero regardless of direction:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
    scroll-behavior: auto !important;
  }
}
```

Note `1ms` rather than `0s`: it preserves `transitionend` and `animationend` events, so nothing that waits on one hangs.

**The rule the launch site paid for.** `[VERIFIED]` There are **ten** occurrences of `initial={{ opacity: 0 }}` in the renderer. That is the exact shape that shipped the launch site blank: an element whose visible state is only reachable if JavaScript runs to completion. The renderer is a client-only bundle, so a failed hydration is not the failure mode here, but a `motion` component that never receives its `animate` because of an error in a sibling, or an `AnimatePresence` that never resolves an exit, produces the same invisible content. **Content is visible by default. Motion may add to a visible element and may remove it, but must never be the only thing that reveals it.** Where an entrance is genuinely wanted, use a CSS `@keyframes` with `animation-fill-mode: both` starting from a visible-by-default rule, exactly as the site's `.rise` does.

### 3.4 The single chunk

Every direction below should improve it, and the arithmetic is direction-independent:

| Change | Estimated KiB |
|---|---:|
| Replace `@uiw/react-markdown-preview` with `react-markdown` + `remark-gfm` in the chat path | about -830 |
| Route-split the markdown editor so it is not in the entry chunk | about -80 further |
| Add `@tanstack/react-virtual` | +24 |

The KaTeX fonts, roughly 1.4 MB on disk, do not move in either step, because the chat path renders maths and imports `katex/dist/katex.min.css` directly. They are not in the JavaScript chunk and they are fetched from disk over `file://`, so their cost is disk footprint rather than parse time. Making them lazy is a separate question and not urgent.

`[UNVERIFIED]` The estimate is derived from isolated measurements, and isolated measurements overlap in a real build. The number that settles it is `npm run build:renderer` followed by reading the byte count, which takes about a minute. Treat "roughly 1.94 MiB down to roughly 1.1 MiB" as the hypothesis to test, not a result.

The markdown swap has one behaviour change worth naming: fenced code blocks lose syntax colouring. In a knowledge-base app whose corpus is screenshots, PDFs and articles, that is a fair trade for 582 KiB. If a language or two is genuinely wanted later, `refractor` supports registering individual grammars, at roughly 2 to 5 KiB each rather than all 290.

---

## 4. Library survey

Measured today, not recalled. Registry versions read from npm, bundle costs measured with esbuild against a clean install in a scratch directory, isolated from a react and react-dom baseline.

One provenance note, because the distinction matters. Every version number and every byte count in this section was produced here, on this machine. The repository health figures, commit distribution, issue counts and the shadcn changelog quote, came from a research pass that fetched the npm registry API, the GitHub REST API and the vendors' own changelogs directly. Those are `[VERIFIED]` under this folder's definition, checked against a primary source, but they were not re-fetched by hand afterwards.

The realistic set is seven components an app like this actually needs: dialog, menu, tooltip, tabs, select or combobox, scroll area, switch. The barrel column is the worst case if tree-shaking fails, which is the number most public comparisons quote and which nobody actually ships.

| Library | Version | 7 components, KiB | Barrel, KiB | Installed MB | Tailwind 4 |
|---|---|---:|---:|---:|---|
| `radix-ui` | 1.6.7 | **144.5** | 252 | 5.5 | no conflict, ships no CSS |
| `react-aria-components` | 1.20.0 | 195.7 | 1040 | 11 | plugin, not v4-confirmed |
| `@mantine/core` | 9.5.1 | 218.4 + 273 KB CSS | 589 | 20 | **documented conflict** |
| `@ark-ui/react` | 5.38.0 | 220.5 | 1015 | 29 with `@zag-js` | no conflict |
| `@base-ui/react` | 1.6.0 | 233.6 | 484 | 19 | no conflict |

**shadcn/ui is already partly here, and it moved.** `[VERIFIED]` `globals.css` imports `shadcn/tailwind.css`, `shadcn` 3.8.5 is a devDependency, and `components/ui/` contains generated `button`, `input`, `resizable`, `scroll-area`, `separator`, `textarea` and `tag-color-picker`. The CLI is now at **4.16.1**. `[VERIFIED]` shadcn switched its **default primitive engine from Radix to Base UI in July 2026**, and explicitly did not deprecate Radix: "Radix is a mature, tested library. We still run it in production today and we're not migrating." Migration tooling exists in both directions. shadcn is not a fifth option next to the libraries above; it is a generator that emits source against one of them.

**Radix, and the real risk.** `[VERIFIED]` The registry shows `radix-ui` 1.6.7 as current with the packument last modified 2026-07-31, so release cadence is fine. The concern is depth: of commits to `radix-ui/primitives` since 2026-05-01, one WorkOS engineer authored 191 of about 215, roughly **89 percent**. That is a genuine bus-factor problem and it is the strongest argument for moving.

**Base UI.** `[VERIFIED]` 1.0.0 shipped 2025-12-11; current is 1.6.0. The package name moved from `@base-ui-components/react` to `@base-ui/react`, so older imports and tutorials point at a stale package. Contributor spread is materially healthier than Radix, with the top contributor at roughly 35 to 40 percent rather than 89. `[UNVERIFIED]` Its accessibility claim is marketing on its own site; no published test methodology was found.

**Mantine.** `[VERIFIED]` The Tailwind 4 conflict is real and documented in two live threads, `mantinedev/mantine#823` and a `tailwindlabs/tailwindcss` v4 discussion, with the reported symptom being components rendering invisible until hover because Tailwind's Preflight wins on cascade-layer order. The fix requires hand-sequencing `@layer theme, base, mantine, components, utilities;` and importing `styles.layer.css` into the right layer. A third-party package exists solely to paper over this. `[VERIFIED]` Its 273 KB of CSS is not per-component tree-shakeable in the standard setup, on top of the app's existing 134 KB. It has the best maintenance profile of the five by every count, and it is still the wrong choice here, because adopting it means running two styling systems.

**React Aria Components.** `[VERIFIED]` Its styling story is the most technically rigorous of the set: state exposed as `data-` attributes rather than CSS pseudo-classes, so mouse, touch and keyboard stay visually consistent, plus render-prop `className` functions and an official Tailwind plugin. `[SECONDARY]` Adobe's accessibility rigour is long-standing, cross-referenced consensus rather than something audited here. It is the right answer for a team whose hardest constraint is accessibility, and it is a different idiom from what is already in `components/ui/`.

**Ark UI.** `[VERIFIED]` 68 `@zag-js` dependencies and 29 MB installed. Its framework-agnostic Zag.js architecture is real and cannot be cashed in by a React-only Electron app.

### Recommendation: adopt nothing except a virtualiser. Stay on Radix.

The reasoning, in order of weight:

1. **Radix measured cheapest for the realistic set**, 144.5 KiB against Base UI's 233.6 for the same seven components. The barrel numbers that public comparisons quote invert this ranking and are not what anyone ships.
2. **It is already installed and already generating the `components/ui/` surface.** A migration buys zero user-visible change, and this document is asking for a considerable amount of interface work already.
3. **The exposure is bounded by shadcn's own model.** The primitives are consumed through copied source in `components/ui/`, so a Radix problem is a per-component problem with a migration path shadcn maintains in both directions, not a rewrite.
4. The honest counter-argument is the 89 percent bus factor, and it is a real one. The mitigation is a **calendar item, not a migration**: re-check `radix-ui/primitives` commit distribution when React 20 ships or when a Radix component blocks something, whichever is first, and move that component to Base UI if the answer has got worse. Base UI is the destination if it comes to that, because shadcn now defaults there.

The only addition is `@tanstack/react-virtual`, at 23.7 KiB.

Two upgrades are due independent of any of this: `radix-ui` 1.4.3 to 1.6.7, and `shadcn` 3.8.5 to 4.16.1.

---

## 5. Three directions

Each takes a different position on how a source-type-faceted corpus plus a briefing should be navigated. They are not three skins.

### Direction A: The Contact Sheet

**The organising idea.** The window is the corpus, laid out as a virtualised grid of thumbnails you scan with your eyes, and text is what you fall back to when looking is not enough. It suits someone whose corpus is mostly things they saw: screenshots, photos, PDF first pages, article hero images.

**The layout.**

The window is one surface, not three panes. A 48px title bar strip at the top, already built and already the drag handle. Below it, edge to edge, the grid.

Down the left, a 200px facet rail. Not a file tree; a list of the source types with live counts, straight from the `facets` block the `/library` endpoint already returns, so a rail reads something like `screenshot 8,412`, `pdf 203`, `note 71`, `snippet 340`, `photo 1,109`. Those five figures are illustrative, not measured; the real ones are unknown until stage 1 renders them, and section 8 says what they would decide. Below them, modality counts, then a trust filter, because "did a human write this or did a model guess it" is the axis nothing else in this category offers. Clicking narrows the grid. The rail is bounded by the number of source types, so it is never virtualised and never expensive.

The grid itself is uniform-width tiles with variable height from each item's stored aspect ratio, in four to eight columns depending on window width, two `useVirtualizer` instances. Each tile is a thumbnail with a two-line caption underneath: the title, and a small monospace line reading source type and date. Items with no image, notes and snippets, get a tile of the same size showing their first three lines as text on the paper ground, so the grid stays a grid rather than degrading into a mixed list.

**The briefing lives in the grid, not on a route.** The first row of the grid, above everything else and scrolling away with it, is a single full-width card: this week's brief. Three or four sentences and a row of the items it cites, each a smaller version of the same tile. It is not a page you navigate to, it is the top of the corpus. `/digest` stops being a destination.

**A single item** opens as an overlay inspector over a dimmed grid, not a route change: the original image or document on the left at full size, and on the right its segments listed by modality, its provenance, and the citations that point at it. Escape closes it. Left and right arrows move to the neighbouring tile without closing, so a run of screenshots can be triaged in seconds.

**Chat is summoned, not resident.** Cmd+K raises a floating bar over the grid. Typing filters the grid live as a search. Pressing Enter turns the same text into a question, and the answer opens as a panel anchored to the bottom of the window with its citations as tiles you can click into the inspector. Nothing is a permanent pane.

**The visual treatment.**

Paper ground from the launch site's palette, so the app and the site are recognisably one thing: `--color-paper #faf8f2`, ink `#211c16`, vermilion `#bc3f1d` for the one accent. Dark and palenight get equivalent grounds derived the same way. Tiles are opaque, with a hairline and one small shadow, `0 1px 2px rgba(33,28,22,.06)`, which is the launch site's `--shadow-card` first stop.

Blur appears in exactly three places, all of them fixed and small: the 48px title bar, the Cmd+K command bar, and the scrim behind the item inspector. Blur is banned inside a tile, banned on the facet rail, and banned on anything that scrolls.

Soft shadow appears on the command bar and the inspector, both of which are single elements at any moment. It is banned on tiles, because there are up to ten thousand of them, and section 2.2 bans it as a boundary cue everywhere.

The grid is where the "considered rather than a wall of prose" feeling comes from, and it comes from the layout rather than from an effect.

**What it costs.**

Bundle: the best of the three. The editor leaves the entry chunk entirely. The KaTeX fonts do not go with it, because `animated-text.tsx` imports `katex/dist/katex.min.css` for the chat path and answers contain maths; that 1.4 MB of fonts leaves only if maths rendering itself becomes lazy, which is a separate decision. Adds only the virtualiser.

Render: the most demanding, and the most bounded once the work in section 3 is done. The failure mode is loud and obvious, which is a virtue: if thumbnails are missing, the grid dies immediately at 475 MB per viewport rather than degrading quietly.

Complexity: the two-axis virtualiser with variable heights is the single hardest piece of front-end work in this document. Budget for the scroll-restoration and resize cases, which are where grid virtualisers actually go wrong.

**The strongest honest argument against it.**

It bets the interface on thumbnails existing, and today not a single one does. Until the thumbnail pipeline is written and every existing item is backfilled, this direction has nothing to show. It also flatters a corpus of screenshots and quietly punishes one of PDFs and notes, where a tile is a grey rectangle with a filename and the grid is worse than a list. If the user's real corpus turns out to be mostly documents, this is the wrong shape and the wrongness will not be obvious until the corpus is large.

### Direction B: The Briefing Spine

**The organising idea.** Time is the spine and source type is the colour: a single scrolling column where the briefing is not a summary of the corpus but its most recent entry, and scrolling down is scrolling backwards. It suits someone who wants the app to tell them what happened rather than being asked.

**The layout.**

One column, roughly 720px, centred, with generous margin. No panes at all. The window is a document.

At the top, today. Then a dated section per period, coarsening as you descend: this week by day, last month by week, last year by month. Each section opens with its brief, three or four sentences of prose, and below it a horizontal strip of the items that period holds, scrolled sideways within the section rather than wrapping. A section is therefore a fixed height regardless of whether it holds four items or four hundred, which is what lets the vertical column be virtualised cheaply: the outer virtualiser handles sections, and each strip virtualises itself horizontally only while it is on screen.

Source type is carried by colour and a small glyph on each item rather than by position, so a period reads at a glance as mostly screenshots, or as the week the PDFs arrived.

**Facets filter the spine rather than replacing it.** A control at the top toggles source types on and off. Turning off everything but `pdf` leaves the same timeline with the same dates, thinner. The structure never changes, which is the point: you always know where you are.

**A single item** expands inline, pushing the timeline down, rather than opening over it. Escape or clicking the header collapses it. There is no second surface, ever.

**Chat is the top of the column.** Above today, a permanently visible input. Asking a question inserts the answer as a new entry at the top of the spine, dated now, with its citations as items in a strip beneath it, exactly like every other entry. A conversation and a week are the same kind of object. This is the direction's cleverest move and also its biggest risk.

**The visual treatment.**

The most typographic of the three, and the one that leans hardest on the launch site's identity: Newsreader for the briefing prose, Instrument Sans for the interface, Fragment Mono for dates and counts. Both would need bundling under `@fontsource-variable` alongside the existing Inter and JetBrains Mono, because the CSP forbids CDN fonts.

Blur appears in one place: the date header that sticks to the top of the viewport as you scroll through a section. It is 40px tall, fixed, and it is the one place in this direction where a blurred surface has a scrolling backdrop. Section 2.1 bans that. The resolution is to make it opaque and accept that it looks like a header rather than glass, or to blur it and accept the one violation knowingly, having measured that on this hardware it costs nothing observable. **Recommend opaque**, because the rule is worth more than the effect.

Soft shadow appears nowhere. This direction gets its depth from typography and white space, which is the honest way to do it.

**What it costs.**

Bundle: good. Keeps the markdown renderer, because briefs are prose, so section 3.4's swap matters more here than anywhere. Drops the editor.

Render: the cheapest of the three by a distance. A section is a fixed-height box; the nested horizontal strips only mount while visible; there are never more than a few dozen images alive.

Complexity: the lowest. A vertical virtualiser over sections plus horizontal virtualisers within them is a well-understood pattern, and the visual system is mostly type.

**The strongest honest argument against it.**

It is the direction most likely to be beautiful and least likely to answer "where is that thing". Time is a poor index for retrieval: a corpus is searched by what something was, not by when it arrived, and "sometime in March" is exactly the memory people do not have. It also structurally contradicts PRODUCT_DIRECTION, which says organising by source type is "a genuinely different axis" and the reason this product is not Obsidian. This direction makes source type a colour and time the structure, which is the axis every note app already uses. Making the briefing the spine also makes the app useless before the corpus is interesting, since an empty timeline is an empty page.

### Direction C: The Ledger

**The organising idea.** The corpus is a table you drive from the keyboard, with a persistent inspector that always shows exactly one thing. It suits a power user with a large corpus who wants precision, and who is annoyed by anything that makes them reach for the mouse.

**The layout.**

Two panes, split about 40/60, with the divider draggable. `react-resizable-panels` is already installed and already does this.

The left pane is a dense virtualised list: one row per item, 32px tall, columns for a 24px thumbnail, title, source type, modality glyphs, date and segment count. It is sortable by any column and filterable by a query line at the top that accepts both free text and structured terms, `source:screenshot trust:untrusted before:2026-06`. Facet counts live inline in that query line's autocomplete rather than in a rail, so no horizontal space is spent on chrome.

The right pane is the inspector, and it never empties. It shows whichever row has focus, updating as you arrow through the list. For a screenshot: the image, the OCR segments, the caption, the provenance. For a PDF: the page, the chunk, its neighbours.

**The briefing is a row.** Each week's brief is an item in the list like any other, with `source_type` of `brief`, sorted into place by date and pinned to the top by default. Selecting it fills the inspector with the prose and makes its cited items selectable from within it. There is no separate surface and no separate route, which is the most economical answer to "where does the briefing go" of the three.

**Chat is a mode of the query line.** A prefix, or a modifier key on Enter, sends the text as a question instead of a filter. The answer renders in the inspector; its citations become the list's contents, so answering a question narrows the corpus to what the answer used. That is a genuinely useful behaviour that neither other direction gives you.

**The visual treatment.**

The quietest of the three. Hairlines, no shadows on rows, alternating row tint at about 2 percent, and the vermilion accent used only for the selected row's left edge and for the count that changes when a filter is applied.

Blur appears in one place: the query line's autocomplete popover. It is small, transient, and its backdrop is not scrolling while it is open.

Soft shadow appears nowhere in the list, ever. A 32px row repeated ten thousand times is the single worst place in any of these designs to put a blurred or shadowed surface, and the design does not put one there.

**What it costs.**

Bundle: the same as A. Editor leaves, virtualiser arrives.

Render: cheap in images, but only if a second thumbnail size is generated. Decoded bitmap size follows the source pixels, not the CSS box, so serving the grid's 320px thumbnail and displaying it at 24px costs the same 256 KB per image it costs in Direction A, and a thousand rows alive would be 256 MB. Generate a 64px tier as well and a row costs 16 KB, so a thousand is 16 MB. This is the same trap as section 1.2 at a smaller scale, and it is easier to miss here because the visible image is tiny. The cost is otherwise elsewhere: the inspector re-renders on every arrow key, so it must be the only thing that re-renders, which means the list rows cannot be re-created by a selection change. That is the constraint section 3.3 exists to satisfy.

Complexity: middling. A single-axis virtualised list is the easy case. The query language is the real work, and it is the kind of work that expands.

**The strongest honest argument against it.**

It is the most text-heavy interface of the three, and the user's actual complaint was that the interface is too text-heavy. A dense ledger is what "a wall of prose" looks like when it has been organised. It also drifts straight at the "programmable view layer" that PRODUCT_DIRECTION explicitly defers: a query language with structured terms is the first two thirds of the thing that document says the project stalls on if it starts early. And it is the direction that most rewards a user who already knows what they are looking for, which is the opposite of the case the corpus exists to serve.

---

## 6. Recommendation

**Direction A, the contact sheet.**

The reasoning, in order of weight:

**It answers the complaint that was actually made.** "Too text-heavy" is a complaint about the primary surface, and A is the only direction whose primary surface is not text. C makes it worse. B makes it prettier without making it less textual.

**It matches what the corpus is made of.** PRODUCT_DIRECTION's own retention arithmetic is entirely about screenshots and photos, because that is where both the volume and the cost sit. An interface whose primary object is an image is an interface shaped like the data.

**It is the only direction that makes the performance work non-optional.** This sounds like a drawback and is the opposite. In B and C the thumbnail pipeline is a nice-to-have that gets deferred, virtualisation is a nice-to-have that gets deferred, and the app degrades slowly and invisibly as the corpus grows until it is unpleasant and nobody can say when it happened. In A the grid does not work at all until both exist. Work that is load-bearing gets done.

**It is the direction that most decisively displaces the editor.** PRODUCT_DIRECTION says editor parity is "a race already lost", and the editor is currently the left 55 percent of the window. Its bundle weight is a smaller argument than it first looks: `@uiw/react-md-editor` measures 1069 KiB, but 993 of those are the markdown preview the chat path uses anyway, so route-splitting the editor saves about 80 KiB rather than a megabyte. The megabyte comes from section 3.4's plugin swap, which is available in every direction. The argument for A here is about attention, not bytes: it stops the app from being organised around a race it has already decided not to run.

**And its accent, structurally, is where the product's only defensible claim lives.** Source type as the rail, and trust as a filter within it, is the axis PRODUCT_DIRECTION says nothing else in this category has. A puts it on the left edge of every screen.

**What choosing A gives up, stated plainly.** B's insight that a briefing should be part of the corpus rather than a route is better than A's version of the same idea, and A should take it: the brief as the first card of the grid is directly borrowed from B and is why A has no `/digest` route. C's insight that answering a question should narrow the list to the citations is genuinely better than A's citation tiles, and is worth adopting into A's Cmd+K panel later. What is genuinely lost is C's keyboard precision at scale. A grid is a bad interface for "find the one PDF from March", and A's answer, Cmd+K as a filter, is weaker than a real query line. If the corpus turns out to be mostly documents rather than mostly screenshots, this recommendation should be revisited, and the signal that would trigger that is the facet counts in the rail: if `pdf` and `note` together exceed `screenshot` and `photo`, A is the wrong shape.

**On the two idioms the user asked for.** Semi-glassmorphism survives, in three places, governed by a rule that can be checked in review. Neumorphism does not survive, and section 2.2 is the argument. What the user is likely to actually want from neumorphism, surfaces that read as soft and raised rather than boxed and outlined, is delivered by the paper ground plus a hairline plus one small shadow, which passes 1.4.11 and costs one shadow instead of two.

---

## 7. Build order

Stage one is small enough to try in a day and reverts by deleting files.

**Stage 0, half a day, no direction committed, pure win.** Add the `prefers-reduced-motion` block to `globals.css`. Replace `@uiw/react-markdown-preview` with `react-markdown` plus `remark-gfm` in `components/chat/animated-text.tsx`, keeping `remark-math` and `rehype-katex`, which drops `rehype-raw` and `rehype-prism-plus` because `react-markdown` does not add them. Expect the `.chat-markdown .wmde-markdown` selectors in `globals.css` to need rewriting against the new class names, which is most of the work in this step. Run `npm run build:renderer` and write the new byte count into this document next to the estimate in section 3.4. Upgrade `radix-ui` and the `shadcn` CLI. Replace the two `backdrop-blur-sm` sticky table headers in `database-viewer.tsx` with opaque backgrounds. None of this depends on choosing a direction, and all of it is worth having if the direction is later rejected.

**Stage 1, mostly done already, half a day of remainder.** The endpoint, the route, the facet rail and the placeholder tiles all landed in `006f078`. What is left is the one thing that makes it survive a corpus: put `@tanstack/react-virtual` under the tile grid so `items.map` at line 178 of `library-view.tsx` stops mounting every record, and move the client-side filter off the render path. Reverting is still a small diff.

The purpose of stage 1 is to answer one question before any more is spent: **does the corpus, laid out this way, look like something worth navigating?** That question is now answerable today, against real data, by opening `/library`. The facet counts answer the "mostly screenshots or mostly documents" question at the same time, and section 6 says what each answer decides.

**Stage 2, thumbnails.** A `services/thumbnails.py` using the Pillow already in the lock file, 320px WebP at q80, written to `ORIGAMI_DATA_DIR/thumbnails/` beside the originals, generated at ingest and backfilled for existing items by a one-shot script. A `GET /api/items/{id}/thumb` endpoint. Then the grid shows real images. Measure the memory of a full-screen scroll before and after and record it, because section 1.2 is the claim this stage is built on and it should be confirmed against the real corpus rather than a synthetic one.

**Stage 3, the item inspector.** Overlay, not a route. Original on the left, segments by modality and provenance on the right, arrow keys to move between neighbours. This is where the trust and origin fields become visible to a human for the first time.

**Stage 4, the briefing card and Cmd+K.** The brief as the first row of the grid, and the command bar as filter-then-question. `/digest` retires. This is the first stage that introduces a blurred surface, and it introduces exactly two.

**Stage 5, retire the split editor as the default route.** Not delete: `/c/:id` keeps working, and the editor becomes a route reached from a note rather than the shape of the app. This is the point at which the entry chunk loses the editor. It does not lose the KaTeX fonts, which the chat path still needs.

Stages 0 and 1 are independent of everything else and together are the cheapest way to find out whether this plan is right.

---

## 8. What would change this document

Named so that a future reader can tell whether it has gone stale rather than guessing.

- **A build number.** Section 3.4's bundle estimate is `[UNVERIFIED]` arithmetic over isolated measurements. One `npm run build:renderer` after stage 0 replaces it with a fact.
- **A GPU-process trace, or a run on an Intel Mac.** Section 1.4 measured that nothing dropped a frame and could not measure how much headroom was left. If the project ever targets Intel or an external 4K display, the blur rules in 2.1 should be re-checked rather than assumed to carry over.
- **The facet counts from a real corpus.** If documents outweigh images, Direction A is the wrong shape and section 6 says so.
- **Radix's commit distribution.** Re-check when React 20 ships or when a Radix component blocks something. If one maintainer is still writing 89 percent of it, move the affected components to Base UI, which is now shadcn's default.
- **`/library` at scale.** Its own docstring says roughly 57 MB per call at ten thousand screenshots, unpaged. The first time a scroll feels slow, that endpoint is the first suspect, not the grid.
