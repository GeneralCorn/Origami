export interface Document {
  id: string;
  name: string;
  uploadedAt: Date;
  size: number;
  status: "uploading" | "processing" | "ready" | "error";
}

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
