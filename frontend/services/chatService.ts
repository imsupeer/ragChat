import { apiFetch, getApiUrl } from '@/services/api';
import type { ChatRequest, ChatResponse, StreamEvent } from '@/types/chat';

export function sendChatMessage(payload: ChatRequest) {
  return apiFetch<ChatResponse>('/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

export async function streamChatMessage(
  payload: ChatRequest,
  handlers: {
    onSources?: (event: Extract<StreamEvent, { type: 'sources' }>) => void;
    onToken?: (token: string) => void;
    onDone?: () => void;
    onError?: (error: Error) => void;
  },
  signal?: AbortSignal,
) {
  const response = await fetch(getApiUrl('/chat/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Failed to stream response (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';

    for (const eventChunk of events) {
      const line = eventChunk.split('\n').find((l) => l.startsWith('data:'));

      if (!line) continue;

      const json = line.replace(/^data:\s*/, '');

      try {
        const event = JSON.parse(json) as StreamEvent;

        if (event.type === 'sources') {
          handlers.onSources?.(event);
        }

        if (event.type === 'token') {
          handlers.onToken?.(event.token);
        }

        if (event.type === 'done') {
          handlers.onDone?.();
        }
      } catch (error) {
        handlers.onError?.(error as Error);
      }
    }
  }
}
