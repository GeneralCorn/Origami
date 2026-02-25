"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload } from "lucide-react";
import { uploadPDF, confirmUpload } from "@/lib/api/upload";
import type { UploadResponse } from "@/types";
import NamingDialog from "./naming-dialog";

interface UploadDropzoneProps {
  onIngestionStarted: (fileId: string, filename: string, totalChunks: number) => void;
}

export default function UploadDropzone({ onIngestionStarted }: UploadDropzoneProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [pendingUpload, setPendingUpload] = useState<{
    response: UploadResponse;
    file: File;
  } | null>(null);

  const [duplicateMsg, setDuplicateMsg] = useState<string | null>(null);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setIsUploading(true);
    setDuplicateMsg(null);
    try {
      const response = await uploadPDF(file);
      if (response.duplicate) {
        setDuplicateMsg(`Already uploaded as ${response.filename}`);
        setTimeout(() => setDuplicateMsg(null), 4000);
      } else {
        setPendingUpload({ response, file });
      }
    } catch {
      // Upload failed silently
    } finally {
      setIsUploading(false);
    }
  }, []);

  const handleConfirm = useCallback(
    async (name: string, tags: string[]) => {
      if (!pendingUpload) return;
      try {
        const result = await confirmUpload(pendingUpload.response.id, name, tags);
        onIngestionStarted(result.id, result.filename, result.total_chunks ?? 0);
      } catch {
        // Confirm failed silently
      }
      setPendingUpload(null);
    },
    [pendingUpload, onIngestionStarted]
  );

  const handleCancel = useCallback(() => {
    setPendingUpload(null);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    disabled: isUploading,
  });

  return (
    <>
      <div
        {...getRootProps()}
        className={`cursor-pointer rounded-md border border-dashed border-zinc-300 px-4 py-5 text-center transition-all duration-150 hover:bg-zinc-50 active:scale-[0.98] ${isDragActive ? "border-zinc-500 bg-zinc-50" : ""} ${isUploading ? "cursor-not-allowed opacity-50" : ""}`}
      >
        <input {...getInputProps()} />
        <Upload className={`mx-auto h-4 w-4 ${duplicateMsg ? "text-amber-500" : "text-muted-foreground"}`} />
        <p className={`mt-1.5 text-xs ${duplicateMsg ? "text-amber-600" : "text-muted-foreground"}`}>
          {duplicateMsg ?? (isUploading ? "Analyzing PDF..." : "Drop PDF or click")}
        </p>
      </div>

      <NamingDialog
        open={pendingUpload !== null}
        suggestedName={pendingUpload?.response.suggested_name ?? ""}
        originalFilename={pendingUpload?.file.name ?? ""}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </>
  );
}
