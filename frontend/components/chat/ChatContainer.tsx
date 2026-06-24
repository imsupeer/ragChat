'use client';

import { useEffect, useRef, useState } from 'react';
import { ChatMessage } from '@/components/chat/ChatMessage';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { Skeleton } from '@/components/ui/Skeleton';
import type { ChatMessage as ChatMessageType } from '@/types/chat';

const SCROLL_THRESHOLD_PX = 120;

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
  onRegenerate: (assistantId: string) => Promise<void>;
  onInspectMessage: (messageId: string) => void;
  selectedMessageId: string | null;
  isLoading?: boolean;
  emptyState?: React.ReactNode;
}) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef(true);
  const previousMessageCountRef = useRef(0);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const isStreaming = messages.some((message) => message.isStreaming);

  function scrollToBottom(behavior: ScrollBehavior) {
    bottomRef.current?.scrollIntoView({ behavior, block: 'end' });
  }

  function updateNearBottomState() {
    const container = scrollContainerRef.current;
    if (!container) {
      return true;
    }

    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    const nearBottom = distanceFromBottom <= SCROLL_THRESHOLD_PX;
    isNearBottomRef.current = nearBottom;
    setShowJumpToLatest(!nearBottom && messages.length > 0);
    return nearBottom;
  }

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) {
      return;
    }

    const handleScroll = () => {
      updateNearBottomState();
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, [messages.length]);

  useEffect(() => {
    const previousCount = previousMessageCountRef.current;
    const messageAdded = messages.length > previousCount;
    previousMessageCountRef.current = messages.length;

    const lastMessage = messages[messages.length - 1];
    const sentUserMessage = messageAdded && lastMessage?.role === 'user';

    if (sentUserMessage) {
      isNearBottomRef.current = true;
      scrollToBottom('smooth');
      setShowJumpToLatest(false);
      return;
    }

    if (isNearBottomRef.current) {
      scrollToBottom(isStreaming ? 'auto' : 'smooth');
      setShowJumpToLatest(false);
      return;
    }

    if (messages.length > 0) {
      setShowJumpToLatest(true);
    }
  }, [messages, isStreaming]);

  function handleJumpToLatest() {
    isNearBottomRef.current = true;
    scrollToBottom('smooth');
    setShowJumpToLatest(false);
  }

  return (
    <div className="relative min-h-0 flex-1" aria-label="Chat messages">
      <div ref={scrollContainerRef} className="h-full overflow-y-auto px-4 py-6">
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
                  onRegenerate={message.role === 'assistant' ? () => onRegenerate(message.id) : undefined}
                />
              ))
            : null}

          {streamError && !messages.some((message) => message.errorMessage) ? (
            <ErrorMessage id="chat-stream-error" message={streamError} />
          ) : null}
          <div ref={bottomRef} />
        </div>
      </div>

      {showJumpToLatest ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center px-4">
          <button
            type="button"
            data-testid="jump-to-latest"
            onClick={handleJumpToLatest}
            aria-label="Jump to latest message"
            className="focus-ring pointer-events-auto rounded-full border border-sky-500/40 bg-sky-500/15 px-4 py-2 text-sm text-sky-100 shadow-lg backdrop-blur transition hover:bg-sky-500/25"
          >
            Jump to latest
          </button>
        </div>
      ) : null}
    </div>
  );
}
