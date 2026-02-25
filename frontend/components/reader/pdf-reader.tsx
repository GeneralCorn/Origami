"use client";

import { ArrowLeft, FileText } from "lucide-react";
import { API_URL } from "@/lib/api/config";

interface PdfReaderProps {
  name: string;
  onBack: () => void;
}

export default function PdfReader({ name, onBack }: PdfReaderProps) {
  const pdfUrl = `${API_URL}/api/pdfs/${encodeURIComponent(name)}/file`;

  return (
    <div className="h-full flex flex-col">
      {/* Reader header */}
      <div className="flex items-center justify-between h-10 px-4 border-b border-thin border-zinc-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground truncate">
            {name}
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

      {/* PDF iframe */}
      <iframe
        src={pdfUrl}
        className="flex-1 w-full border-0"
        title={`${name}.pdf`}
      />
    </div>
  );
}
