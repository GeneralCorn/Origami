export interface UploadResponse {
  id: string;
  filename: string;
  suggested_name?: string;
  suggested_title?: string;
  size?: number;
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

export interface ProcessResult {
  processed: number;
  needs_review: number;
  results: Array<{
    filename: string;
    title?: string;
    category?: string;
    confidence?: string;
    error?: string;
  }>;
}

export interface PendingScreenshot {
  filename: string;
  size: number;
  uploaded_at: string;
}
