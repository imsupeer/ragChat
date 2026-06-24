'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useStreaming } from '@/hooks/useStreaming';
import { useAppStore } from '@/store/useAppStore';
import type { ChatMessage, SourceReference } from '@/types/chat';

function uid() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function findPairedUserMessage(messages: ChatMessage[], assistantId: string) {
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

type StreamContext = {
  chatId: string;
  assistantId: string;
};

export function useChat(
  activeChatId: string | null,
  selectedDocumentIds: string[],
  messages: ChatMessage[],
  ensureActiveChat: () => Promise<string>,
) {
  const appendMessages = useAppStore((state) => state.appendMessages);
  const updateMessage = useAppStore((state) => state.updateMessage);
  const clearDraft = useAppStore((state) => state.clearDraft);
  const setStreamError = useAppStore((state) => state.setStreamError);

  const { isStreaming, streamError, pipelineStage, pipelineDebug, startStreaming, cancelStreaming } = useStreaming();

  const streamContextRef = useRef<StreamContext | null>(null);
  const previousChatIdRef = useRef<string | null>(activeChatId);

  const isActiveStream = useCallback(
    (chatId: string, assistantId: string) =>
      streamContextRef.current?.chatId === chatId && streamContextRef.current?.assistantId === assistantId,
    [],
  );

  const interruptStream = useCallback(
    (markError = false) => {
      const context = streamContextRef.current;
      if (!context) {
        return;
      }

      updateMessage(context.chatId, context.assistantId, (message) => ({
        ...message,
        isStreaming: false,
        error: markError && !message.content,
        errorMessage: markError && !message.content ? 'Response interrupted.' : undefined,
      }));
      streamContextRef.current = null;
    },
    [updateMessage],
  );

  const handleCancel = useCallback(() => {
    interruptStream(false);
    cancelStreaming();
  }, [cancelStreaming, interruptStream]);

  useEffect(() => {
    if (previousChatIdRef.current !== activeChatId && streamContextRef.current) {
      interruptStream(false);
      cancelStreaming();
    }
    previousChatIdRef.current = activeChatId;
  }, [activeChatId, cancelStreaming, interruptStream]);

  const runStream = useCallback(
    async (
      chatId: string,
      assistantId: string,
      question: string,
      regenerate: boolean,
    ) => {
      streamContextRef.current = { chatId, assistantId };
      setStreamError(null);

      await startStreaming(
        {
          question,
          document_ids: selectedDocumentIds.length ? selectedDocumentIds : null,
          chat_id: chatId,
          regenerate,
        },
        assistantId,
        {
          onToken: (token) => {
            if (!isActiveStream(chatId, assistantId)) {
              return;
            }
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              content: `${message.content}${token}`,
              isStreaming: true,
              error: false,
              errorMessage: undefined,
            }));
          },
          onSources: (sources: SourceReference[], debug) => {
            if (!isActiveStream(chatId, assistantId)) {
              return;
            }
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              sources,
              debug: debug ?? message.debug,
            }));
          },
          onDone: (debug) => {
            if (!isActiveStream(chatId, assistantId)) {
              return;
            }
            streamContextRef.current = null;
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              isStreaming: false,
              error: false,
              errorMessage: undefined,
              debug: debug ?? message.debug,
            }));
          },
          onError: (error) => {
            if (!isActiveStream(chatId, assistantId)) {
              return;
            }
            streamContextRef.current = null;
            updateMessage(chatId, assistantId, (message) => ({
              ...message,
              isStreaming: false,
              error: true,
              errorMessage: error.message,
            }));
          },
        },
      );
    },
    [isActiveStream, selectedDocumentIds, setStreamError, startStreaming, updateMessage],
  );

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

      await runStream(chatId, assistantId, trimmed, false);
    },
    [activeChatId, appendMessages, clearDraft, ensureActiveChat, isStreaming, runStream],
  );

  const regenerateAssistant = useCallback(
    async (assistantId: string) => {
      const chatId = activeChatId;
      if (!chatId || isStreaming) {
        return;
      }

      const question = findPairedUserMessage(messages, assistantId);
      if (!question) {
        return;
      }

      updateMessage(chatId, assistantId, (message) => ({
        ...message,
        content: '',
        sources: [],
        debug: undefined,
        isStreaming: true,
        error: false,
        errorMessage: undefined,
      }));

      await runStream(chatId, assistantId, question, true);
    },
    [activeChatId, isStreaming, messages, runStream, updateMessage],
  );

  return {
    isStreaming,
    streamError,
    pipelineStage,
    pipelineDebug,
    sendMessage,
    cancelStreaming: handleCancel,
    regenerateAssistant,
  };
}
