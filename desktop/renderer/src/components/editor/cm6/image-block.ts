import { syntaxTree } from "@codemirror/language";
import {
  RangeSetBuilder,
  StateEffect,
  StateField,
  type EditorState,
  type Extension,
} from "@codemirror/state";
import {
  Decoration,
  EditorView,
  ViewPlugin,
  WidgetType,
  type DecorationSet,
  type ViewUpdate,
} from "@codemirror/view";

/**
 * Block-level image widgets for a CodeMirror 6 markdown document.
 *
 * The document is plain markdown and stays plain markdown. A line that
 * contains nothing but `![alt](src)` is covered by a block replace
 * decoration that draws the image instead; when the selection touches that
 * line the decoration is dropped and the raw source reappears. Nothing is
 * ever written back into the document by this extension.
 *
 * Two constraints from the CM6 architecture shape everything here:
 *
 *  1. Block decorations must come from a StateField, never a ViewPlugin
 *     (`RangeError: Block decorations may not be specified via plugins`).
 *     A StateField cannot see the viewport, so the scan covers the whole
 *     document on every relevant transaction.
 *  2. `estimatedHeight` is consulted only for content the editor has not
 *     drawn yet. Once a widget is on screen its real bounding rect wins,
 *     and an <img> that has not decoded measures near zero. Stabilising
 *     scrolling therefore needs the box reserved before decode as well.
 */

export interface StabilityConfig {
  /** Report a cached rendered height for widgets the editor has not drawn. */
  estimatedHeight: boolean;
  /** Set intrinsic width/height on the <img> so the box exists before decode. */
  reserveBox: boolean;
  /** Force a measure cycle when an image finishes loading. */
  requestMeasureOnLoad: boolean;
  /** Deliberately apply vertical margins, to demonstrate the height-map desync. */
  marginProbe: boolean;
}

export const DEFAULT_STABILITY: StabilityConfig = {
  estimatedHeight: true,
  reserveBox: true,
  requestMeasureOnLoad: true,
  marginProbe: false,
};

export const setStability = StateEffect.define<StabilityConfig>();

/** Content width, bridged in from a ViewPlugin because a StateField cannot see geometry. */
const setContentWidth = StateEffect.define<number>();

// -- Widget lifecycle instrumentation --------------------------------------

export interface WidgetStats {
  toDOM: number;
  destroy: number;
  updateDOM: number;
  /** updateDOM calls handed a DOM node built for a different image. */
  updateDOMCrossWired: number;
  eq: number;
  imagesLoaded: number;
  requestMeasureCalls: number;
}

const stats: WidgetStats = {
  toDOM: 0,
  destroy: 0,
  updateDOM: 0,
  updateDOMCrossWired: 0,
  eq: 0,
  imagesLoaded: 0,
  requestMeasureCalls: 0,
};

export function getWidgetStats(): WidgetStats {
  return { ...stats };
}

export function resetWidgetStats(): void {
  for (const key of Object.keys(stats) as Array<keyof WidgetStats>) {
    stats[key] = 0;
  }
}

// -- Dimension cache -------------------------------------------------------

interface NaturalSize {
  width: number;
  height: number;
}

const DIMENSION_CACHE_KEY = "origami.spike.cm6.dimensions";
const dimensionCache = new Map<string, NaturalSize>();

function loadDimensionCache(): void {
  try {
    const raw = window.localStorage.getItem(DIMENSION_CACHE_KEY);
    if (!raw) return;
    for (const [src, size] of Object.entries(JSON.parse(raw) as Record<string, NaturalSize>)) {
      dimensionCache.set(src, size);
    }
  } catch (err) {
    console.warn("[cm6-spike] dimension cache unreadable", err);
  }
}

function persistDimensionCache(): void {
  try {
    window.localStorage.setItem(
      DIMENSION_CACHE_KEY,
      JSON.stringify(Object.fromEntries(dimensionCache)),
    );
  } catch (err) {
    console.warn("[cm6-spike] dimension cache unwritable", err);
  }
}

export function clearDimensionCache(): void {
  dimensionCache.clear();
  try {
    window.localStorage.removeItem(DIMENSION_CACHE_KEY);
  } catch {
    // A cleared cache that fails to persist is still cleared in memory.
  }
}

export function dimensionCacheSize(): number {
  return dimensionCache.size;
}

loadDimensionCache();

/** Vertical chrome the widget adds around the image, in px. Padding, never margin. */
const WIDGET_PADDING = 12;

function renderedHeight(src: string, contentWidth: number): number {
  const natural = dimensionCache.get(src);
  if (!natural || contentWidth <= 0) return 0;
  const scale = Math.min(1, contentWidth / natural.width);
  return Math.round(natural.height * scale) + WIDGET_PADDING * 2;
}

// -- Widget ----------------------------------------------------------------

export interface ImageSpec {
  src: string;
  alt: string;
}

