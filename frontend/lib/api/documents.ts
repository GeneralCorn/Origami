import type { ChromaDocument, ChromaChunk } from "@/types";

import { API_URL } from "./config";

export async function fetchDocuments(): Promise<ChromaDocument[]> {
  const response = await fetch(`${API_URL}/api/documents`);
  if (!response.ok) {
    throw new Error(`Failed to fetch documents: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchDocumentChunks(fileId: string): Promise<ChromaChunk[]> {
  const response = await fetch(`${API_URL}/api/documents/${fileId}/chunks`);
  if (!response.ok) {
    throw new Error(`Failed to fetch chunks: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteDocument(fileId: string): Promise<{ deleted_chunks: number }> {
  const response = await fetch(`${API_URL}/api/documents/${fileId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete document: ${response.statusText}`);
  }
  return response.json();
}
