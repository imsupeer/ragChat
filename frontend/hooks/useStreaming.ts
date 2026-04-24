'use client';

import { useRef } from 'react';
import { streamChatMessage } from '@/services/chatService';
import { useAppStore } from '@/store/useAppStore';
import type { ChatRequest, SourceReference, StreamEvent } from '@/types/chat';

export function useStreaming() {
  const isStreaming = useAppStore((state) => state.isStreaming);
  const streamError = useAppStore((state) => state.streamError);
  const pipelineStage = useAppStore((state) => state.pipelineStage);
  const pipelineDebug = useAppStore((state) => state.pipelineDebug);

  const startStreamLifecycle = useAppStore((state) => state.startStreaming);
  const setPipelineStage = useAppStore((state) => state.setPipelineStage);
  const setStreamError = useAppStore((state) => state.setStreamError);
  const finishStreaming = useAppStore((state) => state.finishStreaming);
  const resetStreaming = useAppStore((state) => state.resetStreaming);

  const abortRef = useRef<AbortController | null>(null);
  const transitionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function startStreaming(
    payload: ChatRequest,
    assistantId: string,
    callbacks: {
      onToken: (token: string) => void;
      onSources: (sources: SourceReference[], debug?: Extract<StreamEvent, { type: 'sources' }>['debug']) => void;
      onDone: (debug?: Extract<StreamEvent, { type: 'done' }>['debug']) => void;
      onError: (error: Error) => void;
    },
  ) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    startStreamLifecycle(assistantId);
    if (transitionTimeoutRef.current) {
      clearTimeout(transitionTimeoutRef.current);
      transitionTimeoutRef.current = null;
    }

    try {
      await streamChatMessage(
        payload,
        {
          onToken: callbacks.onToken,
          onSources: (event) => {
            if (event.debug?.reranking?.enabled) {
              setPipelineStage('reranking', event.debug ?? null);
              transitionTimeoutRef.current = setTimeout(() => {
                setPipelineStage('generating', event.debug ?? null);
                transitionTimeoutRef.current = null;
              }, 360);
            } else {
              setPipelineStage('generating', event.debug ?? null);
            }
            callbacks.onSources(event.sources, event.debug);
          },
          onDone: (event) => {
            if (transitionTimeoutRef.current) {
              clearTimeout(transitionTimeoutRef.current);
              transitionTimeoutRef.current = null;
            }
            finishStreaming(event.debug ?? null);
            callbacks.onDone(event.debug);
          },
          onError: (error) => {
            if (transitionTimeoutRef.current) {
              clearTimeout(transitionTimeoutRef.current);
              transitionTimeoutRef.current = null;
            }
            setStreamError(error.message);
            callbacks.onError(error);
          },
        },
        controller.signal,
      );
    } catch (error) {
      const err = error instanceof Error ? error : new Error('Streaming failed');
      if (err.name !== 'AbortError') {
        if (transitionTimeoutRef.current) {
          clearTimeout(transitionTimeoutRef.current);
          transitionTimeoutRef.current = null;
        }
        setStreamError(err.message);
        callbacks.onError(err);
      } else {
        resetStreaming();
      }
    }
  }

  function cancelStreaming() {
    abortRef.current?.abort();
    if (transitionTimeoutRef.current) {
      clearTimeout(transitionTimeoutRef.current);
      transitionTimeoutRef.current = null;
    }
    resetStreaming();
  }

  return {
    isStreaming,
    streamError,
    pipelineStage,
    pipelineDebug,
    startStreaming,
    cancelStreaming,
  };
}
