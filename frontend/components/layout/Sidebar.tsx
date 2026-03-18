'use client';

import { DocumentUploader } from '@/components/documents/DocumentUploader';
import { DocumentList } from '@/components/documents/DocumentList';
import { UploadQueueList } from '@/components/documents/UploadQueueList';
import { ChatSessionList } from '@/components/chat/ChatSessionList';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { Loader } from '@/components/ui/Loader';
import type { DocumentItem, UploadQueueItem } from '@/types/document';
import type { ChatSession } from '@/types/chat';

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
  onSelectChat: (chatId: string) => void;
}) {
  return (
    <aside className="flex h-full w-full flex-col gap-4 bg-panel p-4">
      <div>
        <div className="mb-2 text-sm font-semibold text-white">Chats</div>
        <ChatSessionList chats={chats} activeChatId={activeChatId} onSelect={onSelectChat} onCreate={onCreateChat} onDelete={onDeleteChat} />
      </div>

      <div>
        <div className="mb-2 text-sm font-semibold text-white">Knowledge base</div>
        <p className="mb-4 text-xs text-gray-400">Multiple files enter a sequential queue, from smallest to largest.</p>
        <DocumentUploader onUpload={onUpload} />
      </div>

      {queueItems.length ? (
        <div>
          <div className="mb-2 text-sm font-semibold text-white">Upload queue</div>
          <UploadQueueList items={queueItems} />
        </div>
      ) : null}

      {error ? <ErrorMessage message={error} /> : null}
      {loading ? <Loader label="Loading documents..." /> : null}

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <DocumentList documents={documents} selectedIds={selectedIds} onToggle={onToggleDocument} onDelete={onDeleteDocument} />
      </div>
    </aside>
  );
}
