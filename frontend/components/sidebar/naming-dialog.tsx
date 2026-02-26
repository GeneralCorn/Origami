"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { FileText, Plus, Check } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { fetchTags } from "@/lib/api/upload";
import { tagColor } from "@/lib/utils";

interface NamingDialogProps {
  open: boolean;
  suggestedName: string;
  originalFilename: string;
  onConfirm: (name: string, tags: string[]) => void;
  onCancel: () => void;
}

export default function NamingDialog({
  open,
  suggestedName,
  originalFilename,
  onConfirm,
  onCancel,
}: NamingDialogProps) {
  const [name, setName] = useState(suggestedName);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setName(suggestedName);
  }, [suggestedName]);

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.select());
      setSelectedTags([]);
      setNewTag("");
      fetchTags().then(setAllTags).catch(() => {});
    }
  }, [open]);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const addNewTag = () => {
    const trimmed = newTag.trim().toLowerCase();
    if (!trimmed) return;
    if (!allTags.includes(trimmed)) {
      setAllTags((prev) => [...prev, trimmed]);
    }
    if (!selectedTags.includes(trimmed)) {
      setSelectedTags((prev) => [...prev, trimmed]);
    }
    setNewTag("");
  };

  const handleConfirm = () => {
    const trimmed = name.trim();
    onConfirm(trimmed || "untitled", selectedTags);
  };

  const dialog = (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onCancel}
            className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm"
          />

          {/* Dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.15 }}
            className="fixed z-50 left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-80 rounded-lg border border-border bg-popover p-4 shadow-lg"
          >
            <div className="flex items-center gap-2 mb-3">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <p className="text-xs text-muted-foreground truncate">
                {originalFilename}
              </p>
            </div>

            <label className="text-xs font-medium text-foreground mb-1.5 block">
              Document name
            </label>
            <Input
              ref={inputRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleConfirm();
                if (e.key === "Escape") onCancel();
              }}
              placeholder="untitled"
              className="text-sm border-thin border-border"
            />

            {/* Tag picker */}
            <label className="text-xs font-medium text-foreground mt-3 mb-1.5 block">
              Tags
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {allTags.map((tag) => {
                const colors = tagColor(tag);
                const selected = selectedTags.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleTag(tag)}
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium border transition-all duration-150 ${colors.bg} ${colors.text} ${selected ? `${colors.border} ring-1 ring-offset-1 ring-current` : "border-transparent opacity-70 hover:opacity-100"}`}
                  >
                    {selected && <Check className="h-2.5 w-2.5" />}
                    {tag}
                  </button>
                );
              })}
            </div>
            <div className="flex gap-1.5">
              <Input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addNewTag();
                  }
                }}
                placeholder="New tag..."
                className="text-xs h-7 border-thin border-border flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addNewTag}
                className="h-7 w-7 p-0 shrink-0"
                disabled={!newTag.trim()}
              >
                <Plus className="h-3 w-3" />
              </Button>
            </div>

            <div className="flex justify-end gap-2 mt-4">
              <Button
                variant="outline"
                size="sm"
                onClick={onCancel}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleConfirm}
                className="text-xs"
              >
                Confirm
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );

  if (typeof document === "undefined") return null;
  return createPortal(dialog, document.body);
}
