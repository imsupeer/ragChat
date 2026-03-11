'use client';

import { useEffect, useState } from 'react';
import { Cpu, Gpu, Files } from 'lucide-react';

function getStatusColor(status: string) {
  if (status.includes('offline')) return 'border-red-500/30 bg-red-500/10 text-red-300';

  if (status.includes('no models')) return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300';

  return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
}

async function checkService(url: string, onSuccess: (data?: any) => string, onError: () => string, setStatus: (status: string) => void) {
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error();

    const data = await res.json();
    setStatus(onSuccess(data));
  } catch {
    setStatus(onError());
  }
}

export function Header({ documentCount }: { documentCount: number }) {
  const [backendStatus, setBackendStatus] = useState('Checking backend...');
  const [ollamaStatus, setOllamaStatus] = useState('Checking Ollama...');

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    const ollamaUrl = process.env.NEXT_PUBLIC_OLLAMA_URL ?? 'http://localhost:11434';

    checkService(
      `${apiUrl}/health`,
      () => 'Backend online',
      () => 'Backend offline',
      setBackendStatus,
    );

    checkService(
      `${ollamaUrl}/api/tags`,
      (data) => (data.models?.length > 0 ? 'Ollama ready' : 'Ollama running (no models)'),
      () => 'Ollama offline',
      setOllamaStatus,
    );
  }, []);

  const backendColor = getStatusColor(backendStatus);
  const ollamaColor = getStatusColor(ollamaStatus);

  return (
    <header className="flex flex-col gap-3 border-b border-border px-6 py-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 className="text-xl font-semibold">RAG Chat</h1>
        <p className="text-sm text-gray-400">Chat with your documents using your local FastAPI + Ollama stack.</p>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm text-gray-300">
        <div className="flex items-center gap-2 rounded-full border border-border bg-white/5 px-3 py-1.5">
          <Files className="h-4 w-4" />
          <span>{documentCount} indexed</span>
        </div>

        <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 ${backendColor}`}>
          <Cpu className="h-4 w-4" />
          <span>{backendStatus}</span>
        </div>

        <div className={`flex items-center gap-2 rounded-full border px-3 py-1.5 ${ollamaColor}`}>
          <Gpu className="h-4 w-4" />
          <span>{ollamaStatus}</span>
        </div>
      </div>
    </header>
  );
}
