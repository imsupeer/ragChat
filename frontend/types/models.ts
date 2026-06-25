export type ModelPriority = 'speed' | 'balanced' | 'quality' | 'low_memory';

export type ModelUseCase =
  | 'general'
  | 'rag'
  | 'coding'
  | 'cybersecurity'
  | 'long_context'
  | 'agentic'
  | 'summarization';

export type ModelFit = 'comfortable' | 'tight' | 'offload' | 'not_recommended';

export type RecommendationCategory =
  | 'best_overall'
  | 'fastest'
  | 'best_coding'
  | 'best_rag'
  | 'stretch'
  | 'avoid';

export type HardwarePreset = {
  id: string;
  label: string;
  vram_gb: number | null;
  ram_gb: number;
  description: string;
};

export type HardwareProfileInput = {
  gpu_vendor?: string;
  gpu_model?: string;
  vram_gb?: number;
  ram_gb?: number;
  cpu?: string;
  os?: string;
  runtime?: string;
  priority: ModelPriority;
  use_cases: ModelUseCase[];
  needs_long_context?: boolean;
  prefer_installed_models?: boolean;
  installed_models?: string[];
};

export type ModelRecommendation = {
  rank: number;
  model_id: string;
  display_name: string;
  ollama_name: string;
  category: RecommendationCategory;
  fit: ModelFit;
  estimated_vram_gb: number;
  why: string[];
  tradeoffs: string[];
  suggested_context: string;
  run_command: string;
  install_command: string;
  catalog_known?: boolean;
  installed?: boolean | null;
  installed_match?: string | null;
  match_type?: string | null;
};

export type ModelAvoidEntry = {
  model: string;
  reason: string;
};

export type ModelRecommendationResponse = {
  status: 'ok';
  confidence: 'high' | 'medium' | 'low';
  hardware_summary: {
    vram_gb: number | null;
    ram_gb: number | null;
    detected_tier: string;
  };
  recommendations: ModelRecommendation[];
  avoid: ModelAvoidEntry[];
  notes: string[];
};

export const HARDWARE_PRESETS: HardwarePreset[] = [
  {
    id: 'low-memory-laptop',
    label: 'Low memory laptop',
    vram_gb: 0,
    ram_gb: 16,
    description: 'CPU-only or integrated graphics, 8–16GB RAM',
  },
  {
    id: 'entry-gpu',
    label: 'Entry GPU (6GB)',
    vram_gb: 6,
    ram_gb: 16,
    description: 'Entry discrete GPU such as GTX 1660 / RTX 3050 class',
  },
  {
    id: 'mid-range-gpu',
    label: 'Mid-range GPU (12GB)',
    vram_gb: 12,
    ram_gb: 32,
    description: 'RX 6700 XT / RTX 3060 12GB / RTX 4070 class',
  },
  {
    id: 'high-end-gpu',
    label: 'High-end consumer (24GB)',
    vram_gb: 24,
    ram_gb: 64,
    description: 'RTX 4090 / large workstation GPU',
  },
  {
    id: 'cpu-only',
    label: 'CPU-only',
    vram_gb: 0,
    ram_gb: 32,
    description: 'No discrete GPU; rely on RAM offload',
  },
];

export const USE_CASE_OPTIONS: { id: ModelUseCase; label: string }[] = [
  { id: 'general', label: 'General chat' },
  { id: 'rag', label: 'RAG / document Q&A' },
  { id: 'coding', label: 'Coding' },
  { id: 'cybersecurity', label: 'Cybersecurity learning' },
  { id: 'long_context', label: 'Long context' },
  { id: 'summarization', label: 'Summarization' },
];

export const PRIORITY_OPTIONS: { id: ModelPriority; label: string }[] = [
  { id: 'speed', label: 'Speed' },
  { id: 'balanced', label: 'Balanced' },
  { id: 'quality', label: 'Quality' },
  { id: 'low_memory', label: 'Low memory' },
];

