import { useCallback, useEffect, useRef, useState } from "react";

import { forceParsing, syntaxTree } from "@codemirror/language";
import type { EditorView } from "@codemirror/view";

import Cm6MarkdownEditor from "@/components/editor/cm6/cm6-markdown-editor";
import { buildFixture, buildLargeFixture } from "@/components/editor/cm6/fixture";
import {
  DEFAULT_STABILITY,
  blockImagesIn,
  clearDimensionCache,
  dimensionCacheSize,
  getWidgetStats,
  resetWidgetStats,
  setStability,
  type StabilityConfig,
} from "@/components/editor/cm6/image-block";
import { createNote, fetchNote, fetchNotes, updateNote } from "@/lib/api/notes";

const SPIKE_NOTE_TITLE = "CM6 spike scratch note";
const SPIKE_NOTE_ID_KEY = "origami.spike.cm6.noteId";
// The backend derives a note's title from its first `# ` heading, so once the
// fixture is loaded the spike note no longer answers to SPIKE_NOTE_TITLE.
// Both names have to be recognised or every launch creates another scratch file.
const SPIKE_NOTE_TITLES = [SPIKE_NOTE_TITLE, "CodeMirror 6 mixed-media spike", "Large document rebuild cost"];

type BackendState = "unknown" | "connected" | "offline";

interface SpikeHandle {
  view: EditorView | null;
  doc: () => string;
  stats: typeof getWidgetStats;
  resetStats: typeof resetWidgetStats;
  setStability: (config: Partial<StabilityConfig>) => void;
  stability: () => StabilityConfig;
  clearDimensionCache: () => void;
  dimensionCacheSize: () => number;
  blockImageCount: () => number;
  widgetsInDOM: () => number;
  /** How far the incremental parser has reached, against the document length. */
  parseFrontier: () => { treeLength: number; docLength: number };
  forceFullParse: (timeoutMs?: number) => boolean;
  loadFixture: (images: number, paragraphsPerImage?: number) => void;
  loadLargeFixture: (lines: number, imageEvery: number) => void;
  save: () => Promise<{ id: string; title: string } | null>;
  noteId: () => string | null;
  backend: () => BackendState;
}

declare global {
  interface Window {
    __cm6spike?: SpikeHandle;
  }
}

