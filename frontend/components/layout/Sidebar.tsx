'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { ChatSessionList } from '@/components/chat/ChatSessionList';
import { DocumentList } from '@/components/documents/DocumentList';
import { DocumentUploader } from '@/components/documents/DocumentUploader';
import { UploadQueueList } from '@/components/documents/UploadQueueList';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { Skeleton } from '@/components/ui/Skeleton';
import type { ChatSession } from '@/types/chat';
import type { DocumentItem, UploadQueueItem } from '@/types/document';

export function Sidebar({
  documents,
  loading,
  error,
  selectedIds,
  queueItems,
  chats,
  activeChatId,
  onUpload,
  onDeleteDocument,
  onToggleDocument,
  onCreateChat,
  onDeleteChat,
  onRenameChat,
  onSelectChat,
}: {
  documents: DocumentItem[];
  loading: boolean;
  error: string | null;
  selectedIds: string[];
  queueItems: UploadQueueItem[];
  chats: ChatSession[];
  activeChatId: string | null;
  onUpload: (files: File[]) => Promise<void>;
  onDeleteDocument: (id: string) => Promise<void>;
  onToggleDocument: (id: string) => void;
  onCreateChat: () => Promise<void>;
  onDeleteChat: (chatId: string) => Promise<void>;
  onRenameChat: (chatId: string, title: string) => Promise<void>;
  onSelectChat: (chatId: string) => void;
}) {
  const [queueVisible, setQueueVisible] = useState(true);
  const [documentsVisible, setDocumentsVisible] = useState(true);

  return (
    <aside className="flex h-full w-full flex-col gap-4 overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] p-4">
      <div className="rounded-[24px] border border-border bg-black/15 p-4">
        <div className="mb-2 text-sm font-semibold text-white">Chats</div>
        <ChatSessionList
          chats={chats}
          activeChatId={activeChatId}
          onSelect={onSelectChat}
          onCreate={onCreateChat}
          onDelete={onDeleteChat}
          onRename={onRenameChat}
        />
      </div>

      <div className="rounded-[24px] border border-border bg-black/15 p-4">
        <div className="mb-2 text-sm font-semibold text-white">Knowledge base</div>
        <p className="mb-4 text-xs text-gray-400">
          Upload files, recover indexing jobs after refresh, and constrain retrieval with document selection.
        </p>
        <DocumentUploader onUpload={onUpload} />
      </div>

      {queueItems.length ? (
        <div className="rounded-[24px] border border-border bg-black/15 p-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-white">Upload queue</div>
            <button
              type="button"
              onClick={() => setQueueVisible((current) => !current)}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.03] px-3 py-1 text-xs text-gray-300 transition hover:text-white"
            >
              {queueVisible ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              {queueVisible ? 'Hide' : 'Show'}
            </button>
          </div>
          {queueVisible ? <UploadQueueList items={queueItems} /> : null}
        </div>
      ) : null}

      {error ? <ErrorMessage message={error} /> : null}

      <div className="pr-1 pb-2">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-semibold text-white">Indexed documents</div>
          <div className="flex items-center gap-3">
            <div className="text-xs text-gray-500">{selectedIds.length} selected</div>
            <button
              type="button"
              onClick={() => setDocumentsVisible((current) => !current)}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.03] px-3 py-1 text-xs text-gray-300 transition hover:text-white"
            >
              {documentsVisible ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              {documentsVisible ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>

        {!documentsVisible ? null : loading ? (
          <div className="space-y-2">
            <Skeleton className="h-20 w-full rounded-2xl" />
            <Skeleton className="h-20 w-full rounded-2xl" />
            <Skeleton className="h-20 w-full rounded-2xl" />
          </div>
        ) : (
          <DocumentList documents={documents} selectedIds={selectedIds} onToggle={onToggleDocument} onDelete={onDeleteDocument} />
        )}
      </div>
    </aside>
  );
}
