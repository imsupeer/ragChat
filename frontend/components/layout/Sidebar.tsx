'use client';

import { DocumentUploader } from '@/components/documents/DocumentUploader';
import { DocumentList } from '@/components/documents/DocumentList';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { Loader } from '@/components/ui/Loader';
import type { DocumentItem } from '@/types/document';

export function Sidebar({
  documents,
  loading,
  error,
  uploading,
  selectedIds,
  onUpload,
  onDelete,
  onToggle,
}: {
  documents: DocumentItem[];
  loading: boolean;
  error: string | null;
  uploading: boolean;
  selectedIds: string[];
  onUpload: (file: File) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onToggle: (id: string) => void;
}) {
  return (
    <aside className="flex h-full w-full flex-col gap-4 border-r border-border bg-panel p-4 lg:w-[320px]">
      <div>
        <div className="mb-2 text-sm font-semibold text-white">Knowledge base</div>
        <p className="mb-4 text-xs text-gray-400">Select one or more indexed documents to scope retrieval.</p>
        <DocumentUploader onUpload={onUpload} uploading={uploading} />
      </div>

      {error ? <ErrorMessage message={error} /> : null}
      {loading ? <Loader label="Loading documents..." /> : null}

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <DocumentList documents={documents} selectedIds={selectedIds} onToggle={onToggle} onDelete={onDelete} />
      </div>
    </aside>
  );
}
