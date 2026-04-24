'use client';

import { useEffect, useRef } from 'react';
import { ChatMessage } from '@/components/chat/ChatMessage';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { Skeleton } from '@/components/ui/Skeleton';
import type { ChatMessage as ChatMessageType } from '@/types/chat';

function ChatSkeleton() {
  return (
    <div className="space-y-6">
      <div className="max-w-[55%] rounded-[28px] border border-border bg-white/[0.03] p-5">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="mt-4 h-4 w-full" />
        <Skeleton className="mt-2 h-4 w-[85%]" />
        <Skeleton className="mt-2 h-4 w-[70%]" />
      </div>

      <div className="ml-auto max-w-[62%] rounded-[28px] border border-sky-500/20 bg-sky-500/10 p-5">
        <Skeleton className="h-4 w-16 bg-white/20" />
        <Skeleton className="mt-4 h-4 w-full bg-white/20" />
        <Skeleton className="mt-2 h-4 w-[78%] bg-white/20" />
      </div>
    </div>
  );
}

export function ChatContainer({
  messages,
  streamError,
  onRegenerate,
  onInspectMessage,
  selectedMessageId,
  isLoading = false,
  emptyState,
}: {
  messages: ChatMessageType[];
  streamError: string | null;
  onRegenerate: () => Promise<void>;
  onInspectMessage: (messageId: string) => void;
  selectedMessageId: string | null;
  isLoading?: boolean;
  emptyState?: React.ReactNode;
}) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        {isLoading ? <ChatSkeleton /> : null}

        {!isLoading && !messages.length ? emptyState : null}

        {!isLoading
          ? messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                selected={selectedMessageId === message.id}
                onInspect={message.role === 'assistant' ? () => onInspectMessage(message.id) : undefined}
                onRegenerate={message.role === 'assistant' ? onRegenerate : undefined}
              />
            ))
          : null}

        {streamError ? <ErrorMessage message={streamError} /> : null}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
