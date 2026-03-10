'use client';

import { useState } from 'react';
import { SendHorizonal, Square } from 'lucide-react';

export function ChatInput({
  onSend,
  onCancel,
  disabled,
  isStreaming,
}: {
  onSend: (value: string) => Promise<void>;
  onCancel: () => void;
  disabled?: boolean;
  isStreaming: boolean;
}) {
  const [value, setValue] = useState('');

  async function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    setValue('');
    await onSend(trimmed);
  }

  return (
    <div className="border-t border-border bg-bg/80 px-4 py-4 backdrop-blur">
      <div className="mx-auto flex max-w-4xl items-end gap-3 rounded-3xl border border-border bg-panel px-4 py-3 shadow-lg">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={async (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              await handleSubmit();
            }
          }}
          rows={1}
          placeholder="Ask about your documents..."
          className="max-h-48 min-h-[28px] flex-1 resize-none bg-transparent text-sm text-white outline-none placeholder:text-gray-500"
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onCancel}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-red-500/20 text-red-300 transition hover:bg-red-500/30"
          >
            <Square className="h-4 w-4 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-white text-black transition hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <SendHorizonal className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
