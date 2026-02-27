"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { DefaultChatTransport } from "ai";
import { useChat } from "@ai-sdk/react";
import { Pencil, ChevronDown, Plus, MessageSquare } from "lucide-react";
import Message, { type ActionHandlers } from "./message";
import ChatInput from "./chat-input";
import {
  fetchChats,
  fetchChat,
  saveChat,
  createChat,
  type ChatInstance,
} from "@/lib/api/chats";

// Stable refs — created once outside the component so that
// the React compiler never sees a ref access during render.
const noteRef = { current: "" };
const allowEditsRef = { current: false };
const activeTitleRef = { current: "" };
const activeNoteIdRef = { current: "" as string | null };

const transport = new DefaultChatTransport({
  api: "/api/chat",
  body: () => ({
    current_note: noteRef.current,
    allow_edits: allowEditsRef.current,
    active_note_title: activeTitleRef.current,
    active_note_id: activeNoteIdRef.current,
  }),
});

interface FileActionData {
  action: string;
  note_id: string;
  title: string;
  filename: string;
  markdown: string;
  updated_at: string;
}

interface ChatPanelProps {
  currentNote: string;
  chatId?: string;
  activeTitle?: string;
  activeNoteId?: string | null;
  onFileAction?: (data: FileActionData) => void;
  onNavigate?: (noteId: string) => void;
}

