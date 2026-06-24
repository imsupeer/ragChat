'use client';

import { useCallback, useEffect, useMemo, useState, type RefObject } from 'react';
import { Braces, Cpu, Files, Gpu, PanelRightClose, PanelRightOpen, RefreshCw } from 'lucide-react';
import type { ModelRuntimeStatus } from '@/types/models';

const BACKEND_STATUS_POLL_MS = 30_000;

function getStatusColor(status: string) {
  if (status.toLowerCase().includes('offline')) {
    return 'border-red-500/30 bg-red-500/10 text-red-300';
  }

  if (status.toLowerCase().includes('missing') || status.toLowerCase().includes('not installed')) {
    return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';
  }

  if (status.toLowerCase().includes('degraded')) {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-200';
  }

  if (status.toLowerCase().includes('no models')) {
    return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';
  }

  if (status.toLowerCase().includes('cold start')) {
    return 'border-sky-500/30 bg-sky-500/10 text-sky-200';
  }

  if (status.toLowerCase().includes('loaded') && !status.toLowerCase().includes('not')) {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
  }

  if (status.toLowerCase().includes('unknown')) {
    return 'border-border bg-white/[0.03] text-gray-400';
  }

  if (status.toLowerCase().includes('checking') || status.toLowerCase().includes('loading')) {
    return 'border-border bg-white/[0.03] text-gray-400';
  }

  return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
}

function deriveModelRuntimeHeaderStatus(
  runtime: ModelRuntimeStatus | null,
  loading: boolean,
): { label: string; title: string; dotClass: string } {
  if (loading) {
    return {
      label: 'Checking runtime…',
      title: 'Loading local Ollama runtime status from the backend.',
      dotClass: 'bg-gray-400',
    };
  }

  if (!runtime) {
    return {
      label: 'Runtime unknown',
      title: 'Model runtime status is not available yet.',
      dotClass: 'bg-gray-500',
    };
  }

  if (!runtime.ollama.reachable) {
    return {
      label: 'Offline',
      title: runtime.ollama.message ?? 'Ollama is unreachable on the configured local URL.',
      dotClass: 'bg-red-400',
    };
  }

  if (runtime.active_model.installed === false) {
    return {
      label: 'Missing',
      title:
        runtime.ollama.message ??
        `Selected chat model ${runtime.active_model.name} is not installed locally.`,
      dotClass: 'bg-yellow-400',
    };
  }

  if (runtime.ollama.status === 'degraded') {
    return {
      label: 'Runtime degraded',
      title: runtime.ollama.message ?? 'Ollama is reachable but runtime checks reported a degraded state.',
      dotClass: 'bg-amber-400',
    };
  }

  if (runtime.active_model.loaded === true) {
    return {
      label: 'Loaded',
      title: 'Selected chat model is installed locally and loaded in Ollama memory.',
      dotClass: 'bg-emerald-400',
    };
  }

  if (runtime.runtime.cold_start_likely) {
    return {
      label: 'Cold start likely',
      title: 'Selected model is installed locally but not loaded. The next response may have cold-start latency.',
      dotClass: 'bg-sky-400',
    };
  }

  if (runtime.runtime.loaded_detection === 'unsupported' || runtime.runtime.loaded_detection === 'unavailable') {
    return {
      label: 'Unknown',
      title: 'Installed status is available, but loaded-model detection is not available from this Ollama runtime.',
      dotClass: 'bg-gray-400',
    };
  }

  return {
    label: 'Installed locally',
    title: 'Ollama is reachable and the selected chat model is installed locally.',
    dotClass: 'bg-emerald-400',
  };
}

function deriveOllamaServiceStatus(runtime: ModelRuntimeStatus | null, loading: boolean): string {
  if (loading) {
    return 'Checking Ollama…';
  }

  if (!runtime) {
    return 'Ollama unknown';
  }

  if (!runtime.ollama.reachable) {
    return 'Ollama offline';
  }

  if (runtime.active_model.installed === false) {
    return 'Selected model not installed';
  }

  if (runtime.installed_models_count === 0) {
    return 'Ollama online (no models)';
  }

  return 'Ollama online';
}

