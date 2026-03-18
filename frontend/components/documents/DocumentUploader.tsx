'use client';

import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { FileUp } from 'lucide-react';

export function DocumentUploader({ onUpload }: { onUpload: (files: File[]) => Promise<void> }) {
  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length) {
        await onUpload(acceptedFiles);
      }
    },
    [onUpload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
    accept: {
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md', '.markdown'],
    },
  });

  return (
    <button
      type="button"
      {...getRootProps()}
      className={`w-full rounded-2xl border border-dashed p-4 text-left transition ${
        isDragActive ? 'border-sky-400 bg-sky-400/10' : 'border-border bg-white/5 hover:bg-white/10'
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-white/10 p-2">
          <FileUp className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-medium">Upload documents</div>
          <div className="text-xs text-gray-400">PDF, TXT, Markdown — multiple files supported</div>
        </div>
      </div>
    </button>
  );
}
