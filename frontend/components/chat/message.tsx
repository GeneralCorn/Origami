"use client";

import { type UIMessage } from "ai";
import { User, Bot } from "lucide-react";
import Thought, { type ThoughtMeta } from "./thought";
import AnimatedText from "./animated-text";
import ActionCard from "./action-card";

export interface ActionHandlers {
  onFileAction?: (data: { action: string; note_id: string; title: string; filename: string; markdown: string; updated_at: string }) => void;
  onNavigate?: (noteId: string) => void;
  activeTitle?: string;
}

interface MessageProps {
  message: UIMessage;
  isStreaming: boolean;
  actionHandlers?: ActionHandlers;
}

/**
 * Extract a string field value from malformed JSON using character walking.
 * Handles LaTeX-polluted JSON where \frac (\f) and \beta (\b) collide
 * with valid JSON escapes, making JSON.parse fundamentally unreliable.
 */
function extractField(json: string, field: string): string | null {
  const keyRe = new RegExp(`"${field}"\\s*:\\s*"`);
  const m = keyRe.exec(json);
  if (!m) return null;

  let i = m.index + m[0].length;
  const chars: string[] = [];
  while (i < json.length) {
    const ch = json[i];
    if (ch === "\\" && i + 1 < json.length) {
      const nxt = json[i + 1];
      if (nxt === '"')  { chars.push('"');  i += 2; continue; }
      if (nxt === "\\") { chars.push("\\"); i += 2; continue; }
      if (nxt === "/")  { chars.push("/");  i += 2; continue; }
      if (nxt === "n")  { chars.push("\n"); i += 2; continue; }
      if (nxt === "r")  { chars.push("\r"); i += 2; continue; }
      if (nxt === "t")  { chars.push("\t"); i += 2; continue; }
      // \b \f followed by a letter → LaTeX (\beta, \frac), NOT backspace/form-feed
      if ((nxt === "b" || nxt === "f") && i + 2 < json.length && /[a-zA-Z]/.test(json[i + 2])) {
        chars.push("\\", nxt); i += 2; continue;
      }
      if (nxt === "b") { chars.push("\b"); i += 2; continue; }
      if (nxt === "f") { chars.push("\f"); i += 2; continue; }
      // Any other \X — keep as-is (LaTeX like \eta, \alpha, \partial, \sum)
      chars.push("\\", nxt); i += 2; continue;
    }
    if (ch === '"') break;
    chars.push(ch);
    i += 1;
  }
  return chars.join("");
}

/**
 * Fallback: if the backend failed to parse LLM JSON and leaked raw JSON
 * as the text content, recover fields via character walking (not JSON.parse).
 */
function tryRecoverAction(
  text: string
): { action: string; message: string; content?: string; filename?: string } | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") || !trimmed.includes('"action"')) return null;

  const action = extractField(trimmed, "action");
  const message = extractField(trimmed, "message");
  if (!action || !message) return null;

  return {
    action,
    message,
    content: extractField(trimmed, "content") || undefined,
    filename: extractField(trimmed, "filename") || undefined,
  };
}

export default function Message({ message, isStreaming, actionHandlers }: MessageProps) {
  const isUser = message.role === "user";

  return (
    <div className="flex gap-3 py-3">
      {/* Avatar */}
      <div className="flex-shrink-0 pt-0.5">
        {isUser ? (
          <div className="flex h-6 w-6 items-center justify-center rounded-sm border-thin border-border">
            <User className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
        ) : (
          <div className="flex h-6 w-6 items-center justify-center rounded-sm bg-foreground">
            <Bot className="h-3.5 w-3.5 text-background" />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          {isUser ? "You" : "Assistant"}
        </p>
        <div className="text-sm leading-relaxed text-foreground">
          {message.parts.map((part, i) => {
            if (part.type === "reasoning") {
              const meta = (part as any).providerMetadata?.origami as ThoughtMeta | undefined;
              return (
                <Thought
                  key={i}
                  text={part.text}
                  isStreaming={isStreaming && message.role === "assistant"}
                  meta={meta}
                />
              );
            }
            if (part.type === "text") {
              const textMeta = (part as any).providerMetadata?.origami as Record<string, number> | undefined;
              // Fallback: recover raw JSON that backend failed to parse
              const recovered = tryRecoverAction(part.text);
              const statsFooter = textMeta?.total_latency_s != null && (
                <p className="text-[10px] font-mono text-muted-foreground/50 mt-2 space-x-1">
                  <span>
                    Response: {textMeta.latency_s?.toFixed(2) ?? "?"}s
                    {" \u00b7 "}{textMeta.input_tokens ?? 0} in / {textMeta.output_tokens ?? 0} out
                  </span>
                  <span className="text-muted-foreground/30">|</span>
                  <span>
                    Total: {textMeta.total_latency_s.toFixed(2)}s
                    {" \u00b7 "}{textMeta.total_output_tokens ?? 0} tokens out
                  </span>
                </p>
              );
              if (recovered) {
                const isAction = recovered.action === "edit" || recovered.action === "create";
                return (
                  <div key={i}>
                    <AnimatedText content={recovered.message} />
                    {isAction && recovered.content && (
                      <ActionCard
                        action={recovered.action === "edit" ? "edit_current" : "create_new"}
                        filename={recovered.filename || actionHandlers?.activeTitle || ""}
                        markdown={recovered.content}
                        onFileAction={actionHandlers?.onFileAction}
                        onNavigate={actionHandlers?.onNavigate}
                      />
                    )}
                    {statsFooter}
                  </div>
                );
              }
              return (
                <div key={i}>
                  <AnimatedText content={part.text} />
                  {statsFooter}
                </div>
              );
            }
            if (part.type === "data-action") {
              const data = (part as { type: string; data: Record<string, string> }).data;
              return (
                <ActionCard
                  key={i}
                  action={data.action as "edit_current" | "create_new"}
                  filename={data.filename || actionHandlers?.activeTitle || ""}
                  markdown={data.markdown || ""}
                  noteId={data.note_id}
                  noteTitle={data.title}
                  updatedAt={data.updated_at}
                  onFileAction={actionHandlers?.onFileAction}
                  onNavigate={actionHandlers?.onNavigate}
                />
              );
            }
            return null;
          })}
        </div>
      </div>
    </div>
  );
}