class ImageBlockWidget extends WidgetType {
  constructor(
    readonly spec: ImageSpec,
    readonly contentWidth: number,
    readonly config: StabilityConfig,
  ) {
    super();
  }

  eq(other: ImageBlockWidget): boolean {
    stats.eq += 1;
    return (
      other.spec.src === this.spec.src &&
      other.spec.alt === this.spec.alt &&
      other.contentWidth === this.contentWidth &&
      other.config === this.config
    );
  }

  get estimatedHeight(): number {
    if (!this.config.estimatedHeight) return -1;
    const height = renderedHeight(this.spec.src, this.contentWidth);
    return height > 0 ? height : -1;
  }

  toDOM(view: EditorView): HTMLElement {
    stats.toDOM += 1;
    const wrap = document.createElement("div");
    wrap.className = "cm6-image-block";
    if (this.config.marginProbe) {
      wrap.classList.add("cm6-image-block--margin-probe");
    }
    const inner = document.createElement("div");
    inner.className = "cm6-image-block__inner";
    const img = document.createElement("img");
    img.className = "cm6-image-block__img";
    inner.appendChild(img);
    wrap.appendChild(inner);
    this.paint(img, view);
    return wrap;
  }

  updateDOM(dom: HTMLElement, view: EditorView, prev: ImageBlockWidget): boolean {
    stats.updateDOM += 1;
    if (prev.spec.src !== this.spec.src) {
      // The reuse cache is bucketed by widget class, not by document
      // position, so CodeMirror will hand this method a node that was built
      // for an unrelated image. Every content-bearing attribute must be
      // rewritten unconditionally or the wrong picture is displayed.
      stats.updateDOMCrossWired += 1;
    }
    const img = dom.querySelector<HTMLImageElement>(".cm6-image-block__img");
    if (!img) return false;
    dom.classList.toggle("cm6-image-block--margin-probe", this.config.marginProbe);
    this.paint(img, view);
    return true;
  }

  destroy(): void {
    stats.destroy += 1;
  }

  /**
   * `WidgetType.ignoreEvent` returns true by default, and `eventBelongsToEditor`
   * uses that to reject the event before any handler runs. Left at the default,
   * an `EditorView.domEventHandlers` mousedown handler never fires for a click
   * on the image and the widget is inert. Only mousedown needs to get through.
   */
  ignoreEvent(event: Event): boolean {
    return event.type !== "mousedown";
  }

  /** Keeps coordinate queries inside the widget from falling back to its whole rect. */
  coordsAt(dom: HTMLElement): { left: number; right: number; top: number; bottom: number } {
    const rect = dom.getBoundingClientRect();
    return { left: rect.left, right: rect.left, top: rect.top, bottom: rect.bottom };
  }

  private paint(img: HTMLImageElement, view: EditorView): void {
    const { src, alt } = this.spec;
    img.alt = alt;
    img.title = alt;

    const natural = dimensionCache.get(src);
    if (this.config.reserveBox && natural) {
      img.width = natural.width;
      img.height = natural.height;
    } else {
      img.removeAttribute("width");
      img.removeAttribute("height");
    }

    if (img.getAttribute("src") !== src) {
      img.setAttribute("src", src);
      img.onload = () => {
        stats.imagesLoaded += 1;
        const known = dimensionCache.get(src);
        if (!known || known.width !== img.naturalWidth) {
          dimensionCache.set(src, { width: img.naturalWidth, height: img.naturalHeight });
          persistDimensionCache();
        }
        if (this.config.requestMeasureOnLoad) {
          stats.requestMeasureCalls += 1;
          view.requestMeasure();
        }
      };
    }
  }
}

// -- Decoration building ---------------------------------------------------

/** A markdown Image node that is the only content on its line. */
interface BlockImage {
  from: number;
  to: number;
  spec: ImageSpec;
}

function findBlockImages(state: EditorState): BlockImage[] {
  const found: BlockImage[] = [];
  syntaxTree(state).iterate({
    enter(node) {
      if (node.name !== "Image") return;
      const line = state.doc.lineAt(node.from);
      if (line.number !== state.doc.lineAt(node.to).number) return;
      if (line.text.trim() !== state.doc.sliceString(node.from, node.to)) return;

      const url = node.node.getChild("URL");
      if (!url) return;
      const src = state.doc.sliceString(url.from, url.to);
      // `](` sits immediately before the URL, and `![` opens the node.
      const alt = state.doc.sliceString(node.from + 2, Math.max(node.from + 2, url.from - 2));
      found.push({ from: line.from, to: line.to, spec: { src, alt } });
    },
  });
  return found;
}

/**
 * Whether the source for [from, to] should be revealed.
 *
 * The overlap has to be strict. A collapsed caret sitting exactly on `from`
 * or `to` is the caret of the *neighbouring* line arriving at the boundary,
 * and treating that as "inside" is what makes a single forward-Delete from
 * the line above dismiss the widget and start eating the markdown one
 * character at a time. Requiring a strictly interior overlap keeps the
 * decoration, and therefore the atomic range, in place at the boundary.
 */
