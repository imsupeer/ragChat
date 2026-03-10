export type SourceReference = {
  source?: string;
  document?: string;
  page?: number | null;
  chunk_index?: number | null;
  text?: string;
  preview?: string;
};

export type MessageRole = 'user' | 'assistant';

export type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  sources?: SourceReference[];
  isStreaming?: boolean;
  error?: boolean;
};

export type ChatRequest = {
  question: string;
  document_ids?: string[] | null;
};

export type ChatResponse = {
  answer: string;
  sources: SourceReference[];
};

export type StreamEvent = { type: 'sources'; sources: SourceReference[] } | { type: 'token'; token: string } | { type: 'done' };
