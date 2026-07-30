import { useEffect, useRef } from "react";

import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { Compartment, EditorState, Transaction } from "@codemirror/state";
import {
  EditorView,
  GutterMarker,
  drawSelection,
  highlightActiveLine,
  keymap,
  lineNumberWidgetMarker,
  lineNumbers,
  rectangularSelection,
} from "@codemirror/view";
import { tags } from "@lezer/highlight";

import { useTheme } from "@/lib/theme";

import { imageBlocks } from "./image-block";

interface Cm6MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  title: string;
  onTitleChange: (title: string) => void;
  /** Spike-only: hands the live view to the measurement harness. */
  onViewReady?: (view: EditorView | null) => void;
}

const highlight = HighlightStyle.define([
  { tag: tags.heading1, fontSize: "1.5em", fontWeight: "700" },
  { tag: tags.heading2, fontSize: "1.25em", fontWeight: "700" },
  { tag: tags.heading3, fontSize: "1.1em", fontWeight: "600" },
  { tag: tags.strong, fontWeight: "700" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.link, color: "var(--cm6-spike-link)" },
  { tag: tags.url, color: "var(--cm6-spike-link)", textDecoration: "underline" },
  { tag: tags.monospace, fontFamily: "var(--font-mono, ui-monospace, monospace)" },
  { tag: tags.processingInstruction, color: "var(--cm6-spike-syntax)" },
  { tag: tags.contentSeparator, color: "var(--cm6-spike-syntax)" },
  { tag: tags.quote, color: "var(--cm6-spike-syntax)", fontStyle: "italic" },
]);

const baseTheme = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "14px",
    color: "var(--foreground)",
    backgroundColor: "var(--background)",
  },
  ".cm-scroller": {
    fontFamily: "var(--font-sans, Inter Variable, system-ui, sans-serif)",
    lineHeight: "1.6",
    overflow: "auto",
  },
  ".cm-content": {
    maxWidth: "720px",
    margin: "0 auto",
    padding: "16px 24px 60vh 24px",
    caretColor: "var(--foreground)",
  },
  ".cm-gutters": {
    backgroundColor: "transparent",
    border: "none",
    color: "var(--muted-foreground)",
    opacity: "0.5",
  },
  ".cm-activeLine": { backgroundColor: "transparent" },
  "&.cm-focused .cm-activeLine": { backgroundColor: "var(--muted)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--foreground)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": {
    backgroundColor: "var(--accent)",
  },
});

/**
 * A full-line block replace removes that line from the line-number gutter,
 * because the gutter has no line left to attach a marker to. The remedy is a
 * widget marker; for `lineNumbers` specifically it arrives through the
 * `lineNumberWidgetMarker` facet rather than the gutter config object.
 */
class ImageGutterMarker extends GutterMarker {
  toDOM() {
    return document.createTextNode("▣");
  }
}

const imageGutter = [
  lineNumbers(),
  lineNumberWidgetMarker.of((_view, widget) =>
    (widget as unknown as { spec?: unknown }).spec ? new ImageGutterMarker() : null,
  ),
];

export default function Cm6MarkdownEditor({
  value,
  onChange,
  title,
  onTitleChange,
  onViewReady,
}: Cm6MarkdownEditorProps) {
  const { theme } = useTheme();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const historyRef = useRef(new Compartment());
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const view = new EditorView({
      state: EditorState.create({
        doc: value,
        extensions: [
          imageGutter,
          historyRef.current.of(history()),
          drawSelection(),
          rectangularSelection(),
          highlightActiveLine(),
          EditorState.allowMultipleSelections.of(true),
          EditorView.lineWrapping,
          markdown({ base: markdownLanguage }),
          syntaxHighlighting(highlight),
          imageBlocks(),
          keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              onChangeRef.current(update.state.doc.toString());
            }
          }),
          baseTheme,
        ],
      }),
      parent: host,
    });

    viewRef.current = view;
    onViewReady?.(view);

    return () => {
      onViewReady?.(null);
      viewRef.current = null;
      view.destroy();
    };
    // Mount once. External value changes are reconciled by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reconcile an externally driven value (note switch, AI append) without
  // echoing the editor's own edits back into itself.
  //
  // Keeping the replacement out of the history is necessary but not
  // sufficient. The history still holds inverted changes recorded against the
  // *previous* document; after a swap those get mapped forward and undo either
  // does nothing or re-applies old text at a mapped offset in the new note.
  // Cycling the history compartment discards that state along with the doc.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === value) return;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value },
      annotations: Transaction.addToHistory.of(false),
      effects: historyRef.current.reconfigure([]),
    });
    view.dispatch({ effects: historyRef.current.reconfigure(history()) });
  }, [value]);

  return (
    <div className="h-full flex flex-col" data-cm6-theme={theme}>
      <div className="flex items-center h-10 px-3 border-b border-thin border-border shrink-0">
        <input
          type="text"
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          placeholder="Untitled"
          className="w-full text-sm font-semibold text-foreground bg-transparent border-none outline-none placeholder:text-muted-foreground/40"
        />
      </div>
      <div ref={hostRef} className="flex-1 min-h-0 overflow-hidden" data-testid="cm6-host" />
    </div>
  );
}
