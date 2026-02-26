"use client";

import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { FileEdit, FilePlus, ChevronRight, Check } from "lucide-react";

interface FileActionData {
  action: string;
  note_id: string;
  title: string;
  filename: string;
  markdown: string;
  updated_at: string;
}

interface ActionCardProps {
  action: "edit_current" | "create_new";
  filename: string;
  markdown: string;
  noteId?: string;
  noteTitle?: string;
  updatedAt?: string;
  onFileAction?: (data: FileActionData) => void;
  onNavigate?: (noteId: string) => void;
}

export default function ActionCard({
  action,
  filename,
  markdown,
  noteId,
  noteTitle,
  updatedAt,
  onFileAction,
  onNavigate,
}: ActionCardProps) {
  const appliedRef = useRef(false);

  // Notify parent once so it can sync UI state (file already written by backend)
  useEffect(() => {
    if (appliedRef.current || !noteId || !onFileAction) return;
    appliedRef.current = true;
    onFileAction({
      action,
      note_id: noteId,
      title: noteTitle || filename,
      filename,
      markdown,
      updated_at: updatedAt || new Date().toISOString(),
    });
  }, [action, filename, markdown, noteId, noteTitle, updatedAt, onFileAction]);

  const isEdit = action === "edit_current";
  const Icon = isEdit ? FileEdit : FilePlus;
  const title = isEdit
    ? `Applied to ${noteTitle || filename || "current note"}`
    : `Created ${noteTitle || filename}`;

  return (
    <motion.div
      layout
      className="rounded-lg border-thin border-border bg-muted/50 overflow-hidden my-2"
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
    >
      <button
        onClick={() => noteId && onNavigate?.(noteId)}
        className="flex items-center gap-2.5 w-full px-3 py-2.5 text-left hover:bg-accent/60 transition-colors duration-150"
      >
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-100 shrink-0">
          <Icon className="h-3 w-3 text-emerald-600" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium text-foreground">
              {title}
            </span>
            <Check className="h-3 w-3 text-emerald-500 shrink-0" />
          </div>
        </div>

        <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
      </button>
    </motion.div>
  );
}
