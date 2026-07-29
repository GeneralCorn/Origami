import { useEffect } from "react";
import { useNavigate } from "@/lib/router";

import { fetchChats, createChat } from "@/lib/api/chats";

export default function HomePage() {
  const navigate = useNavigate();

  useEffect(() => {
    async function init() {
      try {
        const chats = await fetchChats();
        if (chats.length > 0) {
          navigate(`/c/${chats[0].id}`, { replace: true });
          return;
        }
      } catch {
        // Backend unreachable — fall through and try to create a chat
      }
      try {
        const created = await createChat();
        navigate(`/c/${created.id}`, { replace: true });
      } catch {
        // Fully offline — stay on this page
      }
    }
    init();
  }, [navigate]);

  return (
    <div className="h-screen w-screen flex items-center justify-center">
      <p className="text-xs text-muted-foreground">Loading...</p>
    </div>
  );
}