function selectionEnters(state: EditorState, from: number, to: number): boolean {
  for (const range of state.selection.ranges) {
    if (range.from < to && range.to > from) return true;
  }
  return false;
}

interface ImageBlockState {
  config: StabilityConfig;
  contentWidth: number;
  decorations: DecorationSet;
  /** Every block image in the document, revealed or not. Used by the harness. */
  blocks: BlockImage[];
}

function build(state: EditorState, config: StabilityConfig, contentWidth: number): ImageBlockState {
  const blocks = findBlockImages(state);
  const builder = new RangeSetBuilder<Decoration>();
  for (const block of blocks) {
    if (selectionEnters(state, block.from, block.to)) continue;
    builder.add(
      block.from,
      block.to,
      Decoration.replace({
        widget: new ImageBlockWidget(block.spec, contentWidth, config),
        block: true,
      }),
    );
  }
  return { config, contentWidth, decorations: builder.finish(), blocks };
}

export const imageBlockField = StateField.define<ImageBlockState>({
  create(state) {
    return build(state, DEFAULT_STABILITY, 0);
  },
  update(value, tr) {
    let config = value.config;
    let contentWidth = value.contentWidth;
    // The markdown parser is incremental and does not finish a large document
    // in one go: at 407KB only 58% of the tree exists when the editor first
    // paints. Rebuilding solely on doc and selection changes leaves every
    // image past the parse frontier undetected until some unrelated edit
    // happens, so the advancing tree has to be a trigger in its own right.
    let dirty =
      tr.docChanged ||
      tr.selection != null ||
      syntaxTree(tr.startState) !== syntaxTree(tr.state);

    for (const effect of tr.effects) {
      if (effect.is(setStability)) {
        config = effect.value;
        dirty = true;
      } else if (effect.is(setContentWidth) && effect.value !== contentWidth) {
        contentWidth = effect.value;
        dirty = true;
      }
    }

    if (!dirty) return value;
    return build(tr.state, config, contentWidth);
  },
  provide: (field) => EditorView.decorations.from(field, (value) => value.decorations),
});

/**
 * Bridges the viewport-only content width back into the state field.
 *
 * `estimatedHeight` has no access to the view, so the width the widget needs
 * in order to predict its own rendered height has to arrive through a
 * transaction. This is the standard ViewPlugin-to-StateField bridge.
 */
const contentWidthBridge = ViewPlugin.fromClass(
  class {
    constructor(view: EditorView) {
      queueMicrotask(() => this.sync(view));
    }

    update(update: ViewUpdate) {
      if (update.geometryChanged) this.sync(update.view);
    }

    sync(view: EditorView) {
      const width = view.contentDOM.clientWidth;
      if (width > 0 && width !== view.state.field(imageBlockField).contentWidth) {
        view.dispatch({ effects: setContentWidth.of(width) });
      }
    }
  },
);

/**
 * Clicking a rendered image puts the caret inside its source line, which
 * reveals it. The caret goes to `from + 1` rather than `from` because a caret
 * exactly on the boundary no longer counts as being inside the range.
 */
const revealOnClick = EditorView.domEventHandlers({
  mousedown(event, view) {
    const target = event.target as HTMLElement | null;
    const wrap = target?.closest?.(".cm6-image-block");
    if (!wrap) return false;
    const pos = view.posAtDOM(wrap);
    const line = view.state.doc.lineAt(pos);
    view.dispatch({ selection: { anchor: Math.min(line.from + 1, line.to) } });
    view.focus();
    event.preventDefault();
    return true;
  },
});

const imageBlockTheme = EditorView.theme({
  // Vertical margins on a block widget permanently desync the height map.
  // All spacing lives in padding on an inner element instead.
  ".cm6-image-block": {
    padding: `${WIDGET_PADDING}px 0`,
    display: "block",
  },
  ".cm6-image-block--margin-probe": {
    margin: "40px 0",
  },
  ".cm6-image-block__inner": {
    display: "block",
    borderRadius: "6px",
    overflow: "hidden",
    border: "1px solid var(--cm6-spike-border, rgba(127,127,127,0.35))",
  },
  ".cm6-image-block__img": {
    display: "block",
    maxWidth: "100%",
    height: "auto",
  },
});

export function imageBlocks(): Extension {
  return [
    imageBlockField,
    contentWidthBridge,
    revealOnClick,
    imageBlockTheme,
    // Makes a rendered image delete and traverse as one unit rather than as
    // hidden characters. Only the collapsed ranges are atomic, so a revealed
    // line still edits normally.
    EditorView.atomicRanges.of((view) => view.state.field(imageBlockField).decorations),
  ];
}

export function blockImagesIn(state: EditorState): BlockImage[] {
  return state.field(imageBlockField).blocks;
}
