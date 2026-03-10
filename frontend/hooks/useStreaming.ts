'use client';

import { useRef, useState } from 'react';
import { streamChatMessage } from '@/services/chatService';
import type { ChatRequest, SourceReference } from '@/types/chat';

export function useStreaming() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function startStreaming(
    payload: ChatRequest,
    callbacks: {
      onToken: (token: string) => void;
      onSources: (sources: SourceReference[]) => void;
      onDone: () => void;
      onError: (error: Error) => void;
    },
  ) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsStreaming(true);
    setStreamError(null);

    try {
      await streamChatMessage(
        payload,
        {
          onToken: callbacks.onToken,
          onSources: (event) => callbacks.onSources(event.sources),
          onDone: callbacks.onDone,
          onError: (error) => {
            setStreamError(error.message);
            callbacks.onError(error);
          },
        },
        controller.signal,
      );
    } catch (error) {
      const err = error instanceof Error ? error : new Error('Streaming failed');
      if (err.name !== 'AbortError') {
        setStreamError(err.message);
        callbacks.onError(err);
      }
    } finally {
      setIsStreaming(false);
    }
  }

  function cancelStreaming() {
    abortRef.current?.abort();
    setIsStreaming(false);
  }

  return {
    isStreaming,
    streamError,
    startStreaming,
    cancelStreaming,
  };
}
