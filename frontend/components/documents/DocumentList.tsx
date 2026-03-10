'use client';

import { DocumentItem } from '@/components/documents/DocumentItem';
import type { DocumentItem as DocumentType } from '@/types/document';

export function DocumentList({
  documents,
  selectedIds,
  onToggle,
  onDelete,
}: {
  documents: DocumentType[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  onDelete: (id: string) => Promise<void>;
}) {
  if (!documents.length) {
    return <div className="rounded-xl border border-border bg-white/5 p-4 text-sm text-gray-400">No indexed documents yet.</div>;
  }

  return (
    <div className="space-y-2">
      {documents.map((document) => (
        <DocumentItem
          key={document.id}
          document={document}
          selected={selectedIds.includes(document.id)}
          onToggle={() => onToggle(document.id)}
          onDelete={() => onDelete(document.id)}
        />
      ))}
    </div>
  );
}
