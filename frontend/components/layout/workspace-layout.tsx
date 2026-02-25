"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { AnimatePresence } from "motion/react";
import { motion } from "motion/react";
import { PanelLeft, Database, MessageSquare, ChevronLeft, ChevronRight } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { type PanelImperativeHandle } from "react-resizable-panels";
import MarkdownEditor from "@/components/editor/markdown-editor";
import ChatPanel from "@/components/chat/chat-panel";
import DocumentDrawer from "@/components/sidebar/document-drawer";
import PdfReader from "@/components/reader/pdf-reader";
import DatabaseViewer from "@/components/database/database-viewer";
import type { NoteFile } from "@/types";
import {
  fetchNotes,
  fetchNote,
  createNote,
  updateNote,
  deleteNote,
} from "@/lib/api/notes";

interface WorkspaceLayoutProps {
  chatId?: string;
}

export default function WorkspaceLayout({ chatId }: WorkspaceLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [editorContent, setEditorContent] = useState("");
  const [viewMode, setViewMode] = useState<"research" | "reader" | "database">("research");
  const [readerPdfName, setReaderPdfName] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const chatPanelRef = useRef<PanelImperativeHandle>(null);

  const toggleChat = useCallback(() => {
    const panel = chatPanelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) {
      panel.resize("350px");
    } else {
      panel.collapse();
    }
  }, []);

  // Notes state
  const [notes, setNotes] = useState<NoteFile[]>([]);
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null);
  const [activeTitle, setActiveTitle] = useState("Untitled");

  // Debounced editor content for passing to chat
  const chatDebounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const [debouncedContent, setDebouncedContent] = useState("");

  // Auto-save debounce
  const saveDebounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const activeNoteRef = useRef<string | null>(null);
  useEffect(() => {
    activeNoteRef.current = activeNoteId;
  }, [activeNoteId]);

  // Load notes on mount
  useEffect(() => {
    async function init() {
      try {
        const list = await fetchNotes();
        setNotes(list);
        if (list.length > 0) {
          // Load the most recent note
          const first = list[0];
          setActiveNoteId(first.id);
          setActiveTitle(first.title);
          const data = await fetchNote(first.id);
          setEditorContent(data.content);
        } else {
          // Create a blank note
          const created = await createNote("Untitled");
          setActiveNoteId(created.id);
          setActiveTitle(created.title);
          setEditorContent(`# ${created.title}\n\n`);
          setNotes([{ id: created.id, title: created.title, updated_at: new Date().toISOString() }]);
        }
      } catch {
        // Backend might not be running, start with empty state
        setEditorContent("");
      }
    }
    init();
  }, []);

  // Poll notes list to pick up backend-created notes (e.g. from AI)
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const list = await fetchNotes();
        setNotes(list);
      } catch {
        // Backend unavailable — skip
      }
    }, 5_000);
    return () => clearInterval(interval);
  }, []);

  // Auto-save note content (1s after last edit)
  const saveNote = useCallback(async (noteId: string, content: string) => {
    try {
      const result = await updateNote(noteId, content);
      setNotes((prev) =>
        prev.map((n) =>
          n.id === noteId
            ? { ...n, title: result.title, updated_at: new Date().toISOString() }
            : n
        )
      );
      setActiveTitle(result.title);
    } catch {
      // Silently fail — note will persist on next save
    }
  }, []);

  const handleEditorChange = useCallback(
    (value: string) => {
      setEditorContent(value);

      // Debounce chat content sync
      if (chatDebounceRef.current) clearTimeout(chatDebounceRef.current);
      chatDebounceRef.current = setTimeout(() => {
        setDebouncedContent(value);
      }, 300);

      // Debounce auto-save
      if (saveDebounceRef.current) clearTimeout(saveDebounceRef.current);
      saveDebounceRef.current = setTimeout(() => {
        const noteId = activeNoteRef.current;
        if (noteId) saveNote(noteId, value);
      }, 1000);
    },
    [saveNote]
  );

  // Title change → update the first line of content and save
  const handleTitleChange = useCallback(
    (newTitle: string) => {
      setActiveTitle(newTitle);
      setEditorContent((prev) => {
        // Replace first # heading line, or prepend one
        const lines = prev.split("\n");
        if (lines[0]?.startsWith("# ")) {
          lines[0] = `# ${newTitle}`;
        } else {
          lines.unshift(`# ${newTitle}`);
        }
        const updated = lines.join("\n");

        // Schedule save
        if (saveDebounceRef.current) clearTimeout(saveDebounceRef.current);
        saveDebounceRef.current = setTimeout(() => {
          const noteId = activeNoteRef.current;
          if (noteId) saveNote(noteId, updated);
        }, 1000);

        return updated;
      });
    },
    [saveNote]
  );

  // Select a note
  const handleSelectNote = useCallback(
    async (id: string) => {
      if (id === activeNoteId) return;

      // Save current note first
      if (activeNoteId) {
        if (saveDebounceRef.current) clearTimeout(saveDebounceRef.current);
        await saveNote(activeNoteId, editorContent);
      }

      // Load new note
      try {
        const data = await fetchNote(id);
        setActiveNoteId(id);
        setEditorContent(data.content);
        const note = notes.find((n) => n.id === id);
        setActiveTitle(note?.title ?? "Untitled");
      } catch {
        // Failed to load
      }
    },
    [activeNoteId, editorContent, notes, saveNote]
  );

  // Create a new note
  const handleCreateNote = useCallback(async () => {
    // Save current note first
    if (activeNoteId) {
      if (saveDebounceRef.current) clearTimeout(saveDebounceRef.current);
      await saveNote(activeNoteId, editorContent);
    }

    try {
      const created = await createNote("Untitled");
      const newNote: NoteFile = {
        id: created.id,
        title: created.title,
        updated_at: new Date().toISOString(),
      };
      setNotes((prev) => [newNote, ...prev]);
      setActiveNoteId(created.id);
      setActiveTitle(created.title);
      setEditorContent(`# ${created.title}\n\n`);
    } catch {
      // Failed to create
    }
  }, [activeNoteId, editorContent, saveNote]);

  // Refresh notes list manually
  const handleRefreshNotes = useCallback(async () => {
    try {
      const list = await fetchNotes();
      setNotes(list);
    } catch {
      // Backend unavailable
    }
  }, []);

  // Chat action: backend already wrote the file, just sync UI state
  const handleFileAction = useCallback(
    async (data: { action: string; note_id: string; title: string; markdown: string; updated_at: string }) => {
      if (data.action === "create_new") {
        // Add the new note to our list and switch to it
        const newNote: NoteFile = {
          id: data.note_id,
          title: data.title,
          updated_at: data.updated_at,
        };
        setNotes((prev) => [newNote, ...prev]);
        setActiveNoteId(data.note_id);
        setActiveTitle(data.title);
        // Load the full content from backend (already written)
        try {
          const note = await fetchNote(data.note_id);
          setEditorContent(note.content);
        } catch {
          setEditorContent(`# ${data.title}\n\n${data.markdown}`);
        }
      } else if (data.action === "edit_current") {
        // Reload the note content from backend (already appended)
        try {
          const note = await fetchNote(data.note_id);
          setEditorContent(note.content);
          setActiveTitle(data.title);
        } catch {
          // Fallback: append locally
          setEditorContent((prev) => prev.trimEnd() + "\n\n" + data.markdown);
        }
      }
      // Switch to research view if in reader mode
      if (viewMode === "reader") setViewMode("research");
    },
    [viewMode]
  );

  // Chat action: navigate to a note by id (from ActionCard click)
  const handleNavigateToNote = useCallback(
    (noteId: string) => {
      handleSelectNote(noteId);
      if (viewMode === "reader") setViewMode("research");
    },
    [handleSelectNote, viewMode]
  );

  // Open PDF reader mode
  const handleOpenReader = useCallback((name: string) => {
    setReaderPdfName(name);
    setViewMode("reader");
    setSidebarOpen(false);
  }, []);

  // Delete a note — optimistic: remove from UI first, backend in background
  const handleDeleteNote = useCallback(
    (id: string) => {
      const remaining = notes.filter((n) => n.id !== id);
      setNotes(remaining);

      // Switch away from deleted note immediately
      if (id === activeNoteId) {
        if (remaining.length > 0) {
          handleSelectNote(remaining[0].id);
        } else {
          handleCreateNote();
        }
      }

      // Backend delete in background — resync on failure
      deleteNote(id).catch(() => handleRefreshNotes());
    },
    [activeNoteId, notes, handleSelectNote, handleCreateNote, handleRefreshNotes]
  );

  return (
    <div className="h-screen w-screen overflow-hidden relative">
      {/* Header */}
      <div className="flex items-center h-12 px-3 border-b border-thin border-zinc-200 bg-white/80 backdrop-blur-md z-50 relative">
        <motion.button
          whileTap={{ scale: 0.98 }}
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="flex items-center justify-center h-8 w-8 rounded-md hover:bg-zinc-100 transition-colors duration-150"
        >
          <PanelLeft className="h-5 w-5 text-muted-foreground" />
        </motion.button>
        <span className="ml-2 text-base font-medium text-foreground">
          Origami
        </span>
        <div className="ml-auto">
          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={() =>
              setViewMode(viewMode === "database" ? "research" : "database")
            }
            className={`flex items-center justify-center h-8 w-8 rounded-md transition-colors duration-150 ${
              viewMode === "database"
                ? "bg-zinc-200 text-foreground"
                : "hover:bg-zinc-100 text-muted-foreground"
            }`}
          >
            <Database className="h-5 w-5" />
          </motion.button>
        </div>
      </div>

      {/* Main content */}
      <div className="h-[calc(100vh-3rem)] relative">
        {/* Document drawer overlay */}
        <AnimatePresence>
          {sidebarOpen && (
            <>
              {/* Backdrop */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                onClick={() => setSidebarOpen(false)}
                className="absolute inset-0 z-30 bg-black/5"
              />
              {/* Drawer */}
              <DocumentDrawer
                notes={notes}
                activeNoteId={activeNoteId}
                onSelectNote={handleSelectNote}
                onCreateNote={handleCreateNote}
                onDeleteNote={handleDeleteNote}
                onRefreshNotes={handleRefreshNotes}
                onOpenReader={handleOpenReader}
              />
            </>
          )}
        </AnimatePresence>

        {/* PDF reader overlays on top — panels stay mounted underneath */}
        {viewMode === "reader" && readerPdfName && (
          <div className="absolute inset-0 z-10 bg-background">
            <PdfReader
              name={readerPdfName}
              onBack={() => setViewMode("research")}
            />
          </div>
        )}

        {/* Database viewer overlay */}
        {viewMode === "database" && (
          <div className="absolute inset-0 z-10 bg-background">
            <DatabaseViewer onBack={() => setViewMode("research")} />
          </div>
        )}

        <ResizablePanelGroup orientation="horizontal" className="h-full">
          {/* Left: Markdown Editor */}
          <ResizablePanel defaultSize={55} minSize={30}>
            <MarkdownEditor
              value={editorContent}
              onChange={handleEditorChange}
              title={activeTitle}
              onTitleChange={handleTitleChange}
            />
          </ResizablePanel>

          <ResizableHandle className="w-px bg-zinc-200 hover:bg-zinc-300 transition-colors duration-150" />

          {/* Right: Chat (collapsible) */}
          <ResizablePanel
            defaultSize={45}
            minSize="350px"
            collapsible
            collapsedSize={0}
            panelRef={chatPanelRef}
            onResize={(size) => setChatOpen(size.asPercentage > 0)}
          >
            <ChatPanel
              currentNote={debouncedContent}
              chatId={chatId}
              activeTitle={activeTitle}
              activeNoteId={activeNoteId}
              onFileAction={handleFileAction}
              onNavigate={handleNavigateToNote}
            />
          </ResizablePanel>
        </ResizablePanelGroup>

        {/* Chat pull tab */}
        <motion.button
          onClick={toggleChat}
          initial={false}
          animate={{
            right: chatOpen ? -1 : 0,
            opacity: chatOpen ? 0 : 1,
          }}
          whileHover={{ width: 36 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          className="absolute top-1/2 -translate-y-1/2 z-20 flex items-center justify-center w-7 h-14 rounded-l-lg bg-zinc-100 border border-r-0 border-zinc-200 text-muted-foreground hover:text-foreground hover:bg-zinc-200 transition-colors cursor-pointer"
          style={{ pointerEvents: chatOpen ? "none" : "auto" }}
        >
          <ChevronLeft className="h-4 w-4" />
        </motion.button>
      </div>
    </div>
  );
}
