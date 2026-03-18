'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createChat, deleteChat, getChatMessages, listChats } from '@/services/chatSessionService';
import type { ChatMessage, ChatSession } from '@/types/chat';

export function useChatSessions() {
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingChats, setLoadingChats] = useState(true);

  const refreshChats = useCallback(async () => {
    setLoadingChats(true);
    const data = await listChats();
    setChats(data.chats);

    if (!activeChatId && data.chats.length) {
      setActiveChatId(data.chats[0].id);
    }

    setLoadingChats(false);
  }, [activeChatId]);

  const loadMessages = useCallback(async (chatId: string) => {
    const data = await getChatMessages(chatId);
    setMessages(data.messages);
  }, []);

  const handleCreateChat = useCallback(async () => {
    const data = await createChat();
    await refreshChats();
    setActiveChatId(data.chat.id);
    setMessages([]);
  }, [refreshChats]);

  const handleDeleteChat = useCallback(
    async (chatId: string) => {
      await deleteChat(chatId);
      const data = await listChats();
      setChats(data.chats);

      if (activeChatId === chatId) {
        const nextId = data.chats[0]?.id ?? null;
        setActiveChatId(nextId);
        if (nextId) {
          const msgData = await getChatMessages(nextId);
          setMessages(msgData.messages);
        } else {
          setMessages([]);
        }
      }
    },
    [activeChatId],
  );

  useEffect(() => {
    void refreshChats();
  }, [refreshChats]);

  useEffect(() => {
    if (activeChatId) {
      void loadMessages(activeChatId);
    }
  }, [activeChatId, loadMessages]);

  return useMemo(
    () => ({
      chats,
      activeChatId,
      messages,
      loadingChats,
      setActiveChatId,
      setMessages,
      refreshChats,
      loadMessages,
      handleCreateChat,
      handleDeleteChat,
    }),
    [chats, activeChatId, messages, loadingChats, refreshChats, loadMessages, handleCreateChat, handleDeleteChat],
  );
}
