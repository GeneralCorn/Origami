"use client";

import { useState, useCallback } from "react";
import { motion } from "motion/react";
import { ScrollArea } from "@/components/ui/scroll-area";
import UploadDropzone from "./upload-dropzone";
import ChromaDocumentList from "./chroma-document-list";
import NoteList from "./note-list";
import type { NoteFile } from "@/types";

interface DocumentDrawerProps {
  notes: NoteFile[];
  activeNoteId: string | null;
  onSelectNote: (id: string) => void;
  onCreateNote: () => void;
  onDeleteNote: (id: string) => void;
  onRefreshNotes: () => void;
  onOpenReader?: (name: string) => void;
}

export interface PendingIngestion {
  fileId: string;
  filename: string;
  totalChunks: number;
}

export default function DocumentDrawer({
  notes,
  activeNoteId,
  onSelectNote,
  onCreateNote,
  onDeleteNote,
  onRefreshNotes,
  onOpenReader,
}: DocumentDrawerProps) {
  const [pendingIngestions, setPendingIngestions] = useState<PendingIngestion[]>([]);

  const handleIngestionStarted = useCallback((fileId: string, filename: string, totalChunks: number) => {
    setPendingIngestions((prev) => [...prev, { fileId, filename, totalChunks }]);
  }, []);

  const handleIngestionComplete = useCallback((fileId: string) => {
    setPendingIngestions((prev) => prev.filter((p) => p.fileId !== fileId));
  }, []);

  return (
    <motion.div
      initial={{ x: -300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -300, opacity: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="absolute left-0 top-0 bottom-0 z-40 w-72 flex flex-col overflow-hidden backdrop-blur-md bg-background/80 border-r border-thin border-border"
    >
      {/* Header */}
      <div className="flex items-center px-4 py-2 border-b border-thin border-border">
        <span className="text-xs font-medium text-muted-foreground tracking-wide uppercase">
          Workspace
        </span>
      </div>

      <ScrollArea className="flex-1">
        {/* Notes */}
        <div className="border-b border-thin border-border">
          <div className="flex items-center px-4 py-1.5">
            <span className="text-[10px] font-medium text-muted-foreground/70 tracking-wide uppercase">
              Notes
            </span>
          </div>
          <NoteList
            notes={notes}
            activeNoteId={activeNoteId}
            onSelect={onSelectNote}
            onCreate={onCreateNote}
            onDelete={onDeleteNote}
            onRefresh={onRefreshNotes}
          />
        </div>

        {/* Upload */}
        <div className="border-b border-thin border-border">
          <div className="flex items-center px-4 py-1.5">
            <span className="text-[10px] font-medium text-muted-foreground/70 tracking-wide uppercase">
              Upload PDF
            </span>
          </div>
          <div className="px-3 pb-3">
            <UploadDropzone onIngestionStarted={handleIngestionStarted} />
          </div>
        </div>

        {/* ChromaDB ingested documents */}
        <div>
          <div className="flex items-center px-4 py-1.5">
            <span className="text-[10px] font-medium text-muted-foreground/70 tracking-wide uppercase">
              Knowledge Base
            </span>
          </div>
          <ChromaDocumentList
            pendingIngestions={pendingIngestions}
            onIngestionComplete={handleIngestionComplete}
            onOpenReader={onOpenReader}
          />
        </div>
      </ScrollArea>
    </motion.div>
  );
}