function buildRetrievalScope(documentCount: number, selectedDocumentCount: number) {
  if (documentCount === 0) {
    return {
      label: 'No documents indexed',
      title: 'Upload and index a document from the sidebar before asking grounded questions.',
    };
  }

  if (selectedDocumentCount === 0) {
    const docLabel = documentCount === 1 ? '1 doc' : `${documentCount} docs`;
    return {
      label: `Searching all documents · ${docLabel}`,
      title: 'No documents are selected, so retrieval searches the full indexed knowledge base.',
    };
  }

  const selectedLabel = selectedDocumentCount === 1 ? '1 selected' : `${selectedDocumentCount} selected`;
  return {
    label: `Scoped to ${selectedLabel}`,
    title: 'Only selected documents in the sidebar are included in retrieval.',
  };
}

export function Header({
  documentCount,
  selectedDocumentCount,
  activeSourceCount,
  chatModel,
  modelRuntime,
  modelRuntimeLoading,
  onRefreshModelRuntime,
  debugMode,
  panelOpen,
  panelToggleRef,
  onToggleDebugMode,
  onTogglePanel,
}: {
  documentCount: number;
  selectedDocumentCount: number;
  activeSourceCount: number;
  chatModel: string | null;
  modelRuntime: ModelRuntimeStatus | null;
  modelRuntimeLoading: boolean;
  onRefreshModelRuntime?: () => Promise<void>;
  debugMode: boolean;
  panelOpen: boolean;
  panelToggleRef?: RefObject<HTMLButtonElement>;
  onToggleDebugMode: () => void;
  onTogglePanel: () => void;
}) {
  const [backendStatus, setBackendStatus] = useState('Checking backend...');
  const [refreshing, setRefreshing] = useState(false);

  const retrievalScope = useMemo(
    () => buildRetrievalScope(documentCount, selectedDocumentCount),
    [documentCount, selectedDocumentCount],
  );

  const runtimeHeaderStatus = useMemo(
    () => deriveModelRuntimeHeaderStatus(modelRuntime, modelRuntimeLoading),
    [modelRuntime, modelRuntimeLoading],
  );

  const ollamaStatus = useMemo(
    () => deriveOllamaServiceStatus(modelRuntime, modelRuntimeLoading),
    [modelRuntime, modelRuntimeLoading],
  );

  const refreshBackendStatus = useCallback(async () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

    try {
      const response = await fetch(`${apiUrl}/health`, { cache: 'no-store' });
      setBackendStatus(response.ok ? 'Backend online' : 'Backend offline');
    } catch {
      setBackendStatus('Backend offline');
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    setRefreshing(true);

    try {
      await Promise.all([refreshBackendStatus(), onRefreshModelRuntime?.() ?? Promise.resolve()]);
    } finally {
      setRefreshing(false);
    }
  }, [onRefreshModelRuntime, refreshBackendStatus]);

  useEffect(() => {
    void refreshBackendStatus();
    const interval = setInterval(() => {
      void refreshBackendStatus();
    }, BACKEND_STATUS_POLL_MS);

    return () => clearInterval(interval);
  }, [refreshBackendStatus]);

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
      <div>
        <div className="app-label">Local RAG Workspace</div>
        <h1 className="mt-2 text-2xl font-semibold text-white">Grounded chat with inspectable evidence</h1>
        <p className="mt-2 max-w-2xl text-sm leading-7 text-gray-400">
          Ask questions, constrain retrieval to selected documents, and inspect source evidence, reranking, and generation details in one workspace.
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <div
            data-testid="retrieval-scope-badge"
            title={retrievalScope.title}
            className="app-badge-violet gap-2 px-3 py-1.5 text-sm"
          >
            <Files className="h-4 w-4 shrink-0" />
            <span>{retrievalScope.label}</span>
          </div>

          {activeSourceCount > 0 ? (
            <div title="Sources attached to the answer currently shown in the evidence panel" className="app-badge px-3 py-1.5">
              {activeSourceCount} source{activeSourceCount === 1 ? '' : 's'} in evidence
            </div>
          ) : null}

          {chatModel ? (
            <div
              data-testid="active-chat-model-badge"
              title="Selected chat model used for generation"
              className="app-badge px-3 py-1.5"
              aria-label={`Selected chat model: ${chatModel}`}
            >
              Selected chat model: <span className="font-mono">{chatModel}</span>
            </div>
          ) : null}

          <div
            data-testid="model-runtime-header-status"
            title={runtimeHeaderStatus.title}
            aria-label={`Model runtime: ${runtimeHeaderStatus.label}`}
            className={`app-badge flex items-center gap-2 px-3 py-1.5 ${getStatusColor(runtimeHeaderStatus.label)}`}
          >
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${runtimeHeaderStatus.dotClass}`}
              aria-hidden="true"
            />
            <span>{runtimeHeaderStatus.label}</span>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
          <div
            data-testid="backend-status-badge"
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 ${getStatusColor(backendStatus)}`}
          >
            <Cpu className="h-4 w-4" />
            <span>{backendStatus}</span>
          </div>

          <div
            data-testid="ollama-status-badge"
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 ${getStatusColor(ollamaStatus)}`}
          >
            <Gpu className="h-4 w-4" />
            <span>{ollamaStatus}</span>
          </div>

          <button
            type="button"
            data-testid="service-status-refresh"
            aria-label="Refresh service status"
            onClick={() => void refreshStatus()}
            disabled={refreshing}
            className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-white/[0.04] text-gray-300 transition hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden="true" />
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!panelOpen && activeSourceCount > 0 ? (
            <button
              type="button"
              data-testid="evidence-panel-mobile-cta"
              onClick={onTogglePanel}
              className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-full border border-sky-500/40 bg-sky-500/15 px-4 py-2 text-sm text-sky-100 transition hover:bg-sky-500/25 xl:hidden"
            >
              View evidence and debug ({activeSourceCount} source{activeSourceCount === 1 ? '' : 's'})
            </button>
          ) : null}

          <button
            type="button"
            onClick={onToggleDebugMode}
            aria-pressed={debugMode}
            aria-label={debugMode ? 'Hide technical metadata' : 'Show technical metadata'}
            className={`focus-ring inline-flex min-h-10 items-center gap-2 rounded-full border px-4 py-2 text-sm transition xl:min-h-0 xl:px-3 xl:py-1.5 ${
              debugMode ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.04] text-gray-300 hover:text-white'
            }`}
          >
            <Braces className="h-4 w-4" aria-hidden="true" />
            {debugMode ? 'Hide technical metadata' : 'Show technical metadata'}
          </button>

          <button
            ref={panelToggleRef}
            type="button"
            data-testid="evidence-panel-toggle"
            onClick={onTogglePanel}
            aria-expanded={panelOpen}
            aria-controls="evidence-panel"
            aria-label={panelOpen ? 'Close evidence panel' : 'Open evidence panel'}
            className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-full border border-border bg-white/[0.04] px-4 py-2 text-sm text-gray-300 transition hover:text-white xl:min-h-0 xl:px-3 xl:py-1.5"
          >
            {panelOpen ? <PanelRightClose className="h-4 w-4" aria-hidden="true" /> : <PanelRightOpen className="h-4 w-4" aria-hidden="true" />}
            <span className="xl:hidden">{panelOpen ? 'Close panel' : 'Open evidence panel'}</span>
            <span className="hidden xl:inline">{panelOpen ? 'Hide evidence panel' : 'Show evidence panel'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
