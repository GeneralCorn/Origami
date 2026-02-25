import { API_URL } from "./config";

export interface ChatInstance {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Array<{
    id: string;
    role: "user" | "assistant" | "system";
    parts: Array<{ type: string; text: string }>;
  }>;
}

export async function fetchChats(): Promise<ChatInstance[]> {
  const res = await fetch(`${API_URL}/api/chats`);
  if (!res.ok) throw new Error("Failed to fetch chats");
  return res.json();
}

export async function fetchChat(id: string): Promise<ChatDetail> {
  const res = await fetch(`${API_URL}/api/chats/${id}`);
  if (!res.ok) throw new Error("Failed to fetch chat");
  return res.json();
}

export async function createChat(
  title: string = "New Chat"
): Promise<{ id: string; title: string }> {
  const res = await fetch(`${API_URL}/api/chats`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to create chat");
  return res.json();
}

export async function saveChat(
  id: string,
  messages: Array<{
    id: string;
    role: string;
    parts: Array<{ type: string; text: string }>;
  }>,
  title?: string
): Promise<{ id: string; title: string; updated_at: string }> {
  const res = await fetch(`${API_URL}/api/chats/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, title }),
  });
  if (!res.ok) throw new Error("Failed to save chat");
  return res.json();
}

export async function deleteChat(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/chats/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete chat");
}
