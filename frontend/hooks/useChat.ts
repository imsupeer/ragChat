'use client';

import { useCallback, useMemo, useState } from 'react';
import { create } from 'zustand';
import { useStreaming } from '@/hooks/useStreaming';
import type { ChatMessage, SourceReference } from '@/types/chat';

function uid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

type ChatStore = {
  messages: ChatMessage[];
  appendMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, updater: (message: ChatMessage) => ChatMessage) => void;
  reset: () => void;
};

const initialAssistantMessage: ChatMessage = {
  id: uid(),
  role: 'assistant',
  content: 'Upload one or more documents, then ask anything about them.',
};

const useChatStore = create<ChatStore>((set) => ({
  messages: [initialAssistantMessage],
  appendMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  updateMessage: (id, updater) =>
    set((state) => ({
      messages: state.messages.map((message) => (message.id === id ? updater(message) : message)),
    })),
  reset: () =>
    set({
      messages: [
        {
          id: uid(),
          role: 'assistant',
          content: 'Upload one or more documents, then ask anything about them.',
        },
      ],
    }),
}));

export function useChat(selectedDocumentIds: string[]) {
  const { messages, appendMessage, updateMessage } = useChatStore();
  const { isStreaming, streamError, startStreaming, cancelStreaming } = useStreaming();
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isStreaming) return;

      const userMessage: ChatMessage = {
        id: uid(),
        role: 'user',
        content: trimmed,
      };

      const assistantId = uid();

      appendMessage(userMessage);
      appendMessage({
        id: assistantId,
        role: 'assistant',
        content: '',
        sources: [],
        isStreaming: true,
      });

      setPendingQuestion(trimmed);

      await startStreaming(
        {
          question: trimmed,
          document_ids: selectedDocumentIds.length ? selectedDocumentIds : null,
        },
        {
          onToken: (token) => {
            updateMessage(assistantId, (message) => ({
              ...message,
              content: `${message.content}${token}`,
              isStreaming: true,
            }));
          },
          onSources: (sources: SourceReference[]) => {
            updateMessage(assistantId, (message) => ({
              ...message,
              sources,
            }));
          },
          onDone: () => {
            updateMessage(assistantId, (message) => ({
              ...message,
              isStreaming: false,
            }));
          },
          onError: (error) => {
            updateMessage(assistantId, (message) => ({
              ...message,
              content: message.content || error.message,
              error: true,
              isStreaming: false,
            }));
          },
        },
      );
    },
    [appendMessage, isStreaming, selectedDocumentIds, startStreaming, updateMessage],
  );

  const regenerateLast = useCallback(async () => {
    if (!pendingQuestion || isStreaming) return;
    await sendMessage(pendingQuestion);
  }, [isStreaming, pendingQuestion, sendMessage]);

  return useMemo(
    () => ({
      messages,
      isStreaming,
      streamError,
      sendMessage,
      cancelStreaming,
      regenerateLast,
    }),
    [messages, isStreaming, streamError, sendMessage, cancelStreaming, regenerateLast],
  );
}
