import type { NoteFile } from "@/types";

import { API_URL } from "./config";

export async function fetchNotes(): Promise<NoteFile[]> {
  const res = await fetch(`${API_URL}/api/notes`);
  if (!res.ok) throw new Error("Failed to fetch notes");
  return res.json();
}

export async function fetchNote(id: string): Promise<{ id: string; content: string }> {
  const res = await fetch(`${API_URL}/api/notes/${id}`);
  if (!res.ok) throw new Error("Failed to fetch note");
  return res.json();
}

export async function createNote(title: string = "Untitled"): Promise<{ id: string; title: string }> {
  const res = await fetch(`${API_URL}/api/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to create note");
  return res.json();
}

export async function updateNote(id: string, content: string): Promise<{ id: string; title: string }> {
  const res = await fetch(`${API_URL}/api/notes/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to update note");
  return res.json();
}

export async function deleteNote(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/notes/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete note");
}
