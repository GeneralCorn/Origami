import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "@/lib/router";
import { motion, AnimatePresence } from "motion/react";
import {
  ArrowLeft,
  Calendar,
  Upload,
  Loader2,
  Image as ImageIcon,
  AlertCircle,
  ChevronDown,
  X,
} from "lucide-react";
import {
  fetchDigests,
  fetchDigestContent,
  fetchPendingScreenshots,
  uploadScreenshots,
  processScreenshots,
  recategorize,
  screenshotUrl,
} from "@/lib/api/screenshots";
import { tagColor } from "@/lib/utils";
import type { DigestSummary, PendingScreenshot } from "@/types";

interface DigestEntry {
  title: string;
  source: string;
  description: string;
  screenshotFilename: string;
}

interface DigestSection {
  category: string;
  entries: DigestEntry[];
}

function parseDigestMarkdown(content: string): DigestSection[] {
  const sections: DigestSection[] = [];
  let currentSection: DigestSection | null = null;

  for (const line of content.split("\n")) {
    if (line.startsWith("## ")) {
      if (currentSection) sections.push(currentSection);
      currentSection = { category: line.slice(3).trim(), entries: [] };
      continue;
    }

    if (!currentSection) continue;

    if (line.startsWith("- **")) {
      // Parse: - **Title** (source) — description
      const titleMatch = line.match(/\*\*(.+?)\*\*/);
      const sourceMatch = line.match(/\*\* \((.+?)\)/);
      const descMatch = line.match(/— (.+)$/);
      currentSection.entries.push({
        title: titleMatch?.[1] ?? "Untitled",
        source: sourceMatch?.[1] ?? "unknown",
        description: descMatch?.[1] ?? "",
        screenshotFilename: "", // filled by next line
      });
    }

    if (line.trim().startsWith("![](../screenshots/")) {
      const fnMatch = line.match(/!\[]\(\.\.\/screenshots\/(.+?)\)/);
      if (fnMatch && currentSection.entries.length > 0) {
        currentSection.entries[currentSection.entries.length - 1].screenshotFilename =
          fnMatch[1];
      }
    }
  }

  if (currentSection) sections.push(currentSection);
  return sections;
}

const CATEGORIES = [
  "news",
  "social_media",
  "code",
  "documentation",
  "conversation",
  "meme",
  "recipe",
  "shopping",
  "finance",
  "other",
];

