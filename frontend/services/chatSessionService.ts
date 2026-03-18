import { apiFetch } from '@/services/api';
import type { ChatMessage, ChatSession } from '@/types/chat';

export function listChats() {
  return apiFetch<{ chats: ChatSession[] }>('/chats');
}

export function createChat(title?: string) {
  return apiFetch<{ chat: ChatSession }>('/chats', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ title }),
  });
}

export function deleteChat(chatId: string) {
  return apiFetch<{ message: string; chat_id: string }>(`/chats/${chatId}`, {
    method: 'DELETE',
  });
}

export function getChatMessages(chatId: string) {
  return apiFetch<{ chat: ChatSession; messages: ChatMessage[] }>(`/chats/${chatId}/messages`);
}
