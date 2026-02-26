"use client";

import { AnimatePresence, motion } from "motion/react";
import { FileText, Plus, RefreshCw, Trash2 } from "lucide-react";
import type { NoteFile } from "@/types";
import { useCallback, useRef, useState } from "react";

interface NoteListProps {
  notes: NoteFile[];
  activeNoteId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

function timeAgo(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function NoteList({
  notes,
  activeNoteId,
  onSelect,
  onCreate,
  onDelete,
  onRefresh,
}: NoteListProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const confirmTimer = useRef<ReturnType<typeof setTimeout>>(null);

  const handleDelete = useCallback(
    (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      if (confirmId !== id) {
        setConfirmId(id);
        if (confirmTimer.current) clearTimeout(confirmTimer.current);
        confirmTimer.current = setTimeout(() => setConfirmId(null), 3000);
        return;
      }
      setConfirmId(null);
      if (confirmTimer.current) clearTimeout(confirmTimer.current);
      onDelete(id);
    },
    [confirmId, onDelete]
  );

  return (
    <div>
      {/* New note + refresh buttons */}
      <div className="flex items-center gap-1 px-3 py-1.5">
        <button
          onClick={onCreate}
          className="flex items-center gap-1.5 flex-1 px-2.5 py-1.5 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors duration-150"
        >
          <Plus className="h-3 w-3" />
          New Note
        </button>
        <button
          onClick={onRefresh}
          className="flex items-center justify-center h-6 w-6 rounded-md text-muted-foreground/50 hover:text-foreground hover:bg-accent transition-colors duration-150"
        >
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>

      {/* Notes list */}
      <div className="divide-y divide-border/50">
        <AnimatePresence initial={false}>
          {notes.map((note, index) => {
            const isActive = note.id === activeNoteId;
            const isConfirming = confirmId === note.id;

            return (
              <motion.div
                key={note.id}
                layout
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{
                  opacity: { duration: 0.2 },
                  height: { duration: 0.25 },
                  delay: index * 0.02,
                }}
                onClick={() => onSelect(note.id)}
                className={`flex items-center gap-2.5 px-3 py-2 cursor-pointer
                  transition-colors duration-150
                  ${isActive ? "bg-accent" : "hover:bg-accent/50"}
                  ${isConfirming ? "bg-red-50" : ""}`}
              >
                <FileText className={`h-3.5 w-3.5 flex-shrink-0 ${
                  isActive ? "text-foreground" : "text-muted-foreground"
                }`} />
                <div className="min-w-0 flex-1">
                  <p className={`text-xs truncate ${
                    isActive ? "font-medium text-foreground" : "text-foreground/80"
                  }`}>
                    {note.title || "Untitled"}
                  </p>
                  <p className="text-[10px] text-muted-foreground/60">
                    {timeAgo(note.updated_at)}
                  </p>
                </div>
                <motion.button
                  whileTap={{ scale: 0.9 }}
                  onClick={(e) => handleDelete(e, note.id)}
                  className={`flex-shrink-0 flex items-center justify-center h-5 w-5 rounded
                    transition-colors duration-150
                    ${isConfirming
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

      {notes.length === 0 && (
        <div className="px-4 py-4 text-center">
          <p className="text-[10px] text-muted-foreground/60">No notes yet</p>
        </div>
      )}
    </div>
  );
}
