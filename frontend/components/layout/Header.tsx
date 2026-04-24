'use client';

import { useEffect, useState } from 'react';
import { Bug, Cpu, Files, Gpu, PanelRightOpen, PanelRightClose } from 'lucide-react';

function getStatusColor(status: string) {
  if (status.toLowerCase().includes('offline')) {
    return 'border-red-500/30 bg-red-500/10 text-red-300';
  }

  if (status.toLowerCase().includes('no models')) {
    return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';
  }

  return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
}

async function checkService(url: string, onSuccess: (data?: unknown) => string, onError: () => string, setStatus: (status: string) => void) {
  try {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error();

    const data = await response.json();
    setStatus(onSuccess(data));
  } catch {
    setStatus(onError());
  }
}

export function Header({
  documentCount,
  selectedDocumentCount,
  activeSourceCount,
  debugMode,
  panelOpen,
  onToggleDebugMode,
  onTogglePanel,
}: {
  documentCount: number;
  selectedDocumentCount: number;
  activeSourceCount: number;
  debugMode: boolean;
  panelOpen: boolean;
  onToggleDebugMode: () => void;
  onTogglePanel: () => void;
}) {
  const [backendStatus, setBackendStatus] = useState('Checking backend...');
  const [ollamaStatus, setOllamaStatus] = useState('Checking Ollama...');

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    const ollamaUrl = process.env.NEXT_PUBLIC_OLLAMA_URL ?? 'http://localhost:11434';

    void checkService(
      `${apiUrl}/health`,
      () => 'Backend online',
      () => 'Backend offline',
      setBackendStatus,
    );

    void checkService(
      `${ollamaUrl}/api/tags`,
      (data: any) => (data?.models?.length > 0 ? 'Ollama ready' : 'Ollama running (no models)'),
      () => 'Ollama offline',
      setOllamaStatus,
    );
  }, []);

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-gray-400">Local RAG Workspace</div>
        <h1 className="mt-2 text-2xl font-semibold text-white">Grounded chat with inspectable evidence</h1>
        <p className="mt-2 max-w-2xl text-sm leading-7 text-gray-400">
          Ask questions, constrain retrieval to selected documents, and inspect source evidence, reranking, and generation details in one workspace.
        </p>
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
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onToggleDebugMode}
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition ${
              debugMode ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.04] text-gray-300 hover:text-white'
            }`}
          >
            <Bug className="h-4 w-4" />
            {debugMode ? 'Debug mode on' : 'Debug mode off'}
          </button>

          <button
            type="button"
            onClick={onTogglePanel}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-white/[0.04] px-3 py-1.5 text-sm text-gray-300 transition hover:text-white"
          >
            {panelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
            {panelOpen ? 'Hide evidence panel' : 'Show evidence panel'}
          </button>
        </div>
      </div>
    </div>
  );
}
