import { API_URL, apiFetch } from "./config";

export type SourceType =
  | "pdf"
  | "note"
  | "snippet"
  | "screenshot"
  | "photo"
  | "calendar"
  | "message";

export type Modality = "text" | "ocr" | "caption" | "transcript";

export interface LibraryItem {
  file_id: string;
  title: string;
  filename: string;
  source_type: SourceType;
  source_id: string;
  raw_ref: string;
  created_at: string;
  ingested_at: string;
  origin: string;
  trust: "trusted" | "untrusted";
  channel: string;
  tags: string[];
  segments: number;
  /** Segment counts per modality. One screenshot holds a caption and several OCR runs. */
  modalities: Partial<Record<Modality, number>>;
}

export interface LibraryFacets {
  source_type: Record<string, number>;
  trust: Record<string, number>;
  origin: Record<string, number>;
  /** Counted per segment, so this does not agree with the item total. */
  modality: Record<string, number>;
}

export interface Library {
  items: LibraryItem[];
  facets: LibraryFacets;
  total: number;
}

export async function fetchLibrary(): Promise<Library> {
  const response = await apiFetch(`${API_URL}/api/library`);
  if (!response.ok) {
    throw new Error(`Failed to fetch library: ${response.statusText}`);
  }
  return response.json();
}