export default function SpikeCm6Page() {
  const [content, setContent] = useState(() => buildFixture(6));
  const [title, setTitle] = useState("CM6 spike scratch note");
  const [noteId, setNoteId] = useState<string | null>(null);
  const [backend, setBackend] = useState<BackendState>("unknown");
  const [savedAt, setSavedAt] = useState<string>("never");
  const [stability, setStabilityState] = useState<StabilityConfig>(DEFAULT_STABILITY);

  const viewRef = useRef<EditorView | null>(null);
  const contentRef = useRef(content);
  contentRef.current = content;
  const noteIdRef = useRef<string | null>(null);
  noteIdRef.current = noteId;

  // Bind (or create) a real note file so the disk stays the source of truth.
  useEffect(() => {
    let cancelled = false;
    async function bind() {
      try {
        const notes = await fetchNotes();
        if (cancelled) return;
        const remembered = window.localStorage.getItem(SPIKE_NOTE_ID_KEY);
        const existing =
          notes.find((n) => n.id === remembered) ??
          notes.find((n) => SPIKE_NOTE_TITLES.includes(n.title));
        if (existing) {
          const full = await fetchNote(existing.id);
          if (cancelled) return;
          setNoteId(existing.id);
          setTitle(existing.title);
          setContent(full.content);
          window.localStorage.setItem(SPIKE_NOTE_ID_KEY, existing.id);
        } else {
          const created = await createNote(SPIKE_NOTE_TITLE);
          if (cancelled) return;
          setNoteId(created.id);
          window.localStorage.setItem(SPIKE_NOTE_ID_KEY, created.id);
          await updateNote(created.id, contentRef.current);
        }
        setBackend("connected");
      } catch {
        if (!cancelled) setBackend("offline");
      }
    }
    bind();
    return () => {
      cancelled = true;
    };
  }, []);

  const save = useCallback(async () => {
    const id = noteIdRef.current;
    if (!id) return null;
    const result = await updateNote(id, contentRef.current);
    setSavedAt(new Date().toISOString());
    return result;
  }, []);

  const applyStability = useCallback((patch: Partial<StabilityConfig>) => {
    setStabilityState((prev) => {
      const next = { ...prev, ...patch };
      viewRef.current?.dispatch({ effects: setStability.of(next) });
      return next;
    });
  }, []);

  const handleViewReady = useCallback(
    (view: EditorView | null) => {
      viewRef.current = view;
      if (view) view.dispatch({ effects: setStability.of(stability) });
    },
    [stability],
  );

  // The measurement harness drives the editor entirely through this handle.
  useEffect(() => {
    const handle: SpikeHandle = {
      get view() {
        return viewRef.current;
      },
      doc: () => viewRef.current?.state.doc.toString() ?? "",
      stats: getWidgetStats,
      resetStats: resetWidgetStats,
      setStability: applyStability,
      stability: () => stability,
      clearDimensionCache,
      dimensionCacheSize,
      blockImageCount: () => {
        const view = viewRef.current;
        return view ? blockImagesIn(view.state).length : 0;
      },
      widgetsInDOM: () => document.querySelectorAll(".cm6-image-block").length,
      parseFrontier: () => {
        const view = viewRef.current;
        if (!view) return { treeLength: 0, docLength: 0 };
        return {
          treeLength: syntaxTree(view.state).length,
          docLength: view.state.doc.length,
        };
      },
      forceFullParse: (timeoutMs = 5000) => {
        const view = viewRef.current;
        if (!view) return false;
        return forceParsing(view, view.state.doc.length, timeoutMs);
      },
      loadFixture: (images, paragraphsPerImage = 3) =>
        setContent(buildFixture(images, paragraphsPerImage)),
      loadLargeFixture: (lines, imageEvery) => setContent(buildLargeFixture(lines, imageEvery)),
      save,
      noteId: () => noteIdRef.current,
      backend: () => backend,
    };
    window.__cm6spike = handle;
    return () => {
      delete window.__cm6spike;
    };
  }, [applyStability, backend, save, stability]);

  const toggle = (key: keyof StabilityConfig) => (
    <label key={key} className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <input
        type="checkbox"
        checked={stability[key]}
        onChange={(e) => applyStability({ [key]: e.target.checked })}
      />
      {key}
    </label>
  );

  return (
    <div className="h-screen flex flex-col bg-background text-foreground">
      <div className="flex flex-wrap items-center gap-3 px-3 py-2 border-b border-border text-xs shrink-0">
        <span className="font-semibold">CM6 spike</span>
        <span className="text-muted-foreground">
          backend: {backend} · note: {noteId ?? "none"} · saved: {savedAt}
        </span>
        {(Object.keys(DEFAULT_STABILITY) as Array<keyof StabilityConfig>).map(toggle)}
        <button
          type="button"
          className="px-2 py-0.5 border border-border rounded"
          onClick={() => setContent(buildFixture(6))}
        >
          fixture 6
        </button>
        <button
          type="button"
          className="px-2 py-0.5 border border-border rounded"
          onClick={() => setContent(buildFixture(20))}
        >
          fixture 20
        </button>
        <button
          type="button"
          className="px-2 py-0.5 border border-border rounded"
          onClick={() => void save()}
        >
          save to disk
        </button>
        <a href="#/" className="ml-auto underline text-muted-foreground">
          back to app
        </a>
      </div>
      <div className="flex-1 min-h-0">
        <Cm6MarkdownEditor
          value={content}
          onChange={setContent}
          title={title}
          onTitleChange={setTitle}
          onViewReady={handleViewReady}
        />
      </div>
    </div>
  );
}
