'use client';

import { useState } from 'react';
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
  const [pendingDelete, setPendingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleConfirmDelete() {
    setDeleting(true);
    try {
      await onDelete();
      setPendingDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div
      data-testid="document-item"
      data-filename={document.filename}
      className={`rounded-2xl border p-3 transition ${
        selected ? 'border-sky-500/40 bg-sky-500/10 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]' : 'border-border bg-white/[0.03] hover:border-white/10'
      }`}
    >
      {pendingDelete ? (
        <div className="space-y-3" role="group" aria-labelledby={`document-delete-confirm-${document.id}`}>
          <p id={`document-delete-confirm-${document.id}`} className="text-xs leading-5 text-gray-300" data-testid="document-delete-confirm">
            Delete this document from the workspace? Indexed chunks and metadata will be removed.
          </p>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setPendingDelete(false)}
              aria-label="Cancel document deletion"
              className="focus-ring rounded-xl border border-border px-2.5 py-1.5 text-xs text-gray-300 transition hover:text-white"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleConfirmDelete()}
              disabled={deleting}
              aria-label="Confirm delete document"
              className="focus-ring rounded-xl border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-xs text-red-200 transition hover:border-red-500/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {deleting ? 'Deleting...' : 'Delete document'}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <button
            type="button"
            className="focus-ring flex min-w-0 flex-1 items-start gap-3 rounded-lg text-left"
            onClick={onToggle}
            aria-pressed={selected}
            aria-label={`${selected ? 'Deselect' : 'Select'} ${document.filename} for retrieval`}
          >
            <div className="rounded-2xl border border-white/10 bg-white/5 p-2">
              <FileText className="h-4 w-4 shrink-0 text-gray-300" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-white">{document.filename}</div>
              <div className="mt-1 text-xs text-gray-400">{document.total_chunks} chunks indexed</div>
              {selected ? (
                <div className="mt-2 app-badge-accent">Included in retrieval</div>
              ) : null}
            </div>
          </button>

          <button
            type="button"
            onClick={() => setPendingDelete(true)}
            className="focus-ring rounded-xl p-2 text-gray-400 transition hover:bg-red-500/10 hover:text-red-300"
            aria-label={`Delete document ${document.filename}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