export default function DigestViewer() {
  const navigate = useNavigate();
  const [digests, setDigests] = useState<DigestSummary[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);
  const [sections, setSections] = useState<DigestSection[]>([]);
  const [pending, setPending] = useState<PendingScreenshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<string | null>(null);
  const [expandedImage, setExpandedImage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDigests = useCallback(async () => {
    try {
      const list = await fetchDigests();
      setDigests(list);
      if (list.length > 0 && !selectedWeek) {
        setSelectedWeek(list[0].week);
      }
    } catch {
      // Backend unavailable
    }
  }, [selectedWeek]);

  const loadPending = useCallback(async () => {
    try {
      const p = await fetchPendingScreenshots();
      setPending(p);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    async function init() {
      setLoading(true);
      await Promise.all([loadDigests(), loadPending()]);
      setLoading(false);
    }
    init();
  }, [loadDigests, loadPending]);

  useEffect(() => {
    if (!selectedWeek) {
      setSections([]);
      return;
    }
    fetchDigestContent(selectedWeek)
      .then((data) => setSections(parseDigestMarkdown(data.content)))
      .catch(() => setSections([]));
  }, [selectedWeek]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    try {
      await uploadScreenshots(files);
      await loadPending();
    } catch {
      // error
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleProcess = async () => {
    setProcessing(true);
    setProcessResult(null);
    try {
      const result = await processScreenshots();
      setProcessResult(
        `Processed ${result.processed} screenshot${result.processed !== 1 ? "s" : ""}${
          result.needs_review > 0 ? `, ${result.needs_review} need review` : ""
        }`
      );
      await Promise.all([loadDigests(), loadPending()]);
      // Reload current digest content
      if (selectedWeek) {
        const data = await fetchDigestContent(selectedWeek);
        setSections(parseDigestMarkdown(data.content));
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Processing failed";
      setProcessResult(message);
    } finally {
      setProcessing(false);
    }
  };

  const handleRecategorize = async (
    screenshotName: string,
    newCategory: string
  ) => {
    if (!selectedWeek) return;
    try {
      await recategorize(selectedWeek, screenshotName, newCategory);
      const data = await fetchDigestContent(selectedWeek);
      setSections(parseDigestMarkdown(data.content));
      await loadDigests();
    } catch {
      // error
    }
  };

  const needsReviewSection = sections.find((s) => s.category === "Needs Review");
  const regularSections = sections.filter((s) => s.category !== "Needs Review");

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between h-10 px-4 border-b border-thin border-border shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">
            Weekly Digest
          </span>
          {pending.length > 0 && (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300 palenight:bg-amber-950 palenight:text-amber-300">
              {pending.length} pending
            </span>
          )}
        </div>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <ArrowLeft className="h-3 w-3" />
          <span>Back</span>
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-thin border-border/50 shrink-0">
        {/* Week selector */}
        <select
          value={selectedWeek ?? ""}
          onChange={(e) => setSelectedWeek(e.target.value || null)}
          className="text-xs bg-transparent border border-border rounded-md px-2 py-1 outline-none text-foreground"
        >
          {digests.length === 0 && (
            <option value="">No digests yet</option>
          )}
          {digests.map((d) => (
            <option key={d.week} value={d.week}>
              {d.label} ({d.entry_count} items
              {d.needs_review > 0 ? `, ${d.needs_review} to review` : ""})
            </option>
          ))}
        </select>

        <div className="flex-1" />

        {/* Upload */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          className="hidden"
          onChange={handleUpload}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent border border-border transition-colors"
        >
          <Upload className="h-3 w-3" />
          Upload
        </button>

        {/* Process */}
        {pending.length > 0 && (
          <button
            onClick={handleProcess}
            disabled={processing}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-foreground text-background hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {processing ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <ImageIcon className="h-3 w-3" />
            )}
            {processing ? "Processing..." : `Process ${pending.length}`}
          </button>
        )}
      </div>

      {/* Process result toast */}
      <AnimatePresence>
        {processResult && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="mx-4 mt-2 flex items-center gap-2 px-3 py-2 rounded-md bg-muted text-xs text-foreground border border-border"
          >
            <AlertCircle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="flex-1">{processResult}</span>
            <button
              onClick={() => setProcessResult(null)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {loading ? (
          <div className="px-4 py-6 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-20 rounded bg-muted animate-pulse" />
            ))}
          </div>
        ) : sections.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Calendar className="h-6 w-6 mb-2 opacity-40" />
            <p className="text-xs">
              {digests.length === 0
                ? "No digests yet. Upload screenshots to get started."
                : "No entries in this digest."}
            </p>
          </div>
        ) : (
          <div className="px-4 py-3 space-y-6">
            {/* Needs Review section (if any) */}
            {needsReviewSection && needsReviewSection.entries.length > 0 && (
              <NeedsReviewSection
                entries={needsReviewSection.entries}
                onRecategorize={handleRecategorize}
              />
            )}

            {/* Regular sections */}
            {regularSections.map((section) => (
              <CategorySection key={section.category} section={section} onExpand={setExpandedImage} />
            ))}
          </div>
        )}
      </div>

      {/* Lightbox */}
      <AnimatePresence>
        {expandedImage && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setExpandedImage(null)}
            className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-8 cursor-pointer"
          >
            <motion.img
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.9 }}
              src={screenshotUrl(expandedImage)}
              alt=""
              className="max-w-full max-h-full rounded-lg shadow-2xl object-contain"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function CategorySection({
  section,
  onExpand,
}: {
  section: DigestSection;
  onExpand: (filename: string) => void;
}) {
  const colors = tagColor(section.category.toLowerCase().replace(" ", "_"));

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${colors.bg} ${colors.text}`}
        >
          {section.category}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {section.entries.length} item{section.entries.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {section.entries.map((entry, i) => (
          <EntryCard key={i} entry={entry} onExpand={onExpand} />
        ))}
      </div>
    </div>
  );
}

function EntryCard({
  entry,
  onExpand,
}: {
  entry: DigestEntry;
  onExpand: (filename: string) => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden group">
      {entry.screenshotFilename && (
        <div
          className="aspect-video bg-muted overflow-hidden cursor-pointer"
          onClick={() => onExpand(entry.screenshotFilename)}
        >
          <img
            src={screenshotUrl(entry.screenshotFilename)}
            alt={entry.title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
            loading="lazy"
          />
        </div>
      )}
      <div className="p-2.5">
        <p className="text-xs font-medium text-foreground truncate">
          {entry.title}
        </p>
        <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">
          {entry.description}
        </p>
        {entry.source !== "unknown" && (
          <span className="inline-block mt-1 text-[9px] font-mono text-muted-foreground/60">
            {entry.source}
          </span>
        )}
      </div>
    </div>
  );
}

function NeedsReviewSection({
  entries,
  onRecategorize,
}: {
  entries: DigestEntry[];
  onRecategorize: (screenshotName: string, category: string) => void;
}) {
  return (
    <div className="rounded-lg border border-amber-200 dark:border-amber-800 palenight:border-amber-800 bg-amber-50/50 dark:bg-amber-950/30 palenight:bg-amber-950/30 p-3">
      <div className="flex items-center gap-2 mb-2">
        <AlertCircle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
        <span className="text-xs font-medium text-amber-700 dark:text-amber-300">
          Needs Review
        </span>
        <span className="text-[10px] text-amber-600/60 dark:text-amber-400/60">
          {entries.length} item{entries.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-2">
        {entries.map((entry, i) => (
          <ReviewEntry
            key={i}
            entry={entry}
            onRecategorize={onRecategorize}
          />
        ))}
      </div>
    </div>
  );
}

function ReviewEntry({
  entry,
  onRecategorize,
}: {
  entry: DigestEntry;
  onRecategorize: (screenshotName: string, category: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex items-center gap-3 rounded-md bg-background/60 p-2 border border-border/50">
      {entry.screenshotFilename && (
        <img
          src={screenshotUrl(entry.screenshotFilename)}
          alt={entry.title}
          className="w-16 h-10 object-cover rounded shrink-0"
        />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-foreground truncate">
          {entry.title}
        </p>
        <p className="text-[10px] text-muted-foreground truncate">
          {entry.description}
        </p>
      </div>

      {/* Category picker */}
      <div className="relative">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1 px-2 py-1 text-[10px] rounded border border-border hover:bg-accent transition-colors"
        >
          <span>Categorize</span>
          <ChevronDown className="h-2.5 w-2.5" />
        </button>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <div className="absolute right-0 top-full mt-1 z-50 w-36 rounded-md border border-border bg-popover shadow-lg py-1">
              {CATEGORIES.map((cat) => {
                const c = tagColor(cat);
                return (
                  <button
                    key={cat}
                    onClick={() => {
                      setOpen(false);
                      onRecategorize(entry.screenshotFilename, cat);
                    }}
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-[10px] text-left hover:bg-accent/50 transition-colors"
                  >
                    <span
                      className={`w-2 h-2 rounded-full ${c.swatch}`}
                    />
                    <span className="text-foreground">
                      {cat.replace("_", " ")}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
