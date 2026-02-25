"use client";

import { useCallback, useRef, useLayoutEffect } from "react";
import dynamic from "next/dynamic";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

const MDEditor = dynamic(() => import("@uiw/react-md-editor"), { ssr: false });

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  title: string;
  onTitleChange: (title: string) => void;
}

export default function MarkdownEditor({
  value,
  onChange,
  title,
  onTitleChange,
}: MarkdownEditorProps) {
  const scrollRestore = useRef<{ el: HTMLTextAreaElement; top: number } | null>(
    null
  );

  // Restore scroll position synchronously before paint.
  useLayoutEffect(() => {
    if (scrollRestore.current) {
      scrollRestore.current.el.scrollTop = scrollRestore.current.top;
      scrollRestore.current = null;
    }
  });

  const handleChange = useCallback(
    (val?: string) => onChange(val ?? ""),
    [onChange]
  );

  // Intercept the closing $ that completes $$[content]$$ and expand to block format.
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key !== "$") return;

      const ta = e.currentTarget;
      const pos = ta.selectionStart;
      const before = ta.value.slice(0, pos);

      // This $ would turn $$[content]$ into $$[content]$$
      const match = before.match(/\$\$([^\n]*)\$$/);
      if (!match) return;

      e.preventDefault();

      const content = match[1];
      const matchStart = before.length - match[0].length;
      const after = ta.value.slice(pos);

      scrollRestore.current = { el: ta, top: ta.scrollTop };

      onChange(
        ta.value.slice(0, matchStart) + "$$\n" + content + "\n$$" + after
      );
    },
    [onChange]
  );

  return (
    <div className="h-full flex flex-col" data-color-mode="light">
      {/* Title input */}
      <div className="flex items-center h-10 px-3 border-b border-thin border-zinc-200 shrink-0">
        <input
          type="text"
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          placeholder="Untitled"
          className="w-full text-sm font-semibold text-foreground bg-transparent border-none outline-none placeholder:text-muted-foreground/40"
        />
      </div>

      {/* Markdown editor */}
      <div className="flex-1 overflow-hidden">
        <MDEditor
          value={value}
          onChange={handleChange}
          height="100%"
          visibleDragbar={false}
          preview="live"
          textareaProps={{ onKeyDown: handleKeyDown }}
          previewOptions={{
            remarkPlugins: [remarkMath],
            rehypePlugins: [rehypeKatex],
          }}
        />
      </div>
    </div>
  );
}
