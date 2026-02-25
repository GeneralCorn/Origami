import type { UploadResponse, PersistedPDF } from "@/types";
import { API_URL } from "./config";

export async function uploadPDF(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_URL}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`);
  }

  return response.json();
}

export async function fetchTags(): Promise<string[]> {
  const response = await fetch(`${API_URL}/api/tags`);
  if (!response.ok) {
    throw new Error(`Failed to fetch tags: ${response.statusText}`);
  }
  return response.json();
}

export async function confirmUpload(
  id: string,
  name: string,
  tags: string[] = []
): Promise<{ id: string; filename: string; size: number; total_chunks: number; status: string }> {
  const response = await fetch(`${API_URL}/api/upload/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, name, tags }),
  });

  if (!response.ok) {
    throw new Error(`Confirm failed: ${response.statusText}`);
  }

  return response.json();
}

export async function fetchPDFs(): Promise<PersistedPDF[]> {
  const response = await fetch(`${API_URL}/api/pdfs`);
  if (!response.ok) {
    throw new Error(`Failed to fetch PDFs: ${response.statusText}`);
  }
  return response.json();
}

export async function deletePDF(name: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/pdfs/${name}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete PDF: ${response.statusText}`);
  }
}
