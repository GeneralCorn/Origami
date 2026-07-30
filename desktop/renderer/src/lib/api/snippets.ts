import type { SnippetResponse } from "@/types";

import { API_URL, apiFetch } from "./config";

export async function createSnippet(
  text: string,
  title: string,
  tags: string[]
): Promise<SnippetResponse> {
  const res = await apiFetch(`${API_URL}/api/snippets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, title, tags }),
  });
  if (!res.ok) throw new Error("Failed to create snippet");
  return res.json();
}
