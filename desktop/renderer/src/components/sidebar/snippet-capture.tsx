import { useCallback, useState } from "react";
import { ClipboardPaste } from "lucide-react";
import { createSnippet } from "@/lib/api/snippets";
import NamingDialog from "./naming-dialog";

const MAX_TITLE_CHARS = 80;
// Mirrors MAX_TEXT_CHARS in backend/routes/snippets.py, so an oversized
// paste is refused at the point of paste rather than by a 413.
const MAX_TEXT_CHARS = 500_000;

interface SnippetCaptureProps {
  onIngestionStarted: (fileId: string, filename: string, totalChunks: number) => void;
}

/** First non-empty line, truncated. Mirrors derive_title in the backend. */
function suggestTitle(text: string): string {
  for (const line of text.split("\n")) {
    const stripped = line.trim().replace(/^#+/, "").trim();
    if (stripped) return stripped.slice(0, MAX_TITLE_CHARS);
  }
  return "Untitled Snippet";
}

export default function SnippetCapture({ onIngestionStarted }: SnippetCaptureProps) {
  const [text, setText] = useState("");
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const handleSave = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isSaving) return;
    setStatusMsg(null);
    setPendingText(trimmed);
  }, [text, isSaving]);

  const handleConfirm = useCallback(
    async (name: string, tags: string[]) => {
      if (!pendingText) return;
      setIsSaving(true);
      try {
        const result = await createSnippet(pendingText, name, tags);
        if (result.duplicate) {
          setStatusMsg("Already captured");
          setTimeout(() => setStatusMsg(null), 4000);
        } else {
          onIngestionStarted(result.id, result.title ?? name, result.total_chunks ?? 0);
          setText("");
        }
      } catch (error) {
        // Swallowing this left the user watching the Save button stop
        // spinning with nothing captured and no way to know why, and
        // clicking Save again minted another orphaned file server-side.
        setStatusMsg(error instanceof Error ? error.message : "Capture failed");
      } finally {
        setIsSaving(false);
        setPendingText(null);
      }
    },
    [pendingText, onIngestionStarted]
  );

  const handleCancel = useCallback(() => {
    setPendingText(null);
  }, []);

  return (
    <>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            handleSave();
          }
        }}
        rows={3}
        maxLength={MAX_TEXT_CHARS}
        placeholder="Paste a snippet"
        disabled={isSaving}
        className="w-full resize-none rounded-md border border-thin border-border bg-transparent px-2 py-1.5 text-xs outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-ring disabled:opacity-50"
      />
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span
          className={`flex items-center gap-1 text-[10px] ${statusMsg ? "text-amber-600" : "text-muted-foreground/60"}`}
        >
          <ClipboardPaste
            className={`h-2.5 w-2.5 ${statusMsg ? "text-amber-500" : "text-muted-foreground/60"}`}
          />
          {statusMsg ?? "⌘↩ to save"}
        </span>
        <button
          type="button"
          onClick={handleSave}
          disabled={!text.trim() || isSaving}
          className="rounded-md border border-thin border-border px-2 py-1 text-[11px] font-medium transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSaving ? "Saving..." : "Save"}
        </button>
      </div>

      <NamingDialog
        open={pendingText !== null}
        suggestedName={pendingText ? suggestTitle(pendingText) : ""}
        originalFilename="snippet"
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </>
  );
}
