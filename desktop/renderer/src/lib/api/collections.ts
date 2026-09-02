import { API_URL, apiFetch } from "./config";
import type { Collection } from "@/types";

export async function fetchCollections(): Promise<Collection[]> {
  const response = await apiFetch(`${API_URL}/api/collections`);
  if (!response.ok) {
    throw new Error(`Failed to fetch collections: ${response.statusText}`);
  }
  return response.json();
}

export async function createCollection(
  name: string,
  description = "",
  keywords: string[] = []
): Promise<Collection> {
  const response = await apiFetch(`${API_URL}/api/collections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, keywords }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to create collection: ${response.statusText}`);
  }
  return response.json();
}

export async function updateCollection(
  id: string,
  changes: Partial<Pick<Collection, "name" | "description" | "keywords">>
): Promise<Collection> {
  const response = await apiFetch(`${API_URL}/api/collections/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  if (!response.ok) {
    throw new Error(`Failed to update collection: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteCollection(id: string): Promise<void> {
  const response = await apiFetch(`${API_URL}/api/collections/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to delete collection: ${response.statusText}`);
  }
}
