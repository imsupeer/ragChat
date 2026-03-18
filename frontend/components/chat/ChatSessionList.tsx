'use client';

import { MessageSquare, Plus, Trash2 } from 'lucide-react';
import type { ChatSession } from '@/types/chat';

export function ChatSessionList({
  chats,
  activeChatId,
  onSelect,
  onCreate,
  onDelete,
}: {
  chats: ChatSession[];
  activeChatId: string | null;
  onSelect: (chatId: string) => void;
  onCreate: () => Promise<void>;
  onDelete: (chatId: string) => Promise<void>;
}) {
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={onCreate}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-white/5 px-3 py-2 text-sm transition hover:bg-white/10"
      >
        <Plus className="h-4 w-4" />
        New Chat
      </button>

      {chats.map((chat) => (
        <div
          key={chat.id}
          className={`flex items-center justify-between gap-2 rounded-xl border p-2 ${
            activeChatId === chat.id ? 'border-sky-500 bg-sky-500/10' : 'border-border bg-white/5'
          }`}
        >
          <button type="button" onClick={() => onSelect(chat.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
            <MessageSquare className="h-4 w-4 shrink-0" />
            <span className="truncate text-sm">{chat.title}</span>
          </button>

          <button
            type="button"
            onClick={() => onDelete(chat.id)}
            className="rounded-lg p-2 text-gray-400 transition hover:bg-red-500/10 hover:text-red-300"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
