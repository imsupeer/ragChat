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
      className={`w-full rounded-[24px] border border-dashed p-5 text-left transition ${
        isDragActive
          ? 'border-sky-400 bg-sky-400/10 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]'
          : 'border-border bg-white/[0.03] hover:border-sky-500/30 hover:bg-white/[0.05]'
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex items-center gap-3">
        <div className="rounded-2xl border border-white/10 bg-white/10 p-3">
          <FileUp className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-medium text-white">Upload documents</div>
          <div className="text-xs text-gray-400">PDF, TXT, Markdown | multiple files supported</div>
        </div>
      </div>
    </button>
  );
}
