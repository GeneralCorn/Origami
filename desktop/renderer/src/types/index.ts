export interface UploadResponse {
  id: string;
  filename: string;
  suggested_name?: string;
  suggested_title?: string;
  size?: number;
  status: string;
  duplicate?: boolean;
}

export interface SnippetResponse {
  id: string;
  title?: string;
  total_chunks?: number;
  tags?: string[];
  status: string;
  duplicate?: boolean;
}

export interface PersistedPDF {
  name: string;
  filename: string;
  size: number;
  uploaded_at: string;
}

export interface ChromaDocument {
  file_id: string;
  filename: string;
  title?: string;
  /** pdf | note | snippet | screenshot | ... — the knowledge base is no longer PDFs only. */
  source_type: string;
  chunk_count: number;
  tags: string[];
  publish_date?: string;
}

export interface ChromaChunk {
  chunk_id: string;
  chunk_index: number;
  text: string;
  original_text: string;
  page_start?: number;
  page_end?: number;
}

export interface NoteFile {
  id: string;
  title: string;
  updated_at: string;
}

export interface DigestSummary {
  week: string;
  label: string;
  entry_count: number;
  needs_review: number;
}

export interface DigestContent {
  week: string;
  content: string;
}

export type ScreenshotStage =
  | "queued"
  | "reading"
  | "classifying"
  | "indexing"
  | "captioning"
  | "done"
  | "error";

/** One screenshot's progress through the pipeline, as /screenshots/status reports it. */
export interface ScreenshotJob {
  filename: string;
  stage: ScreenshotStage;
  title: string;
  collection: string;
  confidence: number;
  method: string;
  ocr_engine: string;
  captioned: boolean;
  error: string;
  started_at: string;
  updated_at: string;
}

export interface ScreenshotStatus {
  jobs: ScreenshotJob[];
  pending: number;
  engines: {
    /** "apple_vision" | "rapidocr" | null when text must come from the VLM. */
    ocr: string | null;
    /** Whether Ollama is up with the vision model pulled. */
    vision: boolean;
  };
}

export interface ProcessResult {
  processed: number;
  failed: number;
  needs_review: number;
  results: ScreenshotJob[];
}

export interface UploadedScreenshot {
  id: string;
  filename: string;
  original_name?: string;
  size?: number;
  status: "processing" | "pending" | "duplicate" | string;
  duplicate?: boolean;
}

export interface PendingScreenshot {
  filename: string;
  size: number;
  uploaded_at: string;
  stage: ScreenshotStage | null;
}

export interface ScreenshotRecord {
  screenshot: string;
  title: string;
  collection: string;
  text: string;
  content_lines: string[];
  note_id?: string;
  week?: string;
  processed_at?: string;
  classification?: { collection: string; confidence: number; method: string };
  vision?: { title: string; description: string; source_app: string; confidence: string } | null;
  ocr?: { engine: string; mean_confidence: number; lines: Array<{ text: string; confidence: number }> } | null;
}

export interface ScreenshotDetail {
  filename: string;
  on_disk: boolean;
  record: ScreenshotRecord | null;
  indexed: boolean;
  collection: string | null;
  title: string | null;
  job: ScreenshotJob | null;
}

/** A category screenshots are filed into, backed by a note. */
export interface Collection {
  id: string;
  name: string;
  description: string;
  keywords: string[];
  note_id: string;
  builtin: boolean;
}
