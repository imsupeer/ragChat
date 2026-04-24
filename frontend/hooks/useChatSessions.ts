'use client';

import { useCallback, useEffect, useRef } from 'react';
import { createChat, deleteChat, getChatMessages, listChats, renameChat } from '@/services/chatSessionService';
import { useAppStore } from '@/store/useAppStore';

export function useChatSessions() {
  const chats = useAppStore((state) => state.chats);
  const activeChatId = useAppStore((state) => state.activeChatId);
  const chatsLoading = useAppStore((state) => state.chatsLoading);
  const messagesByChat = useAppStore((state) => state.messagesByChat);

  const setChats = useAppStore((state) => state.setChats);
  const setChatsLoading = useAppStore((state) => state.setChatsLoading);
  const setActiveChatId = useAppStore((state) => state.setActiveChatId);
  const setMessages = useAppStore((state) => state.setMessages);
  const upsertChat = useAppStore((state) => state.upsertChat);
  const removeChat = useAppStore((state) => state.removeChat);

  const skipNextLoadChatIdRef = useRef<string | null>(null);

  const refreshChats = useCallback(async () => {
    setChatsLoading(true);

    try {
      const data = await listChats();
      setChats(data.chats);

      if (!data.chats.length) {
        setActiveChatId(null);
        return;
      }

      if (!activeChatId || !data.chats.some((chat) => chat.id === activeChatId)) {
        setActiveChatId(data.chats[0].id);
      }
    } finally {
      setChatsLoading(false);
    }
  }, [activeChatId, setActiveChatId, setChats, setChatsLoading]);

  const loadMessages = useCallback(
    async (chatId: string) => {
      const data = await getChatMessages(chatId);
      setMessages(chatId, data.messages);
    },
    [setMessages],
  );

  const createAndActivateChat = useCallback(async () => {
    const data = await createChat();
    skipNextLoadChatIdRef.current = data.chat.id;
    upsertChat(data.chat);
    setActiveChatId(data.chat.id);
    setMessages(data.chat.id, []);
    return data.chat.id;
  }, [setActiveChatId, setMessages, upsertChat]);

  const handleCreateChat = useCallback(async () => {
    await createAndActivateChat();
  }, [createAndActivateChat]);

  const ensureActiveChat = useCallback(async () => {
    if (activeChatId) {
      return activeChatId;
    }

    return createAndActivateChat();
  }, [activeChatId, createAndActivateChat]);

  const handleDeleteChat = useCallback(
    async (chatId: string) => {
      await deleteChat(chatId);
      removeChat(chatId);

      const data = await listChats();
      setChats(data.chats);

      if (activeChatId === chatId) {
        const nextId = data.chats[0]?.id ?? null;
        setActiveChatId(nextId);

        if (nextId) {
          const msgData = await getChatMessages(nextId);
          setMessages(nextId, msgData.messages);
        }
      }
    },
    [activeChatId, removeChat, setActiveChatId, setChats, setMessages],
  );

  const handleRenameChat = useCallback(
    async (chatId: string, title: string) => {
      const response = await renameChat(chatId, title);
      upsertChat(response.chat);
    },
    [upsertChat],
  );

  useEffect(() => {
    void refreshChats();
  }, [refreshChats]);

  useEffect(() => {
    if (!activeChatId) {
      return;
    }

    if (skipNextLoadChatIdRef.current === activeChatId) {
      skipNextLoadChatIdRef.current = null;
      return;
    }

    void loadMessages(activeChatId);
  }, [activeChatId, loadMessages]);

  return {
    chats,
    activeChatId,
    messages: activeChatId ? (messagesByChat[activeChatId] ?? []) : [],
    loadingChats: chatsLoading,
    ensureActiveChat,
    setActiveChatId,
    setMessages,
    refreshChats,
    loadMessages,
    handleCreateChat,
    handleDeleteChat,
    handleRenameChat,
  };
}
