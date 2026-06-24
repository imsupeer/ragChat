export type SourceReference = {
  source?: string;
  document?: string;
  document_id?: string;
  chunk_id?: string;
  page?: number | null;
  chunk_index?: number | null;
  section_title?: string | null;
  section_path?: string | null;
  text?: string;
  preview?: string;
  score?: number | null;
  score_type?: string | null;
  rank?: number | null;
  retrieval_method?: string | null;
  retrieval_methods?: string[];
  retrieval_rank?: number | null;
  retrieval_score?: number | null;
  retrieval_score_type?: string | null;
  rerank_rank?: number | null;
  rerank_score?: number | null;
  dense_rank?: number | null;
  dense_score?: number | null;
  lexical_rank?: number | null;
  lexical_score?: number | null;
  fused_score?: number | null;
  metadata?: Record<string, unknown>;
};

export type MessageRole = 'user' | 'assistant';

export type ChatMessage = {
  id: string;
  chat_id?: string;
  role: MessageRole;
  content: string;
  sources?: SourceReference[];
  debug?: ChatDebugInfo;
  isStreaming?: boolean;
  error?: boolean;
  errorMessage?: string;
  created_at?: string;
};

export type ChatSession = {
  id: string;
  title: string;
  created_at?: string;
};

export type ChatRequest = {
  question: string;
  document_ids?: string[] | null;
  chat_id?: string | null;
  regenerate?: boolean;
};

export type RetrievalResultDebug = {
  rank?: number | null;
  chunk_id?: string | null;
  document_id?: string | null;
  source?: string | null;
  page?: number | null;
  chunk_index?: number | null;
  section_title?: string | null;
  section_path?: string | null;
  score?: number | null;
  score_type?: string | null;
  retrieval_method?: string | null;
  retrieval_methods?: string[];
  retrieval_rank?: number | null;
  retrieval_score?: number | null;
  retrieval_score_type?: string | null;
  rerank_rank?: number | null;
  rerank_score?: number | null;
  dense_rank?: number | null;
  dense_score?: number | null;
  lexical_rank?: number | null;
  lexical_score?: number | null;
  fused_score?: number | null;
  metadata?: Record<string, unknown>;
  preview: string;
};

export type ChatDebugInfo = {
  trace_id: string;
  retrieval?: {
    latency_ms: number;
    top_k: number;
    max_context_chunks: number;
    hybrid_enabled: boolean;
    retrieval_mode: 'dense' | 'hybrid';
    document_ids: string[];
    retrieved_count: number;
    used_count: number;
    candidate_count?: number;
    query?: string;
    results: RetrievalResultDebug[];
  };
  reranking?: {
    enabled: boolean;
    method?: string | null;
    latency_ms: number;
    top_m: number;
    top_k: number;
    candidate_count: number;
    kept_count: number;
    results: RetrievalResultDebug[];
  };
  prompt?: {
    latency_ms: number;
    answer_mode?: 'strict_rag' | 'hybrid_assistant' | string;
    used_chunk_count: number;
    used_chunk_ids: string[];
    used_chunks?: RetrievalResultDebug[];
    context_length_chars: number;
    context_token_estimate: number;
    prompt_length_chars: number;
    prompt_token_estimate: number;
  };
  generation?: {
    model: string;
    latency_ms: number;
    output_length_chars: number;
    output_token_estimate: number;
  };
  total_latency_ms?: number;
  query_rewriting?: {
    enabled: boolean;
    used: boolean;
    original_question: string;
    rewritten_query: string;
    history_turns_used: number;
    latency_ms: number;
  };
};

export type ChatResponse = {
  answer: string;
  sources: SourceReference[];
  debug?: ChatDebugInfo;
};

export type StreamEvent =
  | { type: 'sources'; sources: SourceReference[]; debug?: ChatDebugInfo }
  | { type: 'token'; token: string }
  | { type: 'done'; debug?: ChatDebugInfo }
  | { type: 'error'; message: string; code?: string; recoverable?: boolean };
