'use client';

import { BrainCircuit, FileSearch, Sparkles } from 'lucide-react';

export function ChatEmptyState({
  onSuggestionSelect,
  hasDocuments,
}: {
  onSuggestionSelect: (prompt: string) => Promise<void>;
  hasDocuments: boolean;
}) {
  return (
    <div className="mx-auto flex max-w-4xl flex-col px-4 py-6">
      <div className="rounded-[28px] border border-border bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.12),transparent_40%),rgba(255,255,255,0.02)] p-8 shadow-[0_30px_80px_rgba(0,0,0,0.25)]">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-3 text-sky-300">
            <Sparkles className="h-6 w-6" />
          </div>

          <div className="flex-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-gray-400">AI Workspace</div>
            <h2 className="mt-2 text-2xl font-semibold text-white">Ask grounded questions and inspect how the answer was built.</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-gray-300">
              This interface is built to make the RAG pipeline visible: document selection, retrieval, reranking, streaming generation, and source
              inspection all stay in the loop.
            </p>
          </div>
        </div>

        <div className="mt-8 grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
            <BrainCircuit className="h-5 w-5 text-sky-300" />
            <div className="mt-3 text-sm font-medium text-white">Transparent pipeline</div>
            <div className="mt-1 text-sm text-gray-400">
              Retrieval, reranking, and generation states are surfaced instead of hidden behind a spinner.
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
            <FileSearch className="h-5 w-5 text-emerald-300" />
            <div className="mt-3 text-sm font-medium text-white">Inspectable evidence</div>
            <div className="mt-1 text-sm text-gray-400">
              Sources and debug data stay attached to the answer so you can verify what the model used.
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
            <Sparkles className="h-5 w-5 text-violet-300" />
            <div className="mt-3 text-sm font-medium text-white">Persistent workflow</div>
            <div className="mt-1 text-sm text-gray-400">
              Active chat, selected documents, and drafts are preserved so refreshes do not reset your context.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
