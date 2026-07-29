import { API_URL, apiFetch, withToken } from "./config";
import type {
  DigestSummary,
  DigestContent,
  ProcessResult,
  PendingScreenshot,
} from "@/types";

export async function uploadScreenshots(
  files: File[]
): Promise<Array<{ id: string; filename: string; status: string }>> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await apiFetch(`${API_URL}/api/screenshots/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`);
  }

  return response.json();
}

export async function fetchPendingScreenshots(): Promise<PendingScreenshot[]> {
  const response = await apiFetch(`${API_URL}/api/screenshots/pending`);
  if (!response.ok) {
    throw new Error(`Failed to fetch pending: ${response.statusText}`);
  }
  return response.json();
}

export async function processScreenshots(): Promise<ProcessResult> {
  const response = await apiFetch(`${API_URL}/api/screenshots/process`, {
    method: "POST",
  });

  if (response.status === 503) {
    const data = await response.json();
    throw new Error(data.detail || "Ollama is not running");
  }

  if (!response.ok) {
    throw new Error(`Process failed: ${response.statusText}`);
  }

  return response.json();
}

export async function fetchDigests(): Promise<DigestSummary[]> {
  const response = await apiFetch(`${API_URL}/api/digests`);
  if (!response.ok) {
    throw new Error(`Failed to fetch digests: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchDigestContent(
  week: string
): Promise<DigestContent> {
  const response = await apiFetch(`${API_URL}/api/digests/${week}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch digest: ${response.statusText}`);
  }
  return response.json();
}

export async function recategorize(
  week: string,
  screenshotName: string,
  newCategory: string
): Promise<void> {
  const response = await apiFetch(`${API_URL}/api/digests/${week}/recategorize`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      screenshot_name: screenshotName,
      new_category: newCategory,
    }),
  });
  if (!response.ok) {
    throw new Error(`Recategorize failed: ${response.statusText}`);
  }
}

export function screenshotUrl(filename: string): string {
  return withToken(`${API_URL}/api/screenshots/${filename}/file`);
}

export async function deleteScreenshot(name: string): Promise<void> {
  const response = await apiFetch(`${API_URL}/api/screenshots/${name}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Delete failed: ${response.statusText}`);
  }
}
