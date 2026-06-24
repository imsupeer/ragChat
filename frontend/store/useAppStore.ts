'use client';

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { ChatDebugInfo, ChatMessage, ChatSession } from '@/types/chat';
import type { DocumentItem, UploadQueueItem } from '@/types/document';

export type PipelineStage = 'idle' | 'retrieving' | 'reranking' | 'generating' | 'complete' | 'error';

type AppState = {
  chats: ChatSession[];
  chatsLoading: boolean;
  activeChatId: string | null;
  messagesByChat: Record<string, ChatMessage[]>;

  documents: DocumentItem[];
  documentsLoading: boolean;
  documentsError: string | null;
  selectedDocumentIds: string[];
  uploadQueue: UploadQueueItem[];

  isStreaming: boolean;
  streamError: string | null;
  pipelineStage: PipelineStage;
  pipelineDebug: ChatDebugInfo | null;
  activeAssistantId: string | null;

  debugMode: boolean;
  drafts: Record<string, string>;
  unsavedDraft: string;

  setChats: (chats: ChatSession[]) => void;
  setChatsLoading: (loading: boolean) => void;
  upsertChat: (chat: ChatSession) => void;
  removeChat: (chatId: string) => void;
  setActiveChatId: (chatId: string | null) => void;

  setMessages: (chatId: string, messages: ChatMessage[]) => void;
  appendMessage: (chatId: string, message: ChatMessage) => void;
  appendMessages: (chatId: string, messages: ChatMessage[]) => void;
  updateMessage: (chatId: string, messageId: string, updater: (message: ChatMessage) => ChatMessage) => void;

  setDocuments: (documents: DocumentItem[]) => void;
  setDocumentsLoading: (loading: boolean) => void;
  setDocumentsError: (error: string | null) => void;
  setSelectedDocumentIds: (documentIds: string[]) => void;
  toggleSelectedDocument: (documentId: string) => void;
  setUploadQueue: (items: UploadQueueItem[]) => void;
  updateUploadQueueItem: (localId: string, updater: (item: UploadQueueItem) => UploadQueueItem) => void;
  upsertUploadQueueItems: (items: UploadQueueItem[]) => void;
  removeUploadQueueItem: (localId: string) => void;

  startStreaming: (assistantId: string) => void;
  setPipelineStage: (stage: PipelineStage, debug?: ChatDebugInfo | null) => void;
  setStreamError: (error: string | null) => void;
  finishStreaming: (debug?: ChatDebugInfo | null) => void;
  resetStreaming: () => void;

  setDebugMode: (enabled: boolean) => void;
  setDraft: (chatId: string | null, value: string) => void;
  clearDraft: (chatId: string | null) => void;
};

function updateMessageCollection(collection: Record<string, ChatMessage[]>, chatId: string, updater: (messages: ChatMessage[]) => ChatMessage[]) {
  return {
    ...collection,
    [chatId]: updater(collection[chatId] ?? []),
  };
}

