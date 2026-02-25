"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Database,
  ArrowLeft,
  Search,
  ChevronRight,
  FileText,
} from "lucide-react";
import { fetchDocuments } from "@/lib/api/documents";
import { fetchDocumentChunks } from "@/lib/api/documents";
import type { ChromaDocument, ChromaChunk } from "@/types";

interface DatabaseViewerProps {
  onBack: () => void;
}

export default function DatabaseViewer({ onBack }: DatabaseViewerProps) {
  const [documents, setDocuments] = useState<ChromaDocument[]>([]);
  const [chunks, setChunks] = useState<ChromaChunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  // Two-level navigation
  const [selectedDoc, setSelectedDoc] = useState<ChromaDocument | null>(null);
  const [expandedChunk, setExpandedChunk] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const docs = await fetchDocuments();
      setDocuments(docs);
    } catch {
      // Backend unavailable
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const handleSelectDoc = async (doc: ChromaDocument) => {
    setSelectedDoc(doc);
    setExpandedChunk(null);
    setSearch("");
    try {
      const c = await fetchDocumentChunks(doc.file_id);
      setChunks(c);
    } catch {
      setChunks([]);
    }
  };

  const handleBackToDocs = () => {
    setSelectedDoc(null);
    setChunks([]);
    setExpandedChunk(null);
    setSearch("");
  };

  const totalChunks = documents.reduce((s, d) => s + d.chunk_count, 0);

  const filteredDocs = search
    ? documents.filter((d) =>
        d.filename.toLowerCase().includes(search.toLowerCase())
      )
    : documents;

  const filteredChunks = search
    ? chunks.filter(
        (c) =>
          c.text.toLowerCase().includes(search.toLowerCase()) ||
          c.original_text.toLowerCase().includes(search.toLowerCase())
      )
    : chunks;

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between h-10 px-4 border-b border-thin border-zinc-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          {selectedDoc ? (
            <button
              onClick={handleBackToDocs}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-3 w-3" />
              <span>All Documents</span>
            </button>
          ) : (
            <Database className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <span className="text-xs font-medium text-foreground truncate">
            {selectedDoc ? selectedDoc.filename : "Knowledge Base"}
          </span>
          <span className="text-[10px] font-mono text-muted-foreground ml-1">
            {selectedDoc
              ? `${chunks.length} chunks`
              : `${documents.length} docs · ${totalChunks} chunks`}
          </span>
        </div>
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-zinc-100 transition-colors"
        >
          <ArrowLeft className="h-3 w-3" />
          <span>Research</span>
        </button>
      </div>

      {/* Search */}
      <div className="flex items-center px-4 py-2 border-b border-thin border-zinc-100 shrink-0">
        <Search className="h-3.5 w-3.5 text-muted-foreground mr-2" />
        <input
          type="text"
          placeholder={
            selectedDoc ? "Search chunks..." : "Search documents..."
          }
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 text-xs bg-transparent outline-none placeholder:text-muted-foreground/50"
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {loading ? (
          <div className="px-4 py-6 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-8 rounded bg-zinc-100 animate-pulse"
              />
            ))}
          </div>
        ) : selectedDoc ? (
          <ChunkTable
            chunks={filteredChunks}
            expandedChunk={expandedChunk}
            onToggle={(id) =>
              setExpandedChunk(expandedChunk === id ? null : id)
            }
          />
        ) : (
          <DocumentTable docs={filteredDocs} onSelect={handleSelectDoc} />
        )}
      </div>
    </div>
  );
}

/* ── Document-level table ── */

function DocumentTable({
  docs,
  onSelect,
}: {
  docs: ChromaDocument[];
  onSelect: (doc: ChromaDocument) => void;
}) {
  if (docs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Database className="h-6 w-6 mb-2 opacity-40" />
        <p className="text-xs">No documents in knowledge base</p>
      </div>
    );
  }

  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 bg-zinc-50/95 backdrop-blur-sm z-10">
        <tr className="border-b border-zinc-200">
          <th className="text-left px-4 py-2 font-medium text-muted-foreground">
            Filename
          </th>
          <th className="text-left px-4 py-2 font-medium text-muted-foreground">
            File ID
          </th>
          <th className="text-right px-4 py-2 font-medium text-muted-foreground">
            Chunks
          </th>
          <th className="w-8" />
        </tr>
      </thead>
      <tbody>
        {docs.map((doc) => (
          <tr
            key={doc.file_id}
            onClick={() => onSelect(doc)}
            className="border-b border-zinc-100 hover:bg-zinc-50 cursor-pointer transition-colors group"
          >
            <td className="px-4 py-2.5 font-medium">
              <div className="flex items-center gap-2">
                <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                {doc.filename}
              </div>
            </td>
            <td className="px-4 py-2.5 font-mono text-muted-foreground">
              {doc.file_id.slice(0, 8)}...
            </td>
            <td className="px-4 py-2.5 text-right tabular-nums">
              {doc.chunk_count}
            </td>
            <td className="px-2 py-2.5">
              <ChevronRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── Chunk-level table ── */

function ChunkTable({
  chunks,
  expandedChunk,
  onToggle,
}: {
  chunks: ChromaChunk[];
  expandedChunk: string | null;
  onToggle: (id: string) => void;
}) {
  if (chunks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Database className="h-6 w-6 mb-2 opacity-40" />
        <p className="text-xs">No chunks found</p>
      </div>
    );
  }

  return (
    <table className="w-full text-xs">
      <thead className="sticky top-0 bg-zinc-50/95 backdrop-blur-sm z-10">
        <tr className="border-b border-zinc-200">
          <th className="text-left px-4 py-2 font-medium text-muted-foreground w-16">
            #
          </th>
          <th className="text-left px-4 py-2 font-medium text-muted-foreground">
            Text
          </th>
        </tr>
      </thead>
      <tbody>
        {chunks.map((chunk) => {
          const isExpanded = expandedChunk === chunk.chunk_id;
          return (
            <tr
              key={chunk.chunk_id}
              onClick={() => onToggle(chunk.chunk_id)}
              className="border-b border-zinc-100 hover:bg-zinc-50 cursor-pointer transition-colors align-top"
            >
              <td className="px-4 py-2.5 tabular-nums text-muted-foreground">
                {chunk.chunk_index}
              </td>
              <td className="px-4 py-2.5">
                <AnimatePresence mode="wait" initial={false}>
                  {isExpanded ? (
                    <motion.div
                      key="expanded"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="space-y-3"
                    >
                      <div>
                        <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">
                          Original
                        </p>
                        <p className="text-xs leading-relaxed whitespace-pre-wrap text-foreground">
                          {chunk.original_text}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1">
                          Contextualized
                        </p>
                        <p className="text-xs leading-relaxed whitespace-pre-wrap text-foreground">
                          {chunk.text}
                        </p>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.p
                      key="collapsed"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.15 }}
                      className="truncate max-w-xl"
                    >
                      {chunk.original_text.slice(0, 120)}
                      {chunk.original_text.length > 120 && "..."}
                    </motion.p>
                  )}
                </AnimatePresence>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
