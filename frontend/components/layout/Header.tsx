'use client';

import { useEffect, useState } from 'react';
import { Cpu, Gpu, Files } from 'lucide-react';

export function Header({ documentCount }: { documentCount: number }) {
  const fallbackStatus = '';
  const [backendStatus, setBackendStatus] = useState(fallbackStatus);
  const [ollamaStatus, setOllamaStatus] = useState(fallbackStatus);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

    fetch(`${apiUrl}/health`, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error('Backend offline');
        return res.json();
      })
      .then(() => setBackendStatus('Backend online'))
      .catch(() => setBackendStatus('Backend offline'));
  }, []);

  useEffect(() => {
    const ollamaUrl = process.env.NEXT_PUBLIC_OLLAMA_URL ?? 'http://localhost:11434';

    fetch(`${ollamaUrl}/api/tags`, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error('Ollama offline');
        return res.json();
      })
      .then((data) => {
        if (data.models?.length > 0) {
          setOllamaStatus('Ollama ready');
        } else {
          setOllamaStatus('Ollama running (no models)');
        }
      })
      .catch(() => setOllamaStatus('Ollama offline'));
  }, []);

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
        <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-emerald-300">
          <Cpu className="h-4 w-4" />
          <span>{backendStatus}</span>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-emerald-300">
          <Gpu className="h-4 w-4" />
          <span>{ollamaStatus}</span>
        </div>
      </div>
    </header>
  );
}