function uploadStatusPriority(status: UploadQueueItem['status']) {
  switch (status) {
    case 'uploading':
      return 0;
    case 'processing':
      return 1;
    case 'queued':
      return 2;
    case 'failed':
      return 3;
    case 'completed':
      return 4;
    default:
      return 5;
  }
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      chats: [],
      chatsLoading: true,
      activeChatId: null,
      messagesByChat: {},

      documents: [],
      documentsLoading: true,
      documentsError: null,
      selectedDocumentIds: [],
      uploadQueue: [],

      isStreaming: false,
      streamError: null,
      pipelineStage: 'idle',
      pipelineDebug: null,
      activeAssistantId: null,

      debugMode: false,
      drafts: {},
      unsavedDraft: '',

      setChats: (chats) => set({ chats }),
      setChatsLoading: (chatsLoading) => set({ chatsLoading }),
      upsertChat: (chat) =>
        set((state) => ({
          chats: [chat, ...state.chats.filter((current) => current.id !== chat.id)],
        })),
      removeChat: (chatId) =>
        set((state) => {
          const { [chatId]: _removed, ...remainingMessages } = state.messagesByChat;
          const { [chatId]: _removedDraft, ...remainingDrafts } = state.drafts;

          return {
            chats: state.chats.filter((chat) => chat.id !== chatId),
            activeChatId: state.activeChatId === chatId ? null : state.activeChatId,
            messagesByChat: remainingMessages,
            drafts: remainingDrafts,
          };
        }),
      setActiveChatId: (activeChatId) => set({ activeChatId }),

      setMessages: (chatId, messages) =>
        set((state) => ({
          messagesByChat: {
            ...state.messagesByChat,
            [chatId]: messages,
          },
        })),
      appendMessage: (chatId, message) =>
        set((state) => ({
          messagesByChat: updateMessageCollection(state.messagesByChat, chatId, (messages) => [...messages, message]),
        })),
      appendMessages: (chatId, messages) =>
        set((state) => ({
          messagesByChat: updateMessageCollection(state.messagesByChat, chatId, (current) => [...current, ...messages]),
        })),
      updateMessage: (chatId, messageId, updater) =>
        set((state) => ({
          messagesByChat: updateMessageCollection(state.messagesByChat, chatId, (messages) =>
            messages.map((message) => (message.id === messageId ? updater(message) : message)),
          ),
        })),

      setDocuments: (documents) => set({ documents }),
      setDocumentsLoading: (documentsLoading) => set({ documentsLoading }),
      setDocumentsError: (documentsError) => set({ documentsError }),
      setSelectedDocumentIds: (selectedDocumentIds) => set({ selectedDocumentIds }),
      toggleSelectedDocument: (documentId) =>
        set((state) => ({
          selectedDocumentIds: state.selectedDocumentIds.includes(documentId)
            ? state.selectedDocumentIds.filter((id) => id !== documentId)
            : [...state.selectedDocumentIds, documentId],
        })),
      setUploadQueue: (uploadQueue) => set({ uploadQueue }),
      updateUploadQueueItem: (localId, updater) =>
        set((state) => ({
          uploadQueue: state.uploadQueue.map((item) => (item.localId === localId ? updater(item) : item)),
        })),
      upsertUploadQueueItems: (items) =>
        set((state) => {
          const incomingIds = new Set(items.map((item) => item.localId));
          const preserved = state.uploadQueue.filter((item) => !incomingIds.has(item.localId));
          return {
            uploadQueue: [...preserved, ...items].sort((left, right) => uploadStatusPriority(left.status) - uploadStatusPriority(right.status)),
          };
        }),
      removeUploadQueueItem: (localId) =>
        set((state) => ({
          uploadQueue: state.uploadQueue.filter((item) => item.localId !== localId),
        })),

      startStreaming: (assistantId) =>
        set({
          isStreaming: true,
          streamError: null,
          pipelineStage: 'retrieving',
          pipelineDebug: null,
          activeAssistantId: assistantId,
        }),
      setPipelineStage: (pipelineStage, pipelineDebug = null) =>
        set((state) => ({
          pipelineStage,
          pipelineDebug: pipelineDebug ?? state.pipelineDebug,
        })),
      setStreamError: (streamError) =>
        set({
          streamError,
          pipelineStage: streamError ? 'error' : 'idle',
          isStreaming: false,
        }),
      finishStreaming: (pipelineDebug = null) =>
        set((state) => ({
          isStreaming: false,
          streamError: null,
          pipelineStage: 'complete',
          pipelineDebug: pipelineDebug ?? state.pipelineDebug,
          activeAssistantId: null,
        })),
      resetStreaming: () =>
        set({
          isStreaming: false,
          streamError: null,
          pipelineStage: 'idle',
          pipelineDebug: null,
          activeAssistantId: null,
        }),

      setDebugMode: (debugMode) => set({ debugMode }),
      setDraft: (chatId, value) =>
        set((state) => {
          if (!chatId) {
            return { unsavedDraft: value };
          }

          return {
            drafts: {
              ...state.drafts,
              [chatId]: value,
            },
          };
        }),
      clearDraft: (chatId) =>
        set((state) => {
          if (!chatId) {
            return { unsavedDraft: '' };
          }

          const { [chatId]: _removed, ...remaining } = state.drafts;
          return { drafts: remaining };
        }),
    }),
    {
      name: 'rag-chat-app-store',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        activeChatId: state.activeChatId,
        selectedDocumentIds: state.selectedDocumentIds,
        debugMode: state.debugMode,
        drafts: state.drafts,
        unsavedDraft: state.unsavedDraft,
      }),
    },
  ),
);
