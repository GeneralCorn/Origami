import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertCircle,
  ArrowLeft,
  FileText,
  Images,
  Loader2,
  Plus,
  X,
} from "lucide-react";

import { useNavigate } from "@/lib/router";
import { fetchCollections } from "@/lib/api/collections";
import { fetchLibrary, type LibraryItem } from "@/lib/api/library";
import {
  changeScreenshotCollection,
  fetchScreenshotStatus,
  fetchScreenshotText,
  screenshotUrl,
  uploadScreenshots,
} from "@/lib/api/screenshots";
import type { Collection, ScreenshotJob, ScreenshotStage, ScreenshotStatus } from "@/types";

const ACCEPT = {
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/webp": [".webp"],
  "image/gif": [".gif"],
  "image/heic": [".heic"],
  "image/heif": [".heif"],
};

const STAGE_LABEL: Record<ScreenshotStage, string> = {
  queued: "Queued",
  reading: "Reading text",
  classifying: "Classifying",
  indexing: "Indexing",
  captioning: "Captioning",
  done: "Done",
  error: "Failed",
};

const FINISHED: ReadonlySet<ScreenshotStage> = new Set(["done", "error"]);
const UNFILED = "__unfiled__";

function isScreenshot(item: LibraryItem): boolean {
  return item.source_type === "screenshot";
}

function whenLabel(item: LibraryItem): string {
  const stamp = item.created_at || item.ingested_at;
  const parsed = stamp ? new Date(stamp) : null;
  return parsed && !Number.isNaN(parsed.valueOf()) ? parsed.toLocaleDateString() : "";
}

