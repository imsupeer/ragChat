'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { ChatEmptyState } from '@/components/chat/ChatEmptyState';
import { ChatInput } from '@/components/chat/ChatInput';
import { ChatStageIndicator } from '@/components/chat/ChatStageIndicator';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { EvidencePanelShell } from '@/components/panels/EvidencePanelShell';
import { useChat } from '@/hooks/useChat';
import { useChatSessions } from '@/hooks/useChatSessions';
import { useDocuments } from '@/hooks/useDocuments';
import { useModelSettings } from '@/hooks/useModelSettings';
import { useModelRuntime } from '@/hooks/useModelRuntime';
import { useHardwareTelemetry } from '@/hooks/useHardwareTelemetry';
import { useAppStore } from '@/store/useAppStore';
import type { ChatMessage } from '@/types/chat';

function findAssistantQuestion(messages: ChatMessage[], assistantId: string | null) {
  if (!assistantId) {
    return null;
  }

  const assistantIndex = messages.findIndex((message) => message.id === assistantId);
  if (assistantIndex === -1) {
    return null;
  }

  for (let index = assistantIndex - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'user') {
      return messages[index].content;
    }
  }

  return null;
}

export default function HomePage() {
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(340);
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelTab, setPanelTab] = useState<'sources' | 'debug'>('sources');
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);

  const { documents, loading, error, selectedIds, queueItems, handleUpload, handleDelete, handleRetryJob, toggleSelected } = useDocuments();
  const { chats, activeChatId, messages, loadingChats, ensureActiveChat, setActiveChatId, handleCreateChat, handleDeleteChat, handleRenameChat } =
    useChatSessions();
  const { isStreaming, streamError, pipelineStage, pipelineDebug, sendMessage, cancelStreaming, regenerateAssistant } = useChat(
    activeChatId,
    selectedIds,
    messages,
    ensureActiveChat,
  );
  const {
    settings: modelSettings,
    loading: modelSettingsLoading,
    error: modelSettingsError,
    actionMessage: modelActionMessage,
    applyChatModel,
    resetChatModel,
  } = useModelSettings();
  const {
    runtime: modelRuntime,
    loading: modelRuntimeLoading,
    error: modelRuntimeError,
    actionMessage: modelRuntimeActionMessage,
    actionLoading: modelRuntimeActionLoading,
    refresh: refreshModelRuntime,
    preload: preloadActiveModel,
    unload: unloadActiveModel,
  } = useModelRuntime({ enablePolling: sidebarVisible });
  const {
    telemetry: hardwareTelemetry,
    loading: hardwareTelemetryLoading,
    error: hardwareTelemetryError,
    refresh: refreshHardwareTelemetry,
    refreshSilent: refreshHardwareTelemetrySilent,
  } = useHardwareTelemetry({ enablePolling: sidebarVisible });

  const debugMode = useAppStore((state) => state.debugMode);
  const setDebugMode = useAppStore((state) => state.setDebugMode);
  const panelToggleRef = useRef<HTMLButtonElement>(null);

  const closePanel = useCallback(() => {
    setPanelOpen(false);
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 1279px)').matches) {
      panelToggleRef.current?.focus();
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    if (window.matchMedia('(max-width: 1279px)').matches) {
      setPanelOpen(false);
    }
  }, []);

  function startResize(event: React.MouseEvent<HTMLDivElement>) {
    event.preventDefault();

    function onMouseMove(moveEvent: MouseEvent) {
      const nextWidth = Math.min(520, Math.max(280, moveEvent.clientX));
      setSidebarWidth(nextWidth);
    }

    function onMouseUp() {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  const selectedAssistantMessage = useMemo(() => {
    const assistantMessages = messages.filter((message) => message.role === 'assistant');
    if (!assistantMessages.length) {
      return null;
    }

    const selected = assistantMessages.find((message) => message.id === selectedMessageId) ?? assistantMessages[assistantMessages.length - 1];

    return selected;
  }, [messages, selectedMessageId]);

  const selectedQuestion = useMemo(() => findAssistantQuestion(messages, selectedAssistantMessage?.id ?? null), [messages, selectedAssistantMessage]);

  const hasDocuments = documents.length > 0;
  const hasActiveUploads = queueItems.some((item) => ['queued', 'uploading', 'processing'].includes(item.status));

  function handleSelectChat(chatId: string) {
    if (chatId === activeChatId) {
      return;
    }

    if (isStreaming) {
      const confirmed = window.confirm('Generation is still running. Switch chats and cancel it?');
      if (!confirmed) {
        return;
      }
    }

    setActiveChatId(chatId);
  }

  useEffect(() => {
    if (!messages.length) {
      setSelectedMessageId(null);
      return;
    }

    if (selectedMessageId && messages.some((message) => message.id === selectedMessageId)) {
      return;
    }

    const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant');
    setSelectedMessageId(latestAssistant?.id ?? null);
  }, [messages, selectedMessageId]);

  return (
    <main className="h-screen overflow-hidden bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.08),transparent_28%),linear-gradient(180deg,#0d0f14_0%,#101118_100%)] text-white">
      <div className="flex h-full">
        {sidebarVisible ? (
          <>
            <div id="app-sidebar" className="h-full border-r border-border" style={{ width: sidebarWidth }}>
              <Sidebar
                documents={documents}
                loading={loading}
                error={error}
                selectedIds={selectedIds}
                queueItems={queueItems}
                chats={chats}
                activeChatId={activeChatId}
                isStreaming={isStreaming}
                modelSettings={modelSettings}
                modelSettingsLoading={modelSettingsLoading}
                modelSettingsError={modelSettingsError}
                modelActionMessage={modelActionMessage}
                modelRuntime={modelRuntime}
                modelRuntimeLoading={modelRuntimeLoading}
                modelRuntimeError={modelRuntimeError}
                modelRuntimeActionMessage={modelRuntimeActionMessage}
                modelRuntimeActionLoading={modelRuntimeActionLoading}
                onApplyChatModel={async (chatModel) => {
                  await applyChatModel(chatModel);
                  await refreshModelRuntime();
                }}
                onResetChatModel={async () => {
                  await resetChatModel();
                  await refreshModelRuntime();
                }}
                onRefreshModelRuntime={refreshModelRuntime}
                onPreloadActiveModel={async () => {
                  await preloadActiveModel();
                  await refreshHardwareTelemetrySilent();
                }}
                onUnloadActiveModel={async () => {
                  await unloadActiveModel();
                  await refreshHardwareTelemetrySilent();
                }}
                hardwareTelemetry={hardwareTelemetry}
                hardwareTelemetryLoading={hardwareTelemetryLoading}
                hardwareTelemetryError={hardwareTelemetryError}
                onRefreshHardwareTelemetry={refreshHardwareTelemetry}
                onUpload={handleUpload}
                onDeleteDocument={handleDelete}
                onRetryUploadJob={handleRetryJob}
                onToggleDocument={toggleSelected}
                onCreateChat={handleCreateChat}
                onDeleteChat={handleDeleteChat}
                onRenameChat={handleRenameChat}
                onSelectChat={handleSelectChat}
              />
            </div>

            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize sidebar. Pointer only - drag to adjust width."
              title="Drag to resize sidebar (pointer only)"
              onMouseDown={startResize}
              className="w-1 cursor-col-resize bg-border/30 transition hover:bg-sky-500"
            />
          </>
        ) : null}

        <section aria-label="Chat workspace" className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="border-b border-border px-4 py-4">
            <div className="mx-auto flex max-w-6xl items-start gap-3">
              <button
                type="button"
                onClick={() => setSidebarVisible((current) => !current)}
                aria-label="Toggle sidebar"
                aria-expanded={sidebarVisible}
                aria-controls="app-sidebar"
                className="focus-ring mt-1 rounded-xl border border-border bg-white/[0.04] p-2 transition hover:bg-white/[0.08]"
              >
                {sidebarVisible ? (
                  <PanelLeftClose className="h-5 w-5" aria-hidden="true" />
                ) : (
                  <PanelLeftOpen className="h-5 w-5" aria-hidden="true" />
                )}
              </button>

              <div className="min-w-0 flex-1">
                <Header
                  documentCount={documents.length}
                  selectedDocumentCount={selectedIds.length}
                  activeSourceCount={selectedAssistantMessage?.sources?.length ?? 0}
                  chatModel={modelSettings?.chat_model ?? null}
                  modelRuntime={modelRuntime}
                  modelRuntimeLoading={modelRuntimeLoading}
                  onRefreshModelRuntime={refreshModelRuntime}
                  debugMode={debugMode}
                  panelOpen={panelOpen}
                  panelToggleRef={panelToggleRef}
                  onToggleDebugMode={() => setDebugMode(!debugMode)}
                  onTogglePanel={() => setPanelOpen((current) => !current)}
                />
              </div>
            </div>
          </div>

          <ChatStageIndicator isStreaming={isStreaming} stage={pipelineStage} debug={pipelineDebug} hasDocuments={hasDocuments} />

          <div className="flex min-h-0 flex-1">
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              <ChatContainer
                messages={messages}
                streamError={streamError}
                onRegenerate={regenerateAssistant}
                onInspectMessage={(messageId) => {
                  setSelectedMessageId(messageId);
                  setPanelOpen(true);
                }}
                selectedMessageId={selectedAssistantMessage?.id ?? null}
                isLoading={loadingChats}
                emptyState={<ChatEmptyState hasDocuments={hasDocuments} hasActiveUploads={hasActiveUploads} onSuggestionSelect={sendMessage} />}
              />

              <ChatInput
                activeChatId={activeChatId}
                onSend={sendMessage}
                onCancel={cancelStreaming}
                disabled={loadingChats}
                isStreaming={isStreaming}
                streamErrorId="chat-stream-error"
                hasStreamError={Boolean(streamError && !messages.some((message) => message.errorMessage))}
              />
            </div>

            <EvidencePanelShell
              open={panelOpen}
              onClose={closePanel}
              panelTab={panelTab}
              onTabChange={setPanelTab}
              debugMode={debugMode}
              onToggleDebugMode={setDebugMode}
              message={selectedAssistantMessage}
              question={selectedQuestion}
              panelToggleRef={panelToggleRef}
            />
          </div>
        </section>
      </div>
    </main>
  );
}
