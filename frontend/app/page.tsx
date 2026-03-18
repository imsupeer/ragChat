'use client';

import { useState } from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { ChatInput } from '@/components/chat/ChatInput';
import { useDocuments } from '@/hooks/useDocuments';
import { useChatSessions } from '@/hooks/useChatSessions';
import { useChat } from '@/hooks/useChat';

export default function HomePage() {
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(340);
  const { documents, loading, error, selectedIds, queueItems, handleUpload, handleDelete, toggleSelected } = useDocuments();
  const { chats, activeChatId, messages, setMessages, setActiveChatId, handleCreateChat, handleDeleteChat } = useChatSessions();
  const { isStreaming, streamError, sendMessage, cancelStreaming, regenerateLast } = useChat(activeChatId, selectedIds, messages, setMessages);

  function startResize(event: React.MouseEvent<HTMLDivElement>) {
    event.preventDefault();

    function onMouseMove(e: MouseEvent) {
      const nextWidth = Math.min(520, Math.max(260, e.clientX));
      setSidebarWidth(nextWidth);
    }

    function onMouseUp() {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    }

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  return (
    <main className="h-screen bg-bg text-white">
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
                onSelectChat={setActiveChatId}
              />
            </div>

            <div onMouseDown={startResize} className="w-1 cursor-col-resize bg-border/40 transition hover:bg-sky-500" />
          </>
        ) : null}

        <section className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2">
            <button type="button" onClick={() => setSidebarVisible((prev) => !prev)} className="rounded-lg p-2 transition hover:bg-white/5">
              {sidebarVisible ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeftOpen className="h-5 w-5" />}
            </button>

            <div className="min-w-0 flex-1">
              <Header documentCount={documents.length} />
            </div>
          </div>

          <ChatContainer messages={messages} streamError={streamError} onRegenerate={regenerateLast} />

          <ChatInput onSend={sendMessage} onCancel={cancelStreaming} disabled={!activeChatId} isStreaming={isStreaming} />
        </section>
      </div>
    </main>
  );
}
