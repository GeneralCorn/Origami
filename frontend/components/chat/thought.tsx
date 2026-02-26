"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronRight } from "lucide-react";

interface ThoughtProps {
  text: string;
  isStreaming: boolean;
}

export default function Thought({ text, isStreaming }: ThoughtProps) {
  const [isOpen, setIsOpen] = useState(true);

  // Auto-collapse when streaming completes
  useEffect(() => {
    if (!isStreaming && text.length > 0) {
      const timer = setTimeout(() => setIsOpen(false), 500);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, text.length]);

  return (
    <motion.div
      layout
      className="rounded-md border-thin border-border backdrop-blur-md bg-muted/80 overflow-hidden my-2"
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
    >
      {/* Header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-accent/50 transition-colors duration-150"
      >
        <motion.div
          animate={{ rotate: isOpen ? 90 : 0 }}
          transition={{ type: "spring", stiffness: 400, damping: 25 }}
        >
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
        </motion.div>
        <span className="text-xs font-medium text-muted-foreground">
          {isStreaming ? "Thinking..." : "Thought"}
        </span>
        {isStreaming && (
          <span className="ml-auto h-1.5 w-1.5 rounded-full bg-muted-foreground animate-subtle-pulse" />
        )}
      </button>

      {/* Content */}
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 pt-0">
              <p className="text-xs font-mono leading-relaxed text-muted-foreground whitespace-pre-wrap">
                {text}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
