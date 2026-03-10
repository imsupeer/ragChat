'use client';

import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { ChatContainer } from '@/components/chat/ChatContainer';
import { ChatInput } from '@/components/chat/ChatInput';
import { useDocuments } from '@/hooks/useDocuments';
import { useChat } from '@/hooks/useChat';

export default function HomePage() {
  const { documents, loading, error, uploading, selectedIds, handleUpload, handleDelete, toggleSelected } = useDocuments();

  const { messages, isStreaming, streamError, sendMessage, cancelStreaming, regenerateLast } = useChat(selectedIds);

  return (
    <main className="h-screen bg-bg text-white">
      <div className="flex h-full flex-col lg:flex-row">
        <Sidebar
          documents={documents}
          loading={loading}
          error={error}
          uploading={uploading}
          selectedIds={selectedIds}
          onUpload={handleUpload}
          onDelete={handleDelete}
          onToggle={toggleSelected}
        />

        <section className="flex min-h-0 flex-1 flex-col">
          <Header documentCount={documents.length} />
          <ChatContainer messages={messages} streamError={streamError} onRegenerate={regenerateLast} />
          <ChatInput onSend={sendMessage} onCancel={cancelStreaming} disabled={uploading} isStreaming={isStreaming} />
        </section>
      </div>
    </main>
  );
}
