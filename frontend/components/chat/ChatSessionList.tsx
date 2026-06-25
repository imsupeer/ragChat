'use client';

import { useEffect, useState } from 'react';
import { Check, MessageSquare, Pencil, Plus, Trash2, X } from 'lucide-react';
import type { ChatSession } from '@/types/chat';

export function ChatSessionList({
  chats,
  activeChatId,
  onSelect,
  onCreate,
  onDelete,
  onRename,
}: {
  chats: ChatSession[];
  activeChatId: string | null;
  onSelect: (chatId: string) => void;
  onCreate: () => Promise<void>;
  onDelete: (chatId: string) => Promise<void>;
  onRename: (chatId: string, title: string) => Promise<void>;
}) {
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [savingChatId, setSavingChatId] = useState<string | null>(null);
  const [pendingDeleteChatId, setPendingDeleteChatId] = useState<string | null>(null);
  const [deletingChatId, setDeletingChatId] = useState<string | null>(null);

  useEffect(() => {
    if (!editingChatId) {
      return;
    }

    const currentChat = chats.find((chat) => chat.id === editingChatId);
    if (!currentChat) {
      setEditingChatId(null);
      setDraftTitle('');
    }
  }, [chats, editingChatId]);

  useEffect(() => {
    if (pendingDeleteChatId && !chats.some((chat) => chat.id === pendingDeleteChatId)) {
      setPendingDeleteChatId(null);
    }
  }, [chats, pendingDeleteChatId]);

  async function handleRename(chatId: string) {
    const trimmed = draftTitle.trim();
    if (!trimmed) {
      return;
    }

    setSavingChatId(chatId);

    try {
      await onRename(chatId, trimmed);
      setEditingChatId(null);
      setDraftTitle('');
    } finally {
      setSavingChatId(null);
    }
  }

  async function handleConfirmDelete(chatId: string) {
    setDeletingChatId(chatId);
    try {
      await onDelete(chatId);
      setPendingDeleteChatId(null);
    } finally {
      setDeletingChatId(null);
    }
  }

  function beginEdit(chat: ChatSession) {
    setEditingChatId(chat.id);
    setDraftTitle(chat.title);
    setPendingDeleteChatId(null);
  }

  function cancelEdit() {
    setEditingChatId(null);
    setDraftTitle('');
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        data-testid="chat-new-session"
        onClick={onCreate}
        className="focus-ring flex w-full items-center justify-center gap-2 rounded-2xl border border-border bg-white/[0.04] px-3 py-2.5 text-sm transition hover:border-sky-500/30 hover:bg-white/[0.07]"
      >
        <Plus className="h-4 w-4" />
        New Chat
      </button>

      {!chats.length ? (
        <p className="px-1 text-xs leading-5 text-gray-500" data-testid="chat-session-empty-state">
          No chats yet. Start by asking a question after uploading a document.
        </p>
      ) : null}

      {chats.map((chat) => {
        const isActive = activeChatId === chat.id;
        const isEditing = editingChatId === chat.id;
        const isSaving = savingChatId === chat.id;
        const isPendingDelete = pendingDeleteChatId === chat.id;

        return (
          <div
            key={chat.id}
            className={`rounded-2xl border p-2 transition ${
              isActive
                ? 'border-sky-500/40 bg-sky-500/10 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]'
                : 'border-border bg-white/[0.03] hover:border-white/10'
            }`}
          >
            {isEditing ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 shrink-0 text-gray-300" />
                  <input
                    autoFocus
                    value={draftTitle}
                    onChange={(event) => setDraftTitle(event.target.value)}
                    onKeyDown={async (event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        await handleRename(chat.id);
                      }

                      if (event.key === 'Escape') {
                        event.preventDefault();
                        cancelEdit();
                      }
                    }}
                    className="min-w-0 flex-1 rounded-xl border border-border bg-black/20 px-3 py-2 text-sm text-white outline-none focus:border-sky-500/40"
                  />
                </div>

                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={cancelEdit}
                    className="inline-flex items-center gap-1 rounded-xl border border-border px-2.5 py-1.5 text-xs text-gray-300 transition hover:text-white"
                  >
                    <X className="h-3.5 w-3.5" />
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRename(chat.id)}
                    disabled={!draftTitle.trim() || isSaving}
                    className="inline-flex items-center gap-1 rounded-xl border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-xs text-sky-100 transition hover:border-sky-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Check className="h-3.5 w-3.5" />
                    {isSaving ? 'Saving...' : 'Save'}
                  </button>
                </div>
              </div>
            ) : isPendingDelete ? (
              <div className="space-y-2 px-1" role="group" aria-labelledby={`chat-delete-confirm-${chat.id}`}>
                <p id={`chat-delete-confirm-${chat.id}`} className="text-xs leading-5 text-gray-300" data-testid="chat-delete-confirm">
                  Delete this chat and its messages?
                </p>
                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setPendingDeleteChatId(null)}
                    aria-label="Cancel chat deletion"
                    className="focus-ring inline-flex items-center gap-1 rounded-xl border border-border px-2.5 py-1.5 text-xs text-gray-300 transition hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleConfirmDelete(chat.id)}
                    disabled={deletingChatId === chat.id}
                    aria-label="Confirm delete chat"
                    className="focus-ring inline-flex items-center gap-1 rounded-xl border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-xs text-red-200 transition hover:border-red-500/50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {deletingChatId === chat.id ? 'Deleting...' : 'Delete chat'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => onSelect(chat.id)}
                  aria-label={`Open chat ${chat.title}`}
                  aria-current={isActive ? 'true' : undefined}
                  className="focus-ring flex min-w-0 flex-1 items-center gap-2 rounded-lg text-left"
                >
                  <MessageSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="truncate text-sm">{chat.title}</span>
                </button>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => beginEdit(chat)}
                    className="focus-ring rounded-lg p-2 text-gray-400 transition hover:bg-white/5 hover:text-white"
                    aria-label={`Rename ${chat.title}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => setPendingDeleteChatId(chat.id)}
                    className="focus-ring rounded-lg p-2 text-gray-400 transition hover:bg-red-500/10 hover:text-red-300"
                    aria-label={`Delete chat ${chat.title}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
