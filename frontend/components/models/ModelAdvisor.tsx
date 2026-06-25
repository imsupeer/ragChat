'use client';

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Cpu, Loader2, RotateCcw, Sparkles } from 'lucide-react';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { fetchModelRecommendations } from '@/services/modelRecommendations';
import {
  CATEGORY_LABELS,
  FIT_LABELS,
  HARDWARE_PRESETS,
  PRIORITY_OPTIONS,
  USE_CASE_OPTIONS,
  type HardwareProfileInput,
  type ModelPriority,
  type ModelRecommendationResponse,
  type ModelRuntimeStatus,
  type ModelSettingsState,
  type ModelUseCase,
} from '@/types/models';

const INITIAL_PROFILE: HardwareProfileInput = {
  priority: 'balanced',
  use_cases: ['general', 'rag'],
  prefer_installed_models: true,
  needs_long_context: false,
};

function parseInstalledModels(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function fitBadgeClass(fit: string) {
  if (fit === 'comfortable') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200';
  }
  if (fit === 'tight') {
    return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200';
  }
  if (fit === 'offload') {
    return 'border-sky-500/30 bg-sky-500/10 text-sky-200';
  }
  return 'border-red-500/30 bg-red-500/10 text-red-200';
}

function installedStatusLabel(status: ModelSettingsState['installed_status']) {
  if (status === 'installed') return 'Installed locally';
  if (status === 'not_installed') return 'Not installed locally';
  return 'Unknown';
}

function queryRewritePolicyLabel(settings: ModelSettingsState) {
  const policy = settings.query_rewrite;
  if (!policy) {
    if (settings.use_chat_model_for_query_rewrite) {
      return `Query rewriting follows the selected chat model (${settings.chat_model}).`;
    }
    const rewriteModel = settings.query_rewrite_model ?? settings.default_chat_model;
    return `Query rewriting uses the configured rewrite model (${rewriteModel}), not necessarily the selected chat model.`;
  }

  if (policy.use_chat_model) {
    return `Query rewriting follows the selected chat model (${policy.effective_model}).`;
  }

  return `Query rewriting uses the configured rewrite model (${policy.effective_model}), not necessarily the selected chat model.`;
}

function ollamaStatusLabel(runtime: ModelRuntimeStatus | null) {
  if (!runtime) return 'Unknown';
  if (!runtime.ollama.reachable) return 'Offline';
  if (runtime.ollama.status === 'degraded') return 'Degraded';
  return 'Online';
}

function matchTypeLabel(matchType?: string | null) {
  if (matchType === 'exact') return 'Exact install match';
  if (matchType === 'alias') return 'Alias install match';
  if (matchType === 'custom') return 'Custom installed model';
  return null;
}

