'use client';

import { useCallback, useMemo } from 'react';
import { useStreaming } from '@/hooks/useStreaming';
import type { ChatMessage, SourceReference } from '@/types/chat';

function uid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

export function useChat(
  activeChatId: string | null,
  selectedDocumentIds: string[],
  messages: ChatMessage[],
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>,
) {
  const { isStreaming, streamError, startStreaming, cancelStreaming } = useStreaming();

  const sendMessage = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isStreaming || !activeChatId) return;

      const userMessage: ChatMessage = {
        id: uid(),
        role: 'user',
        content: trimmed,
        chat_id: activeChatId,
      };

      const assistantId = uid();

      setMessages((current) => [
        ...current,
        userMessage,
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          sources: [],
          isStreaming: true,
          chat_id: activeChatId,
        },
      ]);

      await startStreaming(
        {
          question: trimmed,
          document_ids: selectedDocumentIds.length ? selectedDocumentIds : null,
          chat_id: activeChatId,
        },
        {
          onToken: (token) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      content: `${message.content}${token}`,
                      isStreaming: true,
                    }
                  : message,
              ),
            );
          },
          onSources: (sources: SourceReference[]) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      sources,
                    }
                  : message,
              ),
            );
          },
          onDone: () => {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      isStreaming: false,
                    }
                  : message,
              ),
            );
          },
          onError: (error) => {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      content: message.content || error.message,
                      error: true,
                      isStreaming: false,
                    }
                  : message,
              ),
            );
          },
        },
      );
    },
    [activeChatId, isStreaming, selectedDocumentIds, setMessages, startStreaming],
  );

  const regenerateLast = useCallback(async () => {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUser) {
      await sendMessage(lastUser.content);
    }
  }, [messages, sendMessage]);

  return useMemo(
    () => ({
      isStreaming,
      streamError,
      sendMessage,
      cancelStreaming,
      regenerateLast,
    }),
    [isStreaming, streamError, sendMessage, cancelStreaming, regenerateLast],
  );
}
