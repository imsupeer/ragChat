import { getApiUrl } from '@/services/api';
import type { ChatRequest, StreamEvent } from '@/types/chat';

async function parseErrorResponse(response: Response): Promise<string> {
  let detail = `Request failed with status ${response.status}`;

  try {
    const data = await response.json();
    if (typeof data?.detail === 'string') {
      detail = data.detail;
    } else if (Array.isArray(data?.detail)) {
      detail = data.detail
        .map((item: { msg?: string }) => item.msg ?? String(item))
        .join(', ');
    } else if (data?.message) {
      detail = data.message;
    }
  } catch {
    const text = await response.text();
    if (text) {
      detail = text;
    }
  }

  return detail;
}

export async function streamChatMessage(
  payload: ChatRequest,
  handlers: {
    onSources?: (event: Extract<StreamEvent, { type: 'sources' }>) => void;
    onToken?: (token: string) => void;
    onDone?: (event: Extract<StreamEvent, { type: 'done' }>) => void;
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
    throw new Error(await parseErrorResponse(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completed = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';

    for (const eventChunk of events) {
      const line = eventChunk.split('\n').find((entry) => entry.startsWith('data:'));

      if (!line) {
        continue;
      }

      const json = line.replace(/^data:\s*/, '');

      let event: StreamEvent;
      try {
        event = JSON.parse(json) as StreamEvent;
      } catch (error) {
        handlers.onError?.(error instanceof Error ? error : new Error('Invalid stream event'));
        return;
      }

      if (event.type === 'sources') {
        handlers.onSources?.(event);
        continue;
      }

      if (event.type === 'token') {
        handlers.onToken?.(event.token);
        continue;
      }

      if (event.type === 'done') {
        completed = true;
        handlers.onDone?.(event);
        return;
      }

      if (event.type === 'error') {
        completed = true;
        handlers.onError?.(new Error(event.message));
        return;
      }
    }
  }

  if (!completed && !signal?.aborted) {
    handlers.onError?.(new Error('Stream ended before completion.'));
  }
}
