'use client';

import { FileText, Trash2 } from 'lucide-react';
import type { DocumentItem as DocumentType } from '@/types/document';

export function DocumentItem({
  document,
  selected,
  onToggle,
  onDelete,
}: {
  document: DocumentType;
  selected: boolean;
  onToggle: () => void;
  onDelete: () => Promise<void>;
}) {
  return (
    <div className={`rounded-xl border p-3 transition ${selected ? 'border-sky-500 bg-sky-500/10' : 'border-border bg-white/5'}`}>
      <div className="flex items-start justify-between gap-3">
        <button type="button" className="flex flex-1 items-start gap-3 text-left" onClick={onToggle}>
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-gray-300" />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{document.filename}</div>
            <div className="text-xs text-gray-400">{document.total_chunks} chunks</div>
          </div>
        </button>

        <button
          type="button"
          onClick={onDelete}
          className="rounded-lg p-2 text-gray-400 transition hover:bg-red-500/10 hover:text-red-300"
          aria-label={`Delete ${document.filename}`}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
