"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { FileText, Trash2 } from "lucide-react";
import { fetchPDFs, deletePDF } from "@/lib/api/upload";
import type { PersistedPDF } from "@/types";

interface DocumentListProps {
  refreshTrigger?: number;
}

export default function DocumentList({ refreshTrigger }: DocumentListProps) {
  const [pdfs, setPdfs] = useState<PersistedPDF[]>([]);
  const [confirmName, setConfirmName] = useState<string | null>(null);
  const confirmTimer = useRef<ReturnType<typeof setTimeout>>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchPDFs();
      setPdfs(data);
    } catch {
      // silently fail
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10_000);
    return () => clearInterval(interval);
  }, [load]);

  // Re-fetch when parent signals a new upload was confirmed
  useEffect(() => {
    if (refreshTrigger) load();
  }, [refreshTrigger, load]);

  const handleDelete = useCallback(
    async (e: React.MouseEvent, name: string) => {
      e.stopPropagation();
      if (confirmName !== name) {
        setConfirmName(name);
        if (confirmTimer.current) clearTimeout(confirmTimer.current);
        confirmTimer.current = setTimeout(() => setConfirmName(null), 3000);
        return;
      }
      setConfirmName(null);
      if (confirmTimer.current) clearTimeout(confirmTimer.current);
      // Optimistic: remove from UI immediately, backend in background
      setPdfs((prev) => prev.filter((p) => p.name !== name));
      deletePDF(name).catch(() => load());
    },
    [confirmName, load]
  );

  if (pdfs.length === 0) {
    return (
      <div className="px-4 py-6 text-center">
        <p className="text-xs text-muted-foreground">No files yet</p>
      </div>
    );
  }

  return (
    <div className="px-3 pb-3 space-y-1">
      <AnimatePresence initial={false}>
        {pdfs.map((pdf) => {
          const isConfirming = confirmName === pdf.name;
          return (
            <motion.div
              key={pdf.name}
              layout
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex items-center gap-2.5 px-2.5 py-2 rounded-md overflow-hidden transition-colors duration-150 ${
                isConfirming ? "bg-red-50/50" : "hover:bg-accent/50"
              }`}
            >
              <FileText className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-foreground truncate">
                  {pdf.name}
                </p>
                <p className="text-[10px] font-mono text-muted-foreground">
                  {formatBytes(pdf.size)}
                </p>
              </div>
              <motion.button
                whileTap={{ scale: 0.9 }}
                onClick={(e) => handleDelete(e, pdf.name)}
                className={`flex-shrink-0 flex items-center justify-center h-5 w-5 rounded transition-colors duration-150 ${
                  isConfirming
                    ? "bg-red-100 text-red-600"
                    : "text-muted-foreground/30 hover:text-red-500 hover:bg-accent"
                }`}
              >
                <Trash2 className="h-2.5 w-2.5" />
              </motion.button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