function CopyableCommand({ command, testId }: { command: string; testId?: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2" data-testid={testId}>
      <code className="rounded-lg border border-border bg-black/30 px-2 py-1 font-mono text-[11px] text-gray-200">{command}</code>
      <button
        type="button"
        onClick={() => void handleCopy()}
        className="focus-ring rounded-full border border-border bg-white/[0.04] px-2 py-1 text-[11px] text-gray-300 transition hover:text-white"
        aria-label={`Copy command ${command}`}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}

function activeLoadedLabel(runtime: ModelRuntimeStatus | null) {
  if (!runtime) return 'Unknown';
  if (runtime.active_model.loaded === true) return 'Loaded';
  if (runtime.active_model.loaded === false) return 'Not loaded';
  return 'Unknown';
}

function activeInstalledLabel(runtime: ModelRuntimeStatus | null) {
  if (!runtime) return 'Unknown';
  if (runtime.active_model.installed === true) return 'Installed';
  if (runtime.active_model.installed === false) return 'Not installed';
  return 'Unknown';
}

function embeddingIndexLabel(status: string | undefined): string {
  switch (status) {
    case 'ok':
      return 'OK';
    case 'mixed':
      return 'Mixed providers - reindex recommended';
    case 'legacy':
      return 'Legacy metadata - reindex recommended';
    case 'empty':
      return 'Empty';
    case 'error':
      return 'Error';
    default:
      return 'Unknown';
  }
}

function runtimeGuidance(runtime: ModelRuntimeStatus | null, settings: ModelSettingsState | null) {
  if (!runtime) {
    return null;
  }

  if (runtime.active_model.installed === false) {
    const model = settings?.chat_model ?? runtime.active_model.name;
    return `Active model is not installed. Run: ollama pull ${model}`;
  }

  if (runtime.runtime.loaded_detection === 'unsupported' || runtime.runtime.loaded_detection === 'unavailable') {
    return 'Installed status is available, but this Ollama version does not expose loaded-model detection.';
  }

  if (runtime.active_model.installed === true && runtime.active_model.loaded === true) {
    return 'Active model is loaded. First response should avoid model-load cold start.';
  }

  if (runtime.runtime.cold_start_likely) {
    return 'Active model is installed but not loaded. The next response may have cold-start latency.';
  }

  return null;
}

export function ModelAdvisor({
  isStreaming,
  settings,
  settingsLoading,
  settingsError,
  actionMessage,
  runtime,
  runtimeLoading,
  runtimeError,
  runtimeActionMessage,
  runtimeActionLoading,
  onApplyChatModel,
  onResetChatModel,
  onRefreshRuntime,
  onPreloadActiveModel,
  onUnloadActiveModel,
}: {
  isStreaming: boolean;
  settings: ModelSettingsState | null;
  settingsLoading: boolean;
  settingsError: string | null;
  actionMessage: string | null;
  runtime: ModelRuntimeStatus | null;
  runtimeLoading: boolean;
  runtimeError: string | null;
  runtimeActionMessage: string | null;
  runtimeActionLoading: 'preload' | 'unload' | null;
  onApplyChatModel: (chatModel: string) => Promise<void>;
  onResetChatModel: () => Promise<void>;
  onRefreshRuntime: () => Promise<void>;
  onPreloadActiveModel: () => Promise<void>;
  onUnloadActiveModel: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [result, setResult] = useState<ModelRecommendationResponse | null>(null);
  const [profile, setProfile] = useState<HardwareProfileInput>(INITIAL_PROFILE);
  const [installedModelsText, setInstalledModelsText] = useState('');
  const [applyingModel, setApplyingModel] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [selectedInstalledModel, setSelectedInstalledModel] = useState('');

  const [runtimeActionError, setRuntimeActionError] = useState<string | null>(null);
  const selectedUseCases = useMemo(() => new Set(profile.use_cases), [profile.use_cases]);
  const displayError = error || settingsError || applyError || runtimeError || runtimeActionError;
  const combinedActionMessage = [actionMessage, runtimeActionMessage].filter(Boolean).join(' ');

  function updateProfile<K extends keyof HardwareProfileInput>(key: K, value: HardwareProfileInput[K]) {
    setProfile((current) => ({ ...current, [key]: value }));
  }

  function toggleUseCase(useCase: ModelUseCase) {
    setProfile((current) => {
      const next = new Set(current.use_cases);
      if (next.has(useCase)) {
        next.delete(useCase);
      } else {
        next.add(useCase);
      }
      return {
        ...current,
        use_cases: next.size ? Array.from(next) : ['general'],
      };
    });
  }

  function applyPreset(presetId: string) {
    const preset = HARDWARE_PRESETS.find((item) => item.id === presetId);
    if (!preset) {
      return;
    }

    setProfile((current) => ({
      ...current,
      vram_gb: preset.vram_gb === 0 ? undefined : (preset.vram_gb ?? undefined),
      ram_gb: preset.ram_gb,
    }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const payload: HardwareProfileInput = {
        ...profile,
        installed_models: installedModelsText ? parseInstalledModels(installedModelsText) : undefined,
      };
      const response = await fetchModelRecommendations(payload);
      setResult(response);
    } catch (submitError) {
      setResult(null);
      setError(submitError instanceof Error ? submitError.message : 'Failed to fetch recommendations');
    } finally {
      setLoading(false);
    }
  }

  async function handlePreload() {
    if (isStreaming) {
      setRuntimeActionError('Stop the current generation before changing model runtime state.');
      return;
    }
    setRuntimeActionError(null);
    try {
      await onPreloadActiveModel();
    } catch (preloadError) {
      const message = preloadError instanceof Error ? preloadError.message : 'Failed to preload model';
      setRuntimeActionError(message.includes('ollama pull') ? message : `${message} First-token latency may improve after preload.`);
    }
  }

  async function handleUnload() {
    if (isStreaming) {
      setRuntimeActionError('Stop the current generation before changing model runtime state.');
      return;
    }
    setRuntimeActionError(null);
    try {
      await onUnloadActiveModel();
    } catch (unloadError) {
      setRuntimeActionError(unloadError instanceof Error ? unloadError.message : 'Failed to unload model');
    }
  }

  async function handleUseForChat(chatModel: string) {
    if (isStreaming) {
      setApplyError('Stop the current generation before switching models.');
      return;
    }

    setApplyError(null);
    setApplyingModel(chatModel);

    try {
      await onApplyChatModel(chatModel);
    } catch (useError) {
      const message = useError instanceof Error ? useError.message : 'Failed to set chat model';
      if (message.toLowerCase().includes('not installed')) {
        setApplyError(`${message} Run: ollama pull ${chatModel}`);
      } else {
        setApplyError(message);
      }
    } finally {
      setApplyingModel(null);
    }
  }

  async function handleReset() {
    if (isStreaming) {
      setApplyError('Stop the current generation before switching models.');
      return;
    }

    setApplyError(null);
    setResetting(true);

    try {
      await onResetChatModel();
    } catch (resetError) {
      setApplyError(resetError instanceof Error ? resetError.message : 'Failed to reset chat model');
    } finally {
      setResetting(false);
    }
  }

  async function handleApplyInstalledModel() {
    if (!selectedInstalledModel) {
      return;
    }
    await handleUseForChat(selectedInstalledModel);
  }

  return (
    <div className="rounded-[24px] border border-border bg-black/15 p-4" data-testid="model-advisor">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-violet-300" aria-hidden="true" />
          <div className="text-sm font-semibold text-white">Model Advisor</div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          aria-expanded={expanded}
          aria-controls="model-advisor-panel"
          aria-label={expanded ? 'Collapse model advisor' : 'Expand model advisor'}
          className="focus-ring inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.03] px-3 py-1 text-xs text-gray-300 transition hover:text-white"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {expanded ? 'Hide' : 'Show'}
        </button>
      </div>

      <div className="space-y-2 text-xs text-gray-400" data-testid="model-advisor-current-model">
        <p>Local Ollama model picks based on your hardware. Estimates are approximate - longer context uses more memory.</p>
        {settingsLoading ? (
          <p>Loading chat model settings…</p>
        ) : settings ? (
          <div className="rounded-xl border border-border bg-white/[0.03] p-3 text-gray-300">
            <div>
              Selected chat model: <span className="font-mono text-white">{settings.chat_model}</span>
            </div>
            <div className="mt-1 text-gray-500">
              Default: <span className="font-mono">{settings.default_chat_model}</span> · Installed locally:{' '}
              {installedStatusLabel(settings.installed_status)}
              {settings.match_type && settings.match_type !== 'none' ? <span> · {matchTypeLabel(settings.match_type)}</span> : null}
            </div>
            {settings.installed_match && settings.installed_match !== settings.chat_model ? (
              <p className="mt-1 text-[11px] text-gray-500">
                Ollama reports installed as <span className="font-mono">{settings.installed_match}</span>
              </p>
            ) : null}
            {settings.installed_status === 'not_installed' && settings.install_command ? (
              <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2 text-amber-100/90">
                <p className="text-[11px]">Install manually in your terminal (not run by this app):</p>
                <CopyableCommand command={settings.install_command} testId="model-settings-install-command" />
              </div>
            ) : null}
            <details className="mt-3 text-[11px] leading-5 text-gray-500">
              <summary className="cursor-pointer text-gray-400">Selected vs installed vs loaded vs preload</summary>
              <ul className="mt-2 list-disc space-y-1 pl-4">
                <li>Selected chat model is what generation will request from Ollama.</li>
                <li>Installed locally means Ollama reports the model on disk via /api/tags.</li>
                <li>Loaded in memory means Ollama reports the model running via /api/ps when supported.</li>
                <li>Preload keeps weights warm in memory; unload frees memory without changing selection.</li>
                <li>Pull commands are manual - this app never runs ollama pull.</li>
              </ul>
            </details>
            <p className="mt-2 text-[11px] leading-5 text-gray-500" data-testid="model-advisor-query-rewrite-policy">
              {queryRewritePolicyLabel(settings)}
            </p>
            <button
              type="button"
              data-testid="model-advisor-reset"
              disabled={resetting || isStreaming}
              onClick={() => void handleReset()}
              className="focus-ring mt-3 inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.04] px-3 py-1.5 text-xs text-gray-300 transition hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Reset to default
            </button>
          </div>
        ) : null}
        <div className="rounded-xl border border-border bg-white/[0.03] p-3 text-gray-300" data-testid="model-runtime-status">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-sky-300">Local runtime</div>
          {runtimeLoading ? (
            <p className="text-xs text-gray-400">Loading runtime status…</p>
          ) : (
            <div className="space-y-1 text-xs">
              {runtime?.provider?.display_name ? (
                <p data-testid="model-runtime-provider">
                  Provider: <span className="text-white">{runtime.provider.display_name}</span>
                </p>
              ) : null}
              {runtime?.embeddings ? (
                <p data-testid="model-runtime-embeddings">
                  Embeddings:{' '}
                  <span className="text-white">
                    {runtime.embeddings.provider === 'local_hash'
                      ? 'Local hash demo'
                      : runtime.embeddings.provider === 'sentence_transformers'
                        ? 'Sentence Transformers'
                        : runtime.embeddings.provider === 'ollama'
                          ? 'Ollama'
                          : runtime.embeddings.provider}
                  </span>
                  {runtime.embeddings.model ? <span className="text-gray-400"> · {runtime.embeddings.model}</span> : null}
                </p>
              ) : null}
              {runtime?.embeddings?.provider === 'local_hash' ? (
                <p className="text-[11px] leading-5 text-amber-200/90" data-testid="model-runtime-embeddings-warning">
                  Demo-quality local embeddings. For better semantic retrieval, configure Ollama or a stronger embedding provider.
                </p>
              ) : null}
              {runtime?.embeddings?.provider === 'sentence_transformers' && runtime.embeddings.status && runtime.embeddings.status !== 'ok' ? (
                <p className="text-[11px] leading-5 text-amber-200/90" data-testid="model-runtime-embeddings-st-warning">
                  Install/cache the sentence-transformers model, or use local_hash for dependency-free demo mode.
                  {runtime.embeddings.message ? ` ${runtime.embeddings.message}` : ''}
                </p>
              ) : null}
              {runtime?.embeddings?.collection ? (
                <p data-testid="model-runtime-embedding-index">
                  Embedding index: <span className="text-white">{embeddingIndexLabel(runtime.embeddings.collection.status)}</span>
                </p>
              ) : null}
              {runtime?.embeddings?.collection?.strategy ? (
                <p data-testid="model-runtime-chroma-strategy">
                  Chroma strategy: <span className="text-white">{runtime.embeddings.collection.strategy}</span>
                  {runtime.embeddings.collection.active_collection ? (
                    <span className="text-gray-400"> · {runtime.embeddings.collection.active_collection}</span>
                  ) : null}
                </p>
              ) : null}
              {runtime?.embeddings?.collection?.strategy === 'per_embedding_provider' ? (
                <p className="text-[11px] leading-5 text-gray-500" data-testid="model-runtime-collection-isolation">
                  Vectors are isolated per embeddings provider so switching providers does not query incompatible vector spaces.
                </p>
              ) : null}
              {runtime?.embeddings?.collection?.reindex_recommended || runtime?.embeddings?.reindex?.recommended ? (
                <p className="text-[11px] leading-5 text-amber-200/90" data-testid="model-runtime-reindex-warning">
                  {runtime.embeddings.reindex?.message ||
                    'Reindex recommended for the active embeddings provider. Run a dry-run first, then reindex when ready.'}
                  {runtime.embeddings.collection?.message ? ` ${runtime.embeddings.collection.message}` : ''}
                </p>
              ) : null}
              {runtime?.embeddings?.reindex?.recommended ? (
                <p className="text-[11px] leading-5 text-gray-500" data-testid="model-runtime-reindex-command">
                  Dry-run: <span className="font-mono text-gray-300">{runtime.embeddings.reindex.dry_run_command}</span>
                </p>
              ) : null}
              <p>
                Ollama: <span className="text-white">{ollamaStatusLabel(runtime)}</span>
              </p>
              <p>
                Selected model installed locally: <span className="text-white">{activeInstalledLabel(runtime)}</span>
              </p>
              <p data-testid="model-runtime-loaded-status">
                Selected model loaded in memory: <span className="text-white">{activeLoadedLabel(runtime)}</span>
              </p>
              <p>
                Installed models: <span className="text-white">{runtime?.installed_models_count ?? '-'}</span>
                {' · '}
                Running models: <span className="text-white">{runtime?.runtime.running_models_count ?? '-'}</span>
              </p>
              <p>
                Keep alive: <span className="font-mono text-white">{runtime?.runtime.keep_alive ?? '-'}</span>
              </p>
              {runtimeGuidance(runtime, settings) ? (
                <p className="text-[11px] leading-5 text-gray-400" data-testid="model-runtime-guidance">
                  {runtimeGuidance(runtime, settings)}
                </p>
              ) : null}
              <p className="text-[11px] leading-5 text-gray-500">
                {runtime?.provider?.name === 'llama_cpp'
                  ? 'llama.cpp manages the model through the local server process. Preload checks server reachability; unload is not supported.'
                  : 'Preload asks Ollama to keep the selected model warm in memory. Unload releases loaded weights; your selected model and on-disk install stay unchanged. Pull/run commands are manual only.'}
              </p>
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              data-testid="model-runtime-refresh"
              aria-label="Refresh model runtime status"
              disabled={runtimeLoading || runtimeActionLoading !== null}
              onClick={() => void onRefreshRuntime()}
              className="focus-ring rounded-full border border-border bg-white/[0.04] px-3 py-1.5 text-xs text-gray-300 transition hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Refresh runtime
            </button>
            <button
              type="button"
              data-testid="model-runtime-preload"
              aria-label="Preload active chat model"
              disabled={isStreaming || runtimeActionLoading !== null || runtime?.runtime.preload_supported === false}
              onClick={() => void handlePreload()}
              className="focus-ring rounded-full border border-emerald-500/40 bg-emerald-500/15 px-3 py-1.5 text-xs text-emerald-100 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {runtimeActionLoading === 'preload' ? 'Preloading…' : 'Preload active model'}
            </button>
            {runtime?.runtime.unload_supported !== false ? (
              <button
                type="button"
                data-testid="model-runtime-unload"
                aria-label="Unload active chat model from memory"
                disabled={isStreaming || runtimeActionLoading !== null}
                onClick={() => void handleUnload()}
                className="focus-ring rounded-full border border-amber-500/40 bg-amber-500/15 px-3 py-1.5 text-xs text-amber-100 transition hover:bg-amber-500/25 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {runtimeActionLoading === 'unload' ? 'Unloading…' : 'Unload active model'}
              </button>
            ) : null}
          </div>
        </div>
        {combinedActionMessage ? <p className="text-emerald-300">{combinedActionMessage}</p> : null}
      </div>

      {expanded ? (
        <div id="model-advisor-panel" className="mt-4 space-y-4">
          {settings?.installed_models.length ? (
            <div>
              <label htmlFor="model-advisor-installed-select" className="mb-1 block text-xs font-medium text-gray-300">
                Installed Ollama models
              </label>
              <div className="flex gap-2">
                <select
                  id="model-advisor-installed-select"
                  value={selectedInstalledModel}
                  onChange={(event) => setSelectedInstalledModel(event.target.value)}
                  className="focus-ring min-w-0 flex-1 rounded-xl border border-border bg-black/30 px-3 py-2 text-sm text-white"
                >
                  <option value="">Choose installed model</option>
                  {settings.installed_models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  data-testid="model-advisor-use-installed"
                  disabled={!selectedInstalledModel || isStreaming || applyingModel !== null}
                  onClick={() => void handleApplyInstalledModel()}
                  className="focus-ring shrink-0 rounded-xl border border-sky-500/40 bg-sky-500/15 px-3 py-2 text-xs text-sky-100 transition hover:bg-sky-500/25 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Use for chat
                </button>
              </div>
            </div>
          ) : null}

          <form onSubmit={(event) => void handleSubmit(event)} className="space-y-4">
            <div>
              <label htmlFor="model-advisor-preset" className="mb-1 block text-xs font-medium text-gray-300">
                Hardware preset
              </label>
              <select
                id="model-advisor-preset"
                defaultValue=""
                onChange={(event) => applyPreset(event.target.value)}
                className="focus-ring w-full rounded-xl border border-border bg-black/30 px-3 py-2 text-sm text-white"
              >
                <option value="">Choose a preset (optional)</option>
                {HARDWARE_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="model-advisor-vram" className="mb-1 block text-xs font-medium text-gray-300">
                  VRAM (GB)
                </label>
                <input
                  id="model-advisor-vram"
                  type="number"
                  min="0"
                  step="0.5"
                  inputMode="decimal"
                  value={profile.vram_gb ?? ''}
                  onChange={(event) => updateProfile('vram_gb', event.target.value ? Number(event.target.value) : undefined)}
                  placeholder="e.g. 12"
                  className="focus-ring w-full rounded-xl border border-border bg-black/30 px-3 py-2 text-sm text-white"
                />
              </div>

              <div>
                <label htmlFor="model-advisor-ram" className="mb-1 block text-xs font-medium text-gray-300">
                  RAM (GB)
                </label>
                <input
                  id="model-advisor-ram"
                  type="number"
                  min="1"
                  step="1"
                  inputMode="numeric"
                  value={profile.ram_gb ?? ''}
                  onChange={(event) => updateProfile('ram_gb', event.target.value ? Number(event.target.value) : undefined)}
                  placeholder="e.g. 32"
                  className="focus-ring w-full rounded-xl border border-border bg-black/30 px-3 py-2 text-sm text-white"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="model-advisor-gpu" className="mb-1 block text-xs font-medium text-gray-300">
                  GPU model
                </label>
                <input
                  id="model-advisor-gpu"
                  type="text"
                  value={profile.gpu_model ?? ''}
                  onChange={(event) => updateProfile('gpu_model', event.target.value || undefined)}
                  placeholder="e.g. RX 6700 XT"
                  className="focus-ring w-full rounded-xl border border-border bg-black/30 px-3 py-2 text-sm text-white"
                />
              </div>

              <div>
                <label htmlFor="model-advisor-cpu" className="mb-1 block text-xs font-medium text-gray-300">
                  CPU model
                </label>
                <input
                  id="model-advisor-cpu"
                  type="text"
                  value={profile.cpu ?? ''}
                  onChange={(event) => updateProfile('cpu', event.target.value || undefined)}
                  placeholder="e.g. Ryzen 7 5700X3D"
                  className="focus-ring w-full rounded-xl border border-border bg-black/30 px-3 py-2 text-sm text-white"
                />
              </div>
            </div>

            <fieldset>
              <legend className="mb-2 text-xs font-medium text-gray-300">Priority</legend>
              <div className="flex flex-wrap gap-2">
                {PRIORITY_OPTIONS.map((option) => (
                  <label
                    key={option.id}
                    className={`focus-ring cursor-pointer rounded-full border px-3 py-1.5 text-xs transition ${
                      profile.priority === option.id
                        ? 'border-violet-500/40 bg-violet-500/15 text-violet-100'
                        : 'border-border bg-white/[0.03] text-gray-300 hover:text-white'
                    }`}
                  >
                    <input
                      type="radio"
                      name="model-advisor-priority"
                      value={option.id}
                      checked={profile.priority === option.id}
                      onChange={() => updateProfile('priority', option.id as ModelPriority)}
                      className="sr-only"
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="mb-2 text-xs font-medium text-gray-300">Use cases</legend>
              <div className="flex flex-wrap gap-2">
                {USE_CASE_OPTIONS.map((option) => {
                  const checked = selectedUseCases.has(option.id);
                  return (
                    <label
                      key={option.id}
                      className={`focus-ring cursor-pointer rounded-full border px-3 py-1.5 text-xs transition ${
                        checked ? 'border-sky-500/40 bg-sky-500/15 text-sky-100' : 'border-border bg-white/[0.03] text-gray-300 hover:text-white'
                      }`}
                    >
                      <input type="checkbox" checked={checked} onChange={() => toggleUseCase(option.id)} className="sr-only" />
                      {option.label}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <div>
              <label htmlFor="model-advisor-installed" className="mb-1 block text-xs font-medium text-gray-300">
                Installed Ollama models override (optional)
              </label>
              <textarea
                id="model-advisor-installed"
                rows={2}
                value={installedModelsText}
                onChange={(event) => setInstalledModelsText(event.target.value)}
                placeholder="llama3.2:3b, qwen3:8b"
                className="focus-ring w-full rounded-xl border border-border bg-black/30 px-3 py-2 text-sm text-white"
              />
            </div>

            <label className="flex items-center gap-2 text-xs text-gray-300">
              <input
                type="checkbox"
                checked={Boolean(profile.needs_long_context)}
                onChange={(event) => updateProfile('needs_long_context', event.target.checked)}
                className="rounded border-border bg-black/30"
              />
              Need longer context windows
            </label>

            {displayError ? <ErrorMessage message={displayError} /> : null}

            <button
              type="submit"
              disabled={loading}
              data-testid="model-advisor-submit"
              className="focus-ring inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl border border-violet-500/40 bg-violet-500/15 px-4 py-2 text-sm font-medium text-violet-100 transition hover:bg-violet-500/25 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              ) : (
                <Cpu className="h-4 w-4" aria-hidden="true" />
              )}
              {loading ? 'Generating recommendations…' : 'Get recommendations'}
            </button>
          </form>

          {result ? (
            <div className="space-y-3" data-testid="model-advisor-results">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-full border border-border bg-white/[0.04] px-2.5 py-1 text-gray-300">Confidence: {result.confidence}</span>
                <span className="rounded-full border border-border bg-white/[0.04] px-2.5 py-1 text-gray-300">
                  Tier: {result.hardware_summary.detected_tier.replaceAll('_', ' ')}
                </span>
              </div>

              {result.recommendations.map((item) => (
                <article
                  key={`${item.category}-${item.model_id}`}
                  data-testid={`model-recommendation-${item.category}`}
                  className="rounded-2xl border border-border bg-white/[0.03] p-3"
                >
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs uppercase tracking-wide text-violet-300">{CATEGORY_LABELS[item.category]}</div>
                      <h3 className="text-sm font-semibold text-white">{item.display_name}</h3>
                    </div>
                    <span className={`rounded-full border px-2.5 py-1 text-[11px] ${fitBadgeClass(item.fit)}`}>{FIT_LABELS[item.fit]}</span>
                  </div>

                  <p className="mb-2 font-mono text-xs text-gray-400" data-testid="model-run-command">
                    {item.run_command}
                  </p>
                  {item.install_command ? (
                    <p className="mb-2 font-mono text-xs text-gray-500" data-testid="model-install-command">
                      {item.install_command}
                    </p>
                  ) : null}
                  {item.installed === false ? (
                    <CopyableCommand command={item.install_command} testId={`model-install-copy-${item.category}`} />
                  ) : null}

                  <ul className="mb-2 space-y-1 text-xs text-gray-300">
                    {item.why.map((reason) => (
                      <li key={reason}>• {reason}</li>
                    ))}
                  </ul>

                  {item.tradeoffs.length ? <p className="text-[11px] text-gray-500">Tradeoffs: {item.tradeoffs.join(' · ')}</p> : null}

                  <p className="mt-2 text-[11px] text-gray-500">
                    ~{item.estimated_vram_gb}GB est. VRAM · suggested context {item.suggested_context}
                  </p>

                  <button
                    type="button"
                    data-testid={`model-use-for-chat-${item.category}`}
                    disabled={isStreaming || applyingModel !== null}
                    onClick={() => void handleUseForChat(item.ollama_name)}
                    className="focus-ring mt-3 inline-flex min-h-9 items-center rounded-full border border-emerald-500/40 bg-emerald-500/15 px-3 py-1.5 text-xs text-emerald-100 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {applyingModel === item.ollama_name ? 'Applying…' : 'Use for chat'}
                  </button>
                </article>
              ))}

              {result.avoid.length ? (
                <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-3">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-200">Likely too heavy</div>
                  <ul className="space-y-2 text-xs text-red-100/90">
                    {result.avoid.map((item) => (
                      <li key={item.model}>
                        <span className="font-mono">{item.model}</span> - {item.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <ul className="space-y-1 text-[11px] leading-5 text-gray-500">
                {result.notes.map((note) => (
                  <li key={note}>• {note}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
