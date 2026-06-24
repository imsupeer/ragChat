'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { ChatSessionList } from '@/components/chat/ChatSessionList';
import { DocumentList } from '@/components/documents/DocumentList';
import { DocumentUploader } from '@/components/documents/DocumentUploader';
import { UploadQueueList } from '@/components/documents/UploadQueueList';
import { ModelAdvisor } from '@/components/models/ModelAdvisor';
import { HardwareTelemetryPanel } from '@/components/hardware/HardwareTelemetryPanel';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { Skeleton } from '@/components/ui/Skeleton';
import type { ChatSession } from '@/types/chat';
import type { DocumentItem, UploadQueueItem } from '@/types/document';
import type { ModelSettingsState, ModelRuntimeStatus } from '@/types/models';
import type { HardwareTelemetrySnapshot } from '@/types/hardware';

export function Sidebar({
  documents,
  loading,
  error,
  selectedIds,
  queueItems,
  chats,
  activeChatId,
  isStreaming,
  modelSettings,
  modelSettingsLoading,
  modelSettingsError,
  modelActionMessage,
  modelRuntime,
  modelRuntimeLoading,
  modelRuntimeError,
  modelRuntimeActionMessage,
  modelRuntimeActionLoading,
  onApplyChatModel,
  onResetChatModel,
  onRefreshModelRuntime,
  onPreloadActiveModel,
  onUnloadActiveModel,
  hardwareTelemetry,
  hardwareTelemetryLoading,
  hardwareTelemetryError,
  onRefreshHardwareTelemetry,
  onUpload,
  onDeleteDocument,
  onToggleDocument,
  onCreateChat,
  onDeleteChat,
  onRenameChat,
  onSelectChat,
  onRetryUploadJob,
}: {
  documents: DocumentItem[];
  loading: boolean;
  error: string | null;
  selectedIds: string[];
  queueItems: UploadQueueItem[];
  chats: ChatSession[];
  activeChatId: string | null;
  isStreaming: boolean;
  modelSettings: ModelSettingsState | null;
  modelSettingsLoading: boolean;
  modelSettingsError: string | null;
  modelActionMessage: string | null;
  modelRuntime: ModelRuntimeStatus | null;
  modelRuntimeLoading: boolean;
  modelRuntimeError: string | null;
  modelRuntimeActionMessage: string | null;
  modelRuntimeActionLoading: 'preload' | 'unload' | null;
  onApplyChatModel: (chatModel: string) => Promise<void>;
  onResetChatModel: () => Promise<void>;
  onRefreshModelRuntime: () => Promise<void>;
  onPreloadActiveModel: () => Promise<void>;
  onUnloadActiveModel: () => Promise<void>;
  hardwareTelemetry: HardwareTelemetrySnapshot | null;
  hardwareTelemetryLoading: boolean;
  hardwareTelemetryError: string | null;
  onRefreshHardwareTelemetry: () => Promise<void>;
  onUpload: (files: File[]) => Promise<void>;
  onDeleteDocument: (id: string) => Promise<void>;
  onToggleDocument: (id: string) => void;
  onCreateChat: () => Promise<void>;
  onDeleteChat: (chatId: string) => Promise<void>;
  onRenameChat: (chatId: string, title: string) => Promise<void>;
  onSelectChat: (chatId: string) => void;
  onRetryUploadJob?: (localId: string) => Promise<void>;
}) {
  const [queueVisible, setQueueVisible] = useState(true);
  const [documentsVisible, setDocumentsVisible] = useState(true);

  return (
    <aside aria-label="Documents and chats" className="flex h-full w-full flex-col gap-4 overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] p-4">
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
              aria-expanded={queueVisible}
              aria-label={queueVisible ? 'Hide upload queue' : 'Show upload queue'}
              className="focus-ring inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.03] px-3 py-1 text-xs text-gray-300 transition hover:text-white"
            >
              {queueVisible ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              {queueVisible ? 'Hide' : 'Show'}
            </button>
          </div>
          {queueVisible ? <UploadQueueList items={queueItems} onRetry={(localId) => void onRetryUploadJob?.(localId)} /> : null}
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
              aria-expanded={documentsVisible}
              aria-label={documentsVisible ? 'Hide indexed documents' : 'Show indexed documents'}
              className="focus-ring inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.03] px-3 py-1 text-xs text-gray-300 transition hover:text-white"
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
          <>
            <p className="mb-3 text-xs leading-5 text-gray-500">
              Select documents to narrow retrieval. Leave none selected to search all indexed documents.
            </p>
            <DocumentList documents={documents} selectedIds={selectedIds} onToggle={onToggleDocument} onDelete={onDeleteDocument} />
          </>
        )}
      </div>

      <HardwareTelemetryPanel
        telemetry={hardwareTelemetry}
        loading={hardwareTelemetryLoading}
        error={hardwareTelemetryError}
        modelRuntime={modelRuntime}
        onRefresh={onRefreshHardwareTelemetry}
      />

      <ModelAdvisor
        isStreaming={isStreaming}
        settings={modelSettings}
        settingsLoading={modelSettingsLoading}
        settingsError={modelSettingsError}
        actionMessage={modelActionMessage}
        runtime={modelRuntime}
        runtimeLoading={modelRuntimeLoading}
        runtimeError={modelRuntimeError}
        runtimeActionMessage={modelRuntimeActionMessage}
        runtimeActionLoading={modelRuntimeActionLoading}
        onApplyChatModel={onApplyChatModel}
        onResetChatModel={onResetChatModel}
        onRefreshRuntime={onRefreshModelRuntime}
        onPreloadActiveModel={onPreloadActiveModel}
        onUnloadActiveModel={onUnloadActiveModel}
      />
    </aside>
  );
}
