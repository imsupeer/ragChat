'use client';

import { useCallback, useEffect, useMemo, useState, type RefObject } from 'react';
import { Braces, Cpu, Files, Gpu, PanelRightClose, PanelRightOpen, RefreshCw } from 'lucide-react';

const STATUS_POLL_MS = 30_000;

function getStatusColor(status: string) {
  if (status.toLowerCase().includes('offline')) {
    return 'border-red-500/30 bg-red-500/10 text-red-300';
  }

  if (status.toLowerCase().includes('no models')) {
    return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';
  }

  if (status.toLowerCase().includes('checking')) {
    return 'border-border bg-white/[0.03] text-gray-400';
  }

  return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
}

async function fetchServiceStatus(
  url: string,
  onSuccess: (data?: unknown) => string,
  onError: () => string,
): Promise<string> {
  try {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error('Request failed');
    }

    const data = await response.json();
    return onSuccess(data);
  } catch {
    return onError();
  }
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
  debugMode,
  panelOpen,
  panelToggleRef,
  onToggleDebugMode,
  onTogglePanel,
}: {
  documentCount: number;
  selectedDocumentCount: number;
  activeSourceCount: number;
  debugMode: boolean;
  panelOpen: boolean;
  panelToggleRef?: RefObject<HTMLButtonElement>;
  onToggleDebugMode: () => void;
  onTogglePanel: () => void;
}) {
  const [backendStatus, setBackendStatus] = useState('Checking backend...');
  const [ollamaStatus, setOllamaStatus] = useState('Checking Ollama...');
  const [refreshing, setRefreshing] = useState(false);

  const retrievalScope = useMemo(
    () => buildRetrievalScope(documentCount, selectedDocumentCount),
    [documentCount, selectedDocumentCount],
  );

  const refreshStatus = useCallback(async () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    const ollamaUrl = process.env.NEXT_PUBLIC_OLLAMA_URL ?? 'http://localhost:11434';

    setRefreshing(true);

    try {
      const [backend, ollama] = await Promise.all([
        fetchServiceStatus(`${apiUrl}/health`, () => 'Backend online', () => 'Backend offline'),
        fetchServiceStatus(
          `${ollamaUrl}/api/tags`,
          (data: unknown) => {
            const models = (data as { models?: unknown[] })?.models;
            return models && models.length > 0 ? 'Ollama ready' : 'Ollama running (no models)';
          },
          () => 'Ollama offline',
        ),
      ]);

      setBackendStatus(backend);
      setOllamaStatus(ollama);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
    const interval = setInterval(() => {
      void refreshStatus();
    }, STATUS_POLL_MS);

    return () => clearInterval(interval);
  }, [refreshStatus]);

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
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
          <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 ${getStatusColor(backendStatus)}`}>
            <Cpu className="h-4 w-4" />
            <span>{backendStatus}</span>
          </div>

          <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 ${getStatusColor(ollamaStatus)}`}>
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
