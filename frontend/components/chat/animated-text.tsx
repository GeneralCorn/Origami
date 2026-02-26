"use client";

import dynamic from "next/dynamic";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { useTheme } from "@/lib/theme";
import "katex/dist/katex.min.css";

const MarkdownPreview = dynamic(
  () => import("@uiw/react-markdown-preview"),
  { ssr: false }
);

/**
 * Wrap undelimited LaTeX in $...$ so remark-math can parse it.
 * The LLM sometimes outputs \commands without dollar-sign delimiters.
 */
function ensureLatexDelimiters(content: string): string {
  if (!/\\[a-zA-Z]{2,}/.test(content)) return content;

  // Protect existing code blocks and math delimiters
  const saved: string[] = [];
  const save = (m: string) => {
    saved.push(m);
    return `\x00${saved.length - 1}\x00`;
  };
  let text = content
    .replace(/```[\s\S]*?```/g, save)
    .replace(/`[^`]+`/g, save)
    .replace(/\$\$[\s\S]*?\$\$/g, save)
    .replace(/\$[^$\n]+?\$/g, save);

  // [formula with \commands] → display math (but not markdown links)
  text = text.replace(
    /\[([^\]]+\\[a-zA-Z]{2,}[^\]]*)\](?!\()/g,
    (_, inner) => `$$${inner.trim()}$$`,
  );

  // Inline: \command with surrounding math context → $...$
  // Matches optional leading var/number, then \command{args}, then trailing
  // math tokens (short vars, operators, more \commands, braces, etc.)
  text = text.replace(
    /(?:(?:[A-Z][a-z]?(?:[_^]\{[^}]*?\}|[_^]\w)?\s*(?:[=+\-<>]\s*)?|[0-9]+(?:\.[0-9]+)?\s+))?\\[a-zA-Z]{2,}(?:\{(?:[^{}]|\{[^{}]*?\})*?\})*(?:\s*(?:\\[a-zA-Z]{2,}(?:\{(?:[^{}]|\{[^{}]*?\})*?\})*|[A-Za-z]{1,2}(?:[_^]\{[^}]*?\}|[_^]\w)?|[0-9]+(?:\.[0-9]+)?|[+\-*\/=<>^_{}()\[\]|,.]|\|\|)\s*)*/g,
    (match) => {
      let expr = match.trim();
      if (!expr) return match;
      // Strip trailing sentence punctuation
      expr = expr.replace(/[.,;:!?]+$/, "");
      if (!expr || !/\\[a-zA-Z]{2,}/.test(expr)) return match;
      const idx = match.indexOf(expr);
      return match.slice(0, idx) + "$" + expr + "$" + match.slice(idx + expr.length);
    },
  );

  // Restore protected blocks
  text = text.replace(/\x00(\d+)\x00/g, (_, i) => saved[+i]);
  return text;
}

interface AnimatedTextProps {
  content: string;
}

export default function AnimatedText({ content }: AnimatedTextProps) {
  const { theme } = useTheme();
  return (
    <div data-color-mode={theme === "light" ? "light" : "dark"} className="chat-markdown">
      <MarkdownPreview
        source={ensureLatexDelimiters(content)}
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
      />
    </div>
  );
}