export default function ChatPanel({
  currentNote,
  chatId,
  activeTitle = "",
  activeNoteId = null,
  onFileAction,
  onNavigate,
}: ChatPanelProps) {
  const [allowEdits, setAllowEdits] = useState(false);
  const [chatList, setChatList] = useState<ChatInstance[]>([]);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [currentChatTitle, setCurrentChatTitle] = useState("New Chat");

  // Manage active chat as local state to avoid full-page remount on switch
  const [activeChatId, setActiveChatId] = useState(chatId);

  // Keep module-level refs in sync
  useEffect(() => {
    noteRef.current = currentNote;
  }, [currentNote]);
  useEffect(() => {
    allowEditsRef.current = allowEdits;
  }, [allowEdits]);
  useEffect(() => {
    activeTitleRef.current = activeTitle;
  }, [activeTitle]);
  useEffect(() => {
    activeNoteIdRef.current = activeNoteId;
  }, [activeNoteId]);

  const { messages, sendMessage, status, setMessages } = useChat({ transport });

  const isLoading = status === "streaming" || status === "submitted";

  // Load saved messages when active chat changes
  useEffect(() => {
    if (!activeChatId) return;
    async function loadChat() {
      try {
        const data = await fetchChat(activeChatId!);
        if (data.messages.length > 0) {
          setMessages(
            data.messages.map((m) => ({
              id: m.id,
              role: m.role as "user" | "assistant",
              parts: m.parts.map((p) => ({
                type: p.type as "text" | "reasoning",
                text: p.text,
              })),
            }))
          );
        }
        setCurrentChatTitle(data.title || "New Chat");
      } catch {
        // Chat not found or backend down
      }
    }
    loadChat();
  }, [activeChatId, setMessages]);

  // Save messages after each assistant response completes
  const prevStatusRef = useRef(status);
  useEffect(() => {
    const wasActive =
      prevStatusRef.current === "streaming" ||
      prevStatusRef.current === "submitted";
    const isNowReady = status === "ready";

    if (wasActive && isNowReady && activeChatId && messages.length > 0) {
      const serialized = messages.map((m) => ({
        id: m.id,
        role: m.role,
        parts: m.parts
          .filter((p) => p.type === "text" || p.type === "reasoning")
          .map((p) => ({
            type: p.type,
            text: "text" in p ? p.text : "",
          })),
      }));
      saveChat(activeChatId, serialized)
        .then((result) => setCurrentChatTitle(result.title))
        .catch(() => {});
    }
    prevStatusRef.current = status;
  }, [status, activeChatId, messages]);

  // Load chat list for dropdown
  const loadChatList = useCallback(async () => {
    try {
      const list = await fetchChats();
      setChatList(list);
    } catch {
      // Backend unavailable
    }
  }, []);

  useEffect(() => {
    loadChatList();
  }, [loadChatList]);

  // Auto-scroll to bottom on new messages (scroll the container, not the page)
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevMsgCount = useRef(0);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || messages.length === 0) return;
    // Instant jump when loading a chat (0 → many), smooth for incremental messages
    const isLoad = prevMsgCount.current === 0 && messages.length > 1;
    el.scrollTo({ top: el.scrollHeight, behavior: isLoad ? "instant" : "smooth" });
    prevMsgCount.current = messages.length;
  }, [messages]);

  const handleSend = async (text: string) => {
    await sendMessage({ text });
  };

  const switchChat = useCallback((id: string, title?: string) => {
    prevMsgCount.current = 0;
    setMessages([]);
    setActiveChatId(id);
    setCurrentChatTitle(title || "New Chat");
    window.history.replaceState(null, "", `/chat-${id}`);
  }, [setMessages]);

  const handleNewChat = async () => {
    try {
      const created = await createChat();
      setDropdownOpen(false);
      switchChat(created.id);
    } catch {
      // Failed to create
    }
  };

  const handleSelectChat = (id: string, title?: string) => {
    setDropdownOpen(false);
    switchChat(id, title);
  };

  const handleToggleDropdown = () => {
    const next = !dropdownOpen;
    setDropdownOpen(next);
    if (next) loadChatList();
  };

  const actionHandlers: ActionHandlers = {
    onFileAction,
    onNavigate,
    activeTitle,
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between h-10 px-4 border-b border-thin border-border shrink-0">
        <span className="text-xs font-medium text-muted-foreground tracking-wide uppercase">
          Chat
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setAllowEdits(!allowEdits)}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors ${
              allowEdits
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:bg-accent"
            }`}
          >
            <Pencil className="h-3 w-3" />
            <span>{allowEdits ? "Edit" : "Chat"}</span>
          </button>

          {/* Chat instance dropdown */}
          <div className="relative">
            <button
              onClick={handleToggleDropdown}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <span className="max-w-[100px] truncate">{currentChatTitle}</span>
              <ChevronDown className="h-3 w-3" />
            </button>

            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setDropdownOpen(false)}
                />
                <div className="absolute right-0 top-full mt-1 z-50 w-56 rounded-md border border-border bg-popover shadow-lg py-1">
                  <button
                    onClick={handleNewChat}
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
                  >
                    <Plus className="h-3 w-3" />
                    New Chat
                  </button>
                  <div className="border-t border-border/50 my-1" />
                  <div className="max-h-48 overflow-y-auto">
                    {chatList.length === 0 ? (
                      <p className="px-3 py-1.5 text-xs text-muted-foreground">
                        No chats yet
                      </p>
                    ) : (
                      chatList.map((chat) => (
                        <button
                          key={chat.id}
                          onClick={() => handleSelectChat(chat.id, chat.title)}
                          className={`flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-accent/50 transition-colors ${
                            chat.id === activeChatId
                              ? "text-foreground font-medium bg-accent/50"
                              : "text-muted-foreground"
                          }`}
                        >
                          <MessageSquare className="h-3 w-3 flex-shrink-0" />
                          <span className="truncate">{chat.title}</span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Messages — scrollable area */}
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto">
        <div className="px-6 max-w-2xl mx-auto">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-32">
              <p className="text-xs text-muted-foreground">
                Ask a question about your research notes
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {messages.map((message) => (
                <Message
                  key={message.id}
                  message={message}
                  isStreaming={
                    isLoading &&
                    message.id === messages[messages.length - 1]?.id
                  }
                  actionHandlers={actionHandlers}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Input — pinned to bottom */}
      <div className="border-t border-thin border-border shrink-0">
        <ChatInput onSend={handleSend} isLoading={isLoading} />
      </div>
    </div>
  );
}
