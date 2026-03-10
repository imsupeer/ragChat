'use client';

import { useEffect, useRef } from 'react';
import { ChatMessage } from '@/components/chat/ChatMessage';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import type { ChatMessage as ChatMessageType } from '@/types/chat';

export function ChatContainer({
  messages,
  streamError,
  onRegenerate,
}: {
  messages: ChatMessageType[];
  streamError: string | null;
  onRegenerate: () => Promise<void>;
}) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} onRegenerate={message.role === 'assistant' ? onRegenerate : undefined} />
        ))}

        {streamError ? <ErrorMessage message={streamError} /> : null}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
