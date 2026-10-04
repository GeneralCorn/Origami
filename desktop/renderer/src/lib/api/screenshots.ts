import { API_URL, apiFetch, withToken } from "./config";
import type {
  DigestSummary,
  DigestContent,
  ProcessResult,
  PendingScreenshot,
  ScreenshotDetail,
  ScreenshotStatus,
  UploadedScreenshot,
} from "@/types";

/**
 * Upload screenshots. The backend starts reading, classifying and filing
 * them as soon as the bytes land; `process=false` parks them as pending
 * instead, for an explicit "Process" later.
 */
export async function uploadScreenshots(
  files: File[],
  options: { process?: boolean } = {}
): Promise<UploadedScreenshot[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const params = options.process === false ? "?process=false" : "";
  const response = await apiFetch(`${API_URL}/api/screenshots/upload${params}`, {
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

export async function fetchScreenshotStatus(): Promise<ScreenshotStatus> {
  const response = await apiFetch(`${API_URL}/api/screenshots/status`);
  if (!response.ok) {
    throw new Error(`Failed to fetch status: ${response.statusText}`);
  }
  return response.json();
}

export async function processScreenshots(): Promise<ProcessResult> {
  const response = await apiFetch(`${API_URL}/api/screenshots/process`, {
    method: "POST",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Process failed: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchScreenshot(name: string): Promise<ScreenshotDetail> {
  const response = await apiFetch(`${API_URL}/api/screenshots/${encodeURIComponent(name)}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch screenshot: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchScreenshotText(name: string): Promise<string> {
  const response = await apiFetch(`${API_URL}/api/screenshots/${encodeURIComponent(name)}/text`);
  if (!response.ok) {
    throw new Error(`No text for this screenshot: ${response.statusText}`);
  }
  return response.text();
}

/** File a screenshot under another collection: store, note and digest move together. */
export async function changeScreenshotCollection(
  name: string,
  collectionId: string
): Promise<{ status: string; collection: string; note_id: string }> {
  const response = await apiFetch(`${API_URL}/api/screenshots/${encodeURIComponent(name)}/collection`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ collection_id: collectionId }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Move failed: ${response.statusText}`);
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

export async function fetchDigestContent(week: string): Promise<DigestContent> {
  const response = await apiFetch(`${API_URL}/api/digests/${week}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch digest: ${response.statusText}`);
  }
  return response.json();
}

/** Older name for changeScreenshotCollection; the week is no longer needed. */
export async function recategorize(
  _week: string,
  screenshotName: string,
  collectionId: string
): Promise<void> {
  await changeScreenshotCollection(screenshotName, collectionId);
}

export function screenshotUrl(filename: string): string {
  return withToken(`${API_URL}/api/screenshots/${encodeURIComponent(filename)}/file`);
}

/**
 * Notes and digests reference screenshots by the relative path the backend
 * writes, `../screenshots/<name>`. Resolve that to the served file, with the
 * launch token, so the image renders inside the editor preview.
 */
const RELATIVE_SCREENSHOT = /^(?:\.\.\/)?screenshots\/([^/?#]+)$/;

export function resolveScreenshotSrc(src: string): string {
  const match = RELATIVE_SCREENSHOT.exec(src);
  return match ? screenshotUrl(decodeURIComponent(match[1])) : src;
}

export async function deleteScreenshot(name: string): Promise<void> {
  const response = await apiFetch(`${API_URL}/api/screenshots/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Delete failed: ${response.statusText}`);
  }
}
