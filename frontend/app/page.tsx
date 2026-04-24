'use client';

import { useEffect, useMemo, useState } from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { ChatEmptyState } from '@/components/chat/ChatEmptyState';
import { ChatInput } from '@/components/chat/ChatInput';
import { ChatStageIndicator } from '@/components/chat/ChatStageIndicator';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { InsightPanel } from '@/components/panels/InsightPanel';
import { useChat } from '@/hooks/useChat';
import { useChatSessions } from '@/hooks/useChatSessions';
import { useDocuments } from '@/hooks/useDocuments';
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

  const { documents, loading, error, selectedIds, queueItems, handleUpload, handleDelete, toggleSelected } = useDocuments();
  const { chats, activeChatId, messages, loadingChats, ensureActiveChat, setActiveChatId, handleCreateChat, handleDeleteChat, handleRenameChat } =
    useChatSessions();
  const { isStreaming, streamError, pipelineStage, pipelineDebug, sendMessage, cancelStreaming, regenerateLast } = useChat(
    activeChatId,
    selectedIds,
    messages,
    ensureActiveChat,
  );

  const debugMode = useAppStore((state) => state.debugMode);
  const setDebugMode = useAppStore((state) => state.setDebugMode);

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
            <div className="h-full border-r border-border" style={{ width: sidebarWidth }}>
              <Sidebar
                documents={documents}
                loading={loading}
                error={error}
                selectedIds={selectedIds}
                queueItems={queueItems}
                chats={chats}
                activeChatId={activeChatId}
                onUpload={handleUpload}
                onDeleteDocument={handleDelete}
                onToggleDocument={toggleSelected}
                onCreateChat={handleCreateChat}
                onDeleteChat={handleDeleteChat}
                onRenameChat={handleRenameChat}
                onSelectChat={setActiveChatId}
              />
            </div>

            <div onMouseDown={startResize} className="w-1 cursor-col-resize bg-border/30 transition hover:bg-sky-500" />
          </>
        ) : null}

        <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="border-b border-border px-4 py-4">
            <div className="mx-auto flex max-w-6xl items-start gap-3">
              <button
                type="button"
                onClick={() => setSidebarVisible((current) => !current)}
                className="mt-1 rounded-xl border border-border bg-white/[0.04] p-2 transition hover:bg-white/[0.08]"
              >
                {sidebarVisible ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeftOpen className="h-5 w-5" />}
              </button>

              <div className="min-w-0 flex-1">
                <Header
                  documentCount={documents.length}
                  selectedDocumentCount={selectedIds.length}
                  activeSourceCount={selectedAssistantMessage?.sources?.length ?? 0}
                  debugMode={debugMode}
                  panelOpen={panelOpen}
                  onToggleDebugMode={() => setDebugMode(!debugMode)}
                  onTogglePanel={() => setPanelOpen((current) => !current)}
                />
              </div>
            </div>
          </div>

          <ChatStageIndicator isStreaming={isStreaming} stage={pipelineStage} debug={pipelineDebug} />

          <div className="flex min-h-0 flex-1">
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              <ChatContainer
                messages={messages}
                streamError={streamError}
                onRegenerate={regenerateLast}
                onInspectMessage={(messageId) => {
                  setSelectedMessageId(messageId);
                  setPanelOpen(true);
                }}
                selectedMessageId={selectedAssistantMessage?.id ?? null}
                isLoading={loadingChats}
                emptyState={<ChatEmptyState hasDocuments={documents.length > 0} onSuggestionSelect={sendMessage} />}
              />

              <ChatInput
                activeChatId={activeChatId}
                onSend={sendMessage}
                onCancel={cancelStreaming}
                disabled={loadingChats}
                isStreaming={isStreaming}
              />
            </div>

            {panelOpen ? (
              <div className="hidden h-full w-[380px] shrink-0 xl:block">
                <InsightPanel
                  panelTab={panelTab}
                  onTabChange={setPanelTab}
                  debugMode={debugMode}
                  onToggleDebugMode={setDebugMode}
                  message={selectedAssistantMessage}
                  question={selectedQuestion}
                  className="h-full min-h-0"
                />
              </div>
            ) : null}
          </div>
        </section>
      </div>

      {panelOpen ? (
        <>
          <button
            type="button"
            aria-label="Close evidence panel"
            onClick={() => setPanelOpen(false)}
            className="fixed inset-0 z-40 bg-black/50 xl:hidden"
          />
          <div className="fixed inset-y-0 right-0 z-50 w-full max-w-sm xl:hidden">
            <InsightPanel
              panelTab={panelTab}
              onTabChange={setPanelTab}
              debugMode={debugMode}
              onToggleDebugMode={setDebugMode}
              message={selectedAssistantMessage}
              question={selectedQuestion}
              className="min-h-full"
            />
          </div>
        </>
      ) : null}
    </main>
  );
}
