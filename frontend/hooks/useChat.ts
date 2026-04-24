'use client';

import { useCallback } from 'react';
import { useStreaming } from '@/hooks/useStreaming';
import { useAppStore } from '@/store/useAppStore';
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
  ensureActiveChat: () => Promise<string>,
) {
  const appendMessages = useAppStore((state) => state.appendMessages);
  const updateMessage = useAppStore((state) => state.updateMessage);
  const clearDraft = useAppStore((state) => state.clearDraft);

  const { isStreaming, streamError, pipelineStage, pipelineDebug, startStreaming, cancelStreaming } = useStreaming();

  const sendMessage = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isStreaming) {
        return;
      }

      const chatId = activeChatId ?? (await ensureActiveChat());
      if (!chatId) {
        return;
      }

      const userMessage: ChatMessage = {
        id: uid(),
        role: 'user',
        content: trimmed,
        chat_id: chatId,
      };

      const assistantId = uid();
      appendMessages(chatId, [
        userMessage,
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          sources: [],
          isStreaming: true,
          chat_id: chatId,
        },
      ]);
      clearDraft(chatId);

      await startStreaming(
        {
          question: trimmed,
          document_ids: selectedDocumentIds.length ? selectedDocumentIds : null,
          chat_id: chatId,
        },
        assistantId,
        {
          onToken: (token) => {
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              content: `${message.content}${token}`,
              isStreaming: true,
            }));
          },
          onSources: (sources: SourceReference[], debug) => {
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              sources,
              debug: debug ?? message.debug,
            }));
          },
          onDone: (debug) => {
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              isStreaming: false,
              debug: debug ?? message.debug,
            }));
          },
          onError: (error) => {
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              content: message.content || error.message,
              error: true,
              isStreaming: false,
            }));
          },
        },
      );
    },
    [activeChatId, appendMessages, clearDraft, ensureActiveChat, isStreaming, selectedDocumentIds, startStreaming, updateMessage],
  );

  const regenerateLast = useCallback(async () => {
    const lastUser = [...messages].reverse().find((message) => message.role === 'user');
    if (lastUser) {
      await sendMessage(lastUser.content);
    }
  }, [messages, sendMessage]);

  return {
    isStreaming,
    streamError,
    pipelineStage,
    pipelineDebug,
    sendMessage,
    cancelStreaming,
    regenerateLast,
  };
}
