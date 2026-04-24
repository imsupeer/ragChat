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
    <div
      className={`rounded-2xl border p-3 transition ${
        selected ? 'border-sky-500/40 bg-sky-500/10 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]' : 'border-border bg-white/[0.03] hover:border-white/10'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <button type="button" className="flex min-w-0 flex-1 items-start gap-3 text-left" onClick={onToggle}>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-2">
            <FileText className="h-4 w-4 shrink-0 text-gray-300" />
          </div>

          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-white">{document.filename}</div>
            <div className="mt-1 text-xs text-gray-400">{document.total_chunks} chunks indexed</div>
            {selected ? (
              <div className="mt-2 inline-flex rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-[11px] text-sky-100">
                Included in retrieval
              </div>
            ) : null}
          </div>
        </button>

        <button
          type="button"
          onClick={onDelete}
          className="rounded-xl p-2 text-gray-400 transition hover:bg-red-500/10 hover:text-red-300"
          aria-label={`Delete ${document.filename}`}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
