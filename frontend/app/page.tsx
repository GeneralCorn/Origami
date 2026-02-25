"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { fetchChats, createChat } from "@/lib/api/chats";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    async function init() {
      try {
        const chats = await fetchChats();
        if (chats.length > 0) {
          router.replace(`/chat-${chats[0].id}`);
        } else {
          const newChat = await createChat();
          router.replace(`/chat-${newChat.id}`);
        }
      } catch {
        // Backend unavailable — create a chat and redirect
        try {
          const newChat = await createChat();
          router.replace(`/chat-${newChat.id}`);
        } catch {
          // Fully offline — stay on this page
        }
      }
    }
    init();
  }, [router]);

  return (
    <div className="h-screen w-screen flex items-center justify-center">
      <p className="text-xs text-muted-foreground">Loading...</p>
    </div>
  );
}