export const CATEGORY_LABELS: Record<RecommendationCategory, string> = {
  best_overall: 'Best overall',
  fastest: 'Fastest usable',
  best_coding: 'Best coding',
  best_rag: 'Best RAG',
  stretch: 'Stretch option',
  avoid: 'Avoid',
};

export const FIT_LABELS: Record<ModelFit, string> = {
  comfortable: 'Comfortable fit',
  tight: 'Tight fit',
  offload: 'Offload likely',
  not_recommended: 'Not recommended',
};

export type InstalledStatus = 'installed' | 'not_installed' | 'unknown';

export type QueryRewritePolicy = {
  use_chat_model: boolean;
  configured_model: string;
  effective_model: string;
};

export type ModelSettingsState = {
  status: 'ok';
  chat_model: string;
  default_chat_model: string;
  query_rewrite_model: string | null;
  use_chat_model_for_query_rewrite: boolean;
  source: 'default' | 'user';
  updated_at?: string | null;
  installed_status: InstalledStatus;
  installed_models: string[];
  catalog_known?: boolean;
  installed?: boolean | null;
  installed_match?: string | null;
  match_type?: string | null;
  install_command?: string;
  run_command?: string;
  query_rewrite?: QueryRewritePolicy;
  warning?: string;
};

export type UpdateModelSettingsInput = {
  chat_model: string;
  require_installed?: boolean;
};

export type ModelRuntimeStatus = {
  status: 'ok' | 'degraded';
  provider?: {
    name: string;
    display_name: string;
    capabilities: {
      chat: boolean;
      streaming: boolean;
      list_installed_models: boolean;
      list_running_models: boolean;
      preload: boolean;
      unload: boolean;
      keep_alive: boolean;
      openai_compatible: boolean;
    };
  };
  ollama: {
    reachable: boolean;
    status: 'ok' | 'unavailable' | 'error' | 'degraded';
    message: string | null;
  };
  active_model: {
    name: string;
    installed: boolean | null;
    installed_match?: string | null;
    match_type?: string | null;
    loaded?: boolean | null;
    loaded_match?: string | null;
    loaded_match_type?: string | null;
    source: 'default' | 'user';
    catalog_known: boolean;
    family?: string | null;
  };
  installed_models: Array<{
    name: string;
    family?: string | null;
    size?: number | null;
    modified_at?: string | null;
  }>;
  installed_models_count: number;
  running_models: Array<{
    name: string;
    expires_at?: string | null;
    size?: number | null;
    size_vram?: number | null;
  }>;
  settings: {
    chat_model: string;
    default_chat_model: string;
    source: 'default' | 'user';
    query_rewrite?: QueryRewritePolicy;
  };
  runtime: {
    keep_alive: string;
    preload_supported: boolean;
    unload_supported: boolean;
    installed_models_count?: number;
    running_models_count?: number;
    loaded_detection?: 'available' | 'unsupported' | 'unavailable';
    cold_start_likely?: boolean | null;
  };
  embeddings?: {
    provider: string;
    model: string;
    dimension: number;
    quality: string;
    zero_ollama_compatible: boolean;
    local_files_only?: boolean;
    device?: string;
    status?: string;
    message?: string | null;
    setup_command?: string;
    check_command?: string;
    collection?: {
      strategy?: string;
      active_collection?: string;
      status?: string;
      reindex_recommended?: boolean;
      total_chunks?: number;
      matching_chunks?: number;
      mismatched_provider_chunks?: number;
      mismatched_model_chunks?: number;
      mismatched_dimension_chunks?: number;
      legacy_chunks?: number;
      message?: string | null;
    };
    reindex?: {
      recommended?: boolean;
      dry_run_command?: string;
      run_command?: string;
      message?: string | null;
    };
  };
};

export type ModelRuntimeActionResponse = {
  status: 'ok' | 'error';
  model?: string;
  message: string;
  keep_alive?: string;
  install_command?: string;
  runtime?: ModelRuntimeStatus;
};