export function CaptureView() {
  const navigate = useNavigate();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [status, setStatus] = useState<ScreenshotStatus | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [textPanel, setTextPanel] = useState<{ name: string; title: string; text: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const finishedRef = useRef<Set<string>>(new Set());

  const loadItems = useCallback(async () => {
    try {
      const library = await fetchLibrary();
      setItems(library.items.filter(isScreenshot));
    } catch {
      // Backend unavailable; keep what we have.
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const next = await fetchScreenshotStatus();
      setStatus(next);
      // A job that just finished changed the library; refresh once per finish.
      let changed = false;
      for (const job of next.jobs) {
        if (FINISHED.has(job.stage) && !finishedRef.current.has(job.filename)) {
          finishedRef.current.add(job.filename);
          changed = true;
        }
      }
      if (changed) {
        await loadItems();
      }
      return next;
    } catch {
      return null;
    }
  }, [loadItems]);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [cols] = await Promise.all([fetchCollections(), loadItems(), loadStatus()]);
        if (live) {
          setCollections(cols);
          // Jobs already finished before this page opened are not news.
          setStatus((current) => {
            for (const job of current?.jobs ?? []) {
              if (FINISHED.has(job.stage)) finishedRef.current.add(job.filename);
            }
            return current;
          });
        }
      } catch {
        // Collections unavailable; the page still shows items.
      } finally {
        if (live) setLoaded(true);
      }
    })();
    return () => {
      live = false;
    };
  }, [loadItems, loadStatus]);

  const inFlight = useMemo(
    () => (status?.jobs ?? []).filter((job) => !FINISHED.has(job.stage)),
    [status],
  );

  // Poll fast while the pipeline is working, slowly otherwise.
  useEffect(() => {
    const interval = inFlight.length > 0 ? 1_500 : 10_000;
    const id = setInterval(loadStatus, interval);
    return () => clearInterval(id);
  }, [inFlight.length, loadStatus]);

  const onDrop = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      setNotice(null);
      try {
        const uploaded = await uploadScreenshots(files);
        const duplicates = uploaded.filter((entry) => entry.duplicate).length;
        if (duplicates > 0) {
          setNotice(
            duplicates === uploaded.length
              ? `Already captured${duplicates > 1 ? ` (${duplicates})` : ""}`
              : `${duplicates} of ${uploaded.length} already captured`,
          );
        }
        await loadStatus();
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Upload failed");
      }
    },
    [loadStatus],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: ACCEPT,
    noClick: true,
    noKeyboard: true,
  });

  const byCollection = useMemo(() => {
    const groups = new Map<string, LibraryItem[]>();
    for (const item of items) {
      const key = item.collection || UNFILED;
      const list = groups.get(key) ?? [];
      list.push(item);
      groups.set(key, list);
    }
    for (const list of groups.values()) {
      list.sort((a, b) => (b.ingested_at || "").localeCompare(a.ingested_at || ""));
    }
    return groups;
  }, [items]);

  const orderedGroups = useMemo(() => {
    const order = collections.map((c) => c.id);
    const keys = [...byCollection.keys()].sort((a, b) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      return (ia === -1 ? order.length : ia) - (ib === -1 ? order.length : ib);
    });
    return keys
      .filter((key) => selected === null || key === selected)
      .map((key) => ({ key, items: byCollection.get(key) ?? [] }));
  }, [byCollection, collections, selected]);

  const nameOf = useCallback(
    (collectionId: string) => {
      if (collectionId === UNFILED) return "Unfiled";
      return collections.find((c) => c.id === collectionId)?.name ?? collectionId;
    },
    [collections],
  );

  const moveTo = useCallback(async (item: LibraryItem, collectionId: string) => {
    if (collectionId === item.collection) return;
    setItems((prev) => prev.map((it) => (it.file_id === item.file_id ? { ...it, collection: collectionId } : it)));
    try {
      await changeScreenshotCollection(item.file_id, collectionId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Move failed");
      await loadItems();
    }
  }, [loadItems]);

  const showText = useCallback(async (item: LibraryItem) => {
    try {
      const text = await fetchScreenshotText(item.file_id);
      setTextPanel({ name: item.file_id, title: item.title, text });
    } catch {
      setNotice("No text has been extracted for this screenshot yet");
    }
  }, []);

  const engines = status?.engines;
  const inboxCount = byCollection.get("inbox")?.length ?? 0;

  return (
    <div {...getRootProps({ className: "h-full flex flex-col relative outline-none" })}>
      <input {...getInputProps()} />

      {/* Header, also the window drag handle */}
      <div className="titlebar flex items-center justify-between h-12 border-b border-thin border-border shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Images className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">Screenshots</span>
          {inFlight.length > 0 && (
            <span className="flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-accent text-muted-foreground">
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
              {inFlight.length} processing
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={open}
            className="titlebar-interactive flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <Plus className="h-3 w-3" />
            <span>Add</span>
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="titlebar-interactive flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <ArrowLeft className="h-3 w-3" />
            <span>Back</span>
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Collections rail */}
        <aside className="w-56 shrink-0 overflow-y-auto border-r border-thin border-border p-4">
          <h2 className="text-[11px] tracking-wide uppercase text-muted-foreground/70">Collections</h2>
          <ul className="mt-2 space-y-0.5">
            <li>
              <RailButton on={selected === null} onClick={() => setSelected(null)} label="All" count={items.length} />
            </li>
            {collections.map((collection) => (
              <li key={collection.id}>
                <RailButton
                  on={selected === collection.id}
                  onClick={() => setSelected(collection.id)}
                  label={collection.name}
                  count={byCollection.get(collection.id)?.length ?? 0}
                  attention={collection.id === "inbox" && inboxCount > 0}
                />
              </li>
            ))}
            {byCollection.has(UNFILED) && (
              <li>
                <RailButton
                  on={selected === UNFILED}
                  onClick={() => setSelected(UNFILED)}
                  label="Unfiled"
                  count={byCollection.get(UNFILED)?.length ?? 0}
                />
              </li>
            )}
          </ul>

          {engines && (
            <dl className="mt-8 space-y-1 text-[11px] font-mono text-muted-foreground/70">
              <div className="flex justify-between gap-2">
                <dt>ocr</dt>
                <dd className="truncate">{engines.ocr ?? "vlm only"}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>vision</dt>
                <dd>{engines.vision ? "ollama ready" : "offline"}</dd>
              </div>
            </dl>
          )}
          {engines && !engines.ocr && !engines.vision && (
            <p className="mt-3 text-[11px] leading-relaxed text-amber-600 dark:text-amber-400">
              Nothing on this machine can read a screenshot yet. Install the ocr-fallback extra or start Ollama.
            </p>
          )}
        </aside>

        {/* Main */}
        <div className="relative min-w-0 flex-1 overflow-y-auto">
          <AnimatePresence>
            {isDragActive && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 z-30 flex items-center justify-center bg-background/85 backdrop-blur-sm pointer-events-none"
              >
                <div className="rounded-lg border border-dashed border-ring px-8 py-6 text-sm text-foreground">
                  Drop to read and file
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {notice && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="mx-6 mt-3 flex items-center gap-2 px-3 py-2 rounded-md bg-muted text-xs text-foreground border border-border"
              >
                <AlertCircle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                <span className="flex-1">{notice}</span>
                <button type="button" onClick={() => setNotice(null)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-3 w-3" />
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {inFlight.length > 0 && (
            <ul className="mx-6 mt-3 divide-y divide-border/60 rounded-md border border-border/60">
              {inFlight.map((job) => (
                <JobRow key={job.filename} job={job} nameOf={nameOf} />
              ))}
            </ul>
          )}

          {(status?.jobs ?? []).some((job) => job.stage === "error") && (
            <ul className="mx-6 mt-3 space-y-1">
              {(status?.jobs ?? [])
                .filter((job) => job.stage === "error")
                .map((job) => (
                  <li key={job.filename} className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-300">
                    <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                    <span className="min-w-0">
                      <span className="font-mono opacity-70">{job.filename.slice(0, 12)}</span> {job.error}
                    </span>
                  </li>
                ))}
            </ul>
          )}

          {!loaded ? (
            <div className="px-6 py-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-56 rounded-md bg-muted animate-pulse" />
              ))}
            </div>
          ) : items.length === 0 && inFlight.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
              <Images className="h-6 w-6 mb-3 opacity-40" />
              <p className="text-xs">Drop iPhone screenshots anywhere on this page.</p>
              <p className="mt-1 text-[11px] opacity-70">
                Text is read on-device and each one is filed into a collection note.
              </p>
            </div>
          ) : (
            <div className="px-6 py-5 space-y-8">
              {orderedGroups.map(({ key, items: group }) => (
                <section key={key}>
                  <div className="flex items-baseline gap-2 mb-2">
                    <h3 className="text-xs font-medium text-foreground">{nameOf(key)}</h3>
                    <span className="text-[10px] tabular-nums text-muted-foreground">{group.length}</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                    {group.map((item) => (
                      <ScreenshotCard
                        key={item.file_id}
                        item={item}
                        collections={collections}
                        onExpand={() => setExpanded(item.file_id)}
                        onMove={(collectionId) => moveTo(item, collectionId)}
                        onText={() => showText(item)}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>

        {/* Extracted text */}
        <AnimatePresence>
          {textPanel && (
            <motion.aside
              initial={{ x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="w-96 shrink-0 border-l border-thin border-border flex flex-col min-h-0"
            >
              <div className="flex items-center justify-between px-4 h-10 border-b border-thin border-border shrink-0">
                <span className="text-xs font-medium truncate">{textPanel.title}</span>
                <button type="button" onClick={() => setTextPanel(null)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <pre className="flex-1 overflow-y-auto px-4 py-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap text-foreground/90">
                {textPanel.text || "No text was read from this screenshot."}
              </pre>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      {/* Lightbox */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setExpanded(null)}
            className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-8 cursor-pointer"
          >
            <motion.img
              initial={{ scale: 0.95 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.95 }}
              src={screenshotUrl(expanded)}
              alt=""
              className="max-w-full max-h-full rounded-lg shadow-2xl object-contain"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function RailButton({
  on,
  onClick,
  label,
  count,
  attention = false,
}: {
  on: boolean;
  onClick: () => void;
  label: string;
  count: number;
  attention?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={`flex w-full items-baseline justify-between rounded px-2 py-1 text-left text-sm transition-colors ${
        on ? "bg-accent font-medium text-foreground" : "text-foreground/80 hover:bg-accent/50"
      }`}
    >
      <span className="truncate">{label}</span>
      <span
        className={`tabular-nums text-xs ${
          attention ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

function JobRow({ job, nameOf }: { job: ScreenshotJob; nameOf: (id: string) => string }) {
  return (
    <li className="flex items-center gap-3 px-3 py-2 text-xs">
      <img
        src={screenshotUrl(job.filename)}
        alt=""
        className="w-7 h-10 object-cover object-top rounded-sm bg-muted shrink-0"
        loading="lazy"
      />
      <div className="flex-1 min-w-0">
        <p className="truncate text-foreground">
          {job.title || <span className="font-mono text-muted-foreground">{job.filename.slice(0, 16)}</span>}
        </p>
        {job.collection && (
          <p className="text-[10px] text-muted-foreground truncate">{nameOf(job.collection)}</p>
        )}
      </div>
      <span className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground shrink-0">
        <Loader2 className="h-2.5 w-2.5 animate-spin" />
        {STAGE_LABEL[job.stage]}
      </span>
    </li>
  );
}

function ScreenshotCard({
  item,
  collections,
  onExpand,
  onMove,
  onText,
}: {
  item: LibraryItem;
  collections: Collection[];
  onExpand: () => void;
  onMove: (collectionId: string) => void;
  onText: () => void;
}) {
  const captioned = (item.modalities.caption ?? 0) > 0;
  const when = whenLabel(item);
  return (
    <article className="group rounded-md overflow-hidden bg-card border border-border/60 hover:border-border transition-colors">
      <button type="button" onClick={onExpand} className="block w-full h-44 bg-muted overflow-hidden">
        <img
          src={screenshotUrl(item.file_id)}
          alt={item.title}
          className="w-full h-full object-cover object-top group-hover:scale-[1.02] transition-transform duration-200"
          loading="lazy"
        />
      </button>
      <div className="p-2.5">
        <p className="text-xs font-medium text-foreground truncate" title={item.title}>
          {item.title}
        </p>
        <p className="mt-0.5 text-[10px] font-mono text-muted-foreground truncate">
          {[item.source_app, when, captioned ? "captioned" : null].filter(Boolean).join(" · ")}
        </p>
        <div className="mt-2 flex items-center gap-1.5">
          <select
            value={item.collection || ""}
            onChange={(event) => onMove(event.target.value)}
            className="flex-1 min-w-0 text-[11px] bg-transparent border border-border/70 rounded px-1.5 py-0.5 text-foreground outline-none focus:border-ring"
            aria-label="Collection"
          >
            {!item.collection && <option value="">Unfiled</option>}
            {collections.map((collection) => (
              <option key={collection.id} value={collection.id}>
                {collection.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={onText}
            title="Extracted text"
            className="shrink-0 p-1 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <FileText className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </article>
  );
}
