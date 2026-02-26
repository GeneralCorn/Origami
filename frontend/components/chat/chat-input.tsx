"use client";

import { useState, useRef, useCallback, type KeyboardEvent } from "react";
import { motion } from "motion/react";
import { Send } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string) => void;
  isLoading: boolean;
}

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [input, setInput] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, []);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");
    // Reset height after clearing
    requestAnimationFrame(() => {
      if (taRef.current) {
        taRef.current.style.height = "auto";
      }
    });
    onSend(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex items-end gap-2 p-3">
      <textarea
        ref={taRef}
        value={input}
        onChange={(e) => {
          setInput(e.target.value);
          resize();
        }}
        onKeyDown={handleKeyDown}
        placeholder="Ask about your notes..."
        disabled={isLoading}
        rows={1}
        className="flex-1 text-sm border-thin border-border bg-transparent rounded-md px-3 py-2 resize-none outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground disabled:opacity-50"
      />
      <motion.button
        type="button"
        disabled={isLoading || !input.trim()}
        whileTap={{ scale: 0.98 }}
        onClick={handleSend}
        className="inline-flex items-center justify-center h-9 w-9 rounded-md bg-foreground text-background disabled:opacity-40 transition-opacity shrink-0"
      >
        <Send className="h-3.5 w-3.5" />
      </motion.button>
    </div>
  );
}
