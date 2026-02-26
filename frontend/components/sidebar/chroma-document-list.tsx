"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Database, FileText, Trash2, Eye, Check, Pencil } from "lucide-react";
import { fetchDocuments, deleteDocument, updateTitle } from "@/lib/api/documents";
import { tagColor } from "@/lib/utils";
import type { ChromaDocument } from "@/types";
import type { PendingIngestion } from "./document-drawer";

interface ChromaDocumentListProps {
  pendingIngestions?: PendingIngestion[];
  onIngestionComplete?: (fileId: string) => void;
  onOpenReader?: (name: string) => void;
}

export default function ChromaDocumentList({
  pendingIngestions = [],
  onIngestionComplete,
  onOpenReader,
}: ChromaDocumentListProps) {
  const [docs, setDocs] = useState<ChromaDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const confirmTimer = useRef<ReturnType<typeof setTimeout>>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchDocuments();
      setDocs(data);
      return data;
    } catch {
      // silently fail — panel just shows empty
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Check if any pending ingestions have completed
  const pendingRef = useRef(pendingIngestions);
  pendingRef.current = pendingIngestions;
  const onCompleteRef = useRef(onIngestionComplete);
  onCompleteRef.current = onIngestionComplete;

  const checkCompleted = useCallback((data: ChromaDocument[] | null) => {
    if (!data || !onCompleteRef.current) return;
    const chromaMap = new Map(data.map((d) => [d.file_id, d.chunk_count]));
    for (const pending of pendingRef.current) {
      const current = chromaMap.get(pending.fileId) ?? 0;
      // Only mark complete when ALL chunks are ingested
      if (pending.totalChunks > 0 && current >= pending.totalChunks) {
        onCompleteRef.current(pending.fileId);
      }
    }
  }, []);

  useEffect(() => {
    load().then(checkCompleted);
  }, [load, checkCompleted]);

  // Poll — faster (3s) when ingestions are pending, normal (10s) otherwise
  useEffect(() => {
    const interval = pendingIngestions.length > 0 ? 3_000 : 10_000;
    const id = setInterval(() => {
      load().then(checkCompleted);
    }, interval);
    return () => clearInterval(id);
  }, [load, checkCompleted, pendingIngestions.length]);

  const handleDelete = useCallback(
    async (e: React.MouseEvent, fileId: string) => {
      e.stopPropagation();
      if (confirmId !== fileId) {
        setConfirmId(fileId);
        if (confirmTimer.current) clearTimeout(confirmTimer.current);
        confirmTimer.current = setTimeout(() => setConfirmId(null), 3000);
        return;
      }
      setConfirmId(null);
      if (confirmTimer.current) clearTimeout(confirmTimer.current);
      // Optimistic: remove from UI immediately, backend in background
      setDocs((prev) => prev.filter((d) => d.file_id !== fileId));
      deleteDocument(fileId).catch(() => load());
    },
    [confirmId, load]
  );

  const handleTitleSave = useCallback(
    async (fileId: string) => {
      const trimmed = editTitle.trim();
      if (!trimmed) { setEditingId(null); return; }
      // Optimistic update
      setDocs((prev) => prev.map((d) => d.file_id === fileId ? { ...d, title: trimmed } : d));
      setEditingId(null);
      updateTitle(fileId, trimmed).catch(() => load());
    },
    [editTitle, load]
  );

  // Detect duplicates
  const filenameCounts = new Map<string, number>();
  for (const doc of docs) {
    filenameCounts.set(doc.filename, (filenameCounts.get(doc.filename) ?? 0) + 1);
  }

  const totalChunks = docs.reduce((sum, d) => sum + d.chunk_count, 0);

  // Build a map of current chunk counts for progress tracking
  const chromaMap = new Map(docs.map((d) => [d.file_id, d.chunk_count]));

  if (loading) {
    return (
      <div className="space-y-2 p-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-16 rounded-lg bg-muted animate-pulse"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
    );
  }

  if (docs.length === 0 && pendingIngestions.length === 0) {
    return (
      <div className="px-4 py-6 text-center">
        <Database className="mx-auto h-4 w-4 text-muted-foreground/50" />
        <p className="mt-1.5 text-xs text-muted-foreground/70">
          No ingested documents
        </p>
      </div>
    );
  }

  return (
    <div className="px-3 pb-3 space-y-2">
      {/* Stats bar */}
      <div className="flex items-center justify-between px-1 py-1">
        <span className="text-[10px] font-mono text-muted-foreground/60">
          {docs.length} doc{docs.length !== 1 ? "s" : ""}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground/60">
          {totalChunks} chunks
        </span>
      </div>

      {/* Pending ingestion cards */}
      <AnimatePresence initial={false}>
        {pendingIngestions.map((pending) => {
          const currentChunks = chromaMap.get(pending.fileId) ?? 0;
          const hasChunks = currentChunks > 0;
          const progress = pending.totalChunks > 0
            ? Math.round((currentChunks / pending.totalChunks) * 100)
            : 0;
          return (
            <motion.div
              key={`pending-${pending.fileId}`}
              layout
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95, height: 0, marginBottom: 0 }}
              transition={{ duration: 0.2 }}
              className={`rounded-lg border border-thin p-2.5 overflow-hidden transition-colors duration-300
                ${hasChunks
                  ? "border-blue-200 bg-blue-50/40"
                  : "border-blue-200 bg-blue-50/30 animate-pulse"
                }`}
            >
              <div className="flex items-start gap-2">
                <div className={`h-3.5 w-3.5 flex-shrink-0 mt-0.5 rounded-full border-2 border-t-transparent animate-spin
                  ${hasChunks ? "border-blue-400" : "border-blue-300"}`}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-foreground truncate">
                    {pending.filename}
                  </p>
                  <span className="text-[10px] font-mono text-blue-500/70">
                    {hasChunks
                      ? `${currentChunks}/${pending.totalChunks} chunks`
                      : "Processing..."
                    }
                  </span>
                </div>
              </div>
              {hasChunks && (
                <div className="mt-2 h-1 rounded-full bg-blue-100 overflow-hidden">
                  <motion.div
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                    className="h-full rounded-full bg-blue-400"
                  />
                </div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Document cards (hide docs that have a pending ingestion card) */}
      <AnimatePresence initial={false}>
        {docs.filter((d) => !pendingIngestions.some((p) => p.fileId === d.file_id)).map((doc, index) => {
          const isDuplicate = (filenameCounts.get(doc.filename) ?? 0) > 1;
          const isConfirming = confirmId === doc.file_id;

          return (
            <motion.div
              key={doc.file_id}
              layout
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95, height: 0, marginBottom: 0 }}
              transition={{
                opacity: { duration: 0.2 },
                scale: { duration: 0.2 },
                height: { duration: 0.25 },
                layout: { duration: 0.25 },
                delay: index * 0.03,
              }}
              className={`rounded-lg border border-thin p-2.5 overflow-hidden transition-colors duration-150
                ${isConfirming
                  ? "border-red-200 bg-red-50/50"
                  : "border-border bg-card/60 hover:bg-accent/50"
                }`}
            >
              {/* Top row: icon + name + delete */}
              <div className="flex items-start gap-2">
                <FileText className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground mt-0.5" />
                <div className="min-w-0 flex-1">
                  {editingId === doc.file_id ? (
                    <div className="flex items-center gap-1">
                      <input
                        autoFocus
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleTitleSave(doc.file_id);
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        className="text-xs font-medium bg-transparent border-b border-foreground/20 outline-none w-full py-0.5"
                      />
                      <button
                        onClick={() => handleTitleSave(doc.file_id)}
                        className="flex-shrink-0 text-emerald-500 hover:text-emerald-600 transition-colors"
                      >
                        <Check className="h-3 w-3" />
                      </button>
                    </div>
                  ) : (
                    <div
                      className="flex items-center gap-1 group/title cursor-pointer"
                      onClick={() => { setEditingId(doc.file_id); setEditTitle(doc.title || doc.filename); }}
                    >
                      <p className="text-xs font-medium text-foreground truncate">
                        {doc.title || doc.filename}
                      </p>
                      <Pencil className="h-2.5 w-2.5 flex-shrink-0 text-muted-foreground/0 group-hover/title:text-muted-foreground/50 transition-colors" />
                    </div>
                  )}
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[10px] font-mono text-muted-foreground">
                      {doc.chunk_count} chunk{doc.chunk_count !== 1 ? "s" : ""}
                    </span>
                    {isDuplicate && (
                      <span className="text-[9px] font-medium uppercase tracking-wider text-amber-600 bg-amber-50 px-1 py-px rounded">
                        duplicate
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex-shrink-0 flex items-center gap-0.5">
                  {onOpenReader && (
                    <motion.button
                      whileTap={{ scale: 0.9 }}
                      onClick={() => onOpenReader(doc.filename.replace(/\.pdf$/i, ""))}
                      className="flex items-center justify-center h-5 w-5 rounded text-muted-foreground/30 hover:text-foreground hover:bg-accent transition-colors duration-150"
                    >
                      <Eye className="h-2.5 w-2.5" />
                    </motion.button>
                  )}
                  <motion.button
                    whileTap={{ scale: 0.9 }}
                    onClick={(e) => handleDelete(e, doc.file_id)}
                    className={`flex items-center justify-center h-5 w-5 rounded
                      transition-colors duration-150
                      ${isConfirming
                        ? "bg-red-100 text-red-600"
                        : "text-muted-foreground/30 hover:text-red-500 hover:bg-accent"
                      }`}
                  >
                    <Trash2 className="h-2.5 w-2.5" />
                  </motion.button>
                </div>
              </div>

              {/* Tags */}
              {doc.tags?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5 ml-5.5">
                  {doc.tags.map((tag) => {
                    const colors = tagColor(tag);
                    return (
                      <span
                        key={tag}
                        className={`text-[9px] font-medium px-1.5 py-0.5 rounded-full ${colors.bg} ${colors.text}`}
                      >
                        {tag}
                      </span>
                    );
                  })}
                </div>
              )}

            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
