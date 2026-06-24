'use client';

import { FileSearch, FileUp, LoaderCircle, MessageSquareText, Sparkles } from 'lucide-react';

const DEMO_STEPS = [
  { step: 1, label: 'Upload', detail: 'Add PDF, Markdown, or TXT from the sidebar' },
  { step: 2, label: 'Index', detail: 'Wait for the upload queue to finish' },
  { step: 3, label: 'Ask', detail: 'Send a grounded question in the chat' },
  { step: 4, label: 'Inspect', detail: 'Review sources and debug evidence' },
] as const;

const STARTER_PROMPTS = [
  'Summarize the uploaded document.',
  'What are the main limitations mentioned?',
  'Which parts are most relevant to retrieval?',
  'Does the document mention OCR or scanned PDFs?',
] as const;

export function ChatEmptyState({
  onSuggestionSelect,
  hasDocuments,
  hasActiveUploads = false,
}: {
  onSuggestionSelect: (prompt: string) => Promise<void>;
  hasDocuments: boolean;
  hasActiveUploads?: boolean;
}) {
  if (!hasDocuments) {
    return (
      <div className="mx-auto flex max-w-4xl flex-col px-4 py-6" data-testid="chat-empty-state">
        <div
          className="rounded-[28px] border border-border bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.12),transparent_40%),rgba(255,255,255,0.02)] p-8 shadow-[0_30px_80px_rgba(0,0,0,0.25)]"
          data-testid="empty-state-upload-guidance"
        >
          <div className="flex items-start gap-4">
            <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-3 text-sky-300">
              <FileUp className="h-6 w-6" />
            </div>

            <div className="flex-1">
              <div className="app-label">Local RAG Workspace</div>
              <h2 className="mt-2 text-2xl font-semibold text-white">Upload a document to start</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-gray-300">
                Add a PDF, Markdown, or TXT file from the sidebar. Once it is indexed, you can ask grounded questions and inspect the sources used in
                each answer.
              </p>
            </div>
          </div>

          {hasActiveUploads ? (
            <div className="mt-6 flex items-start gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
              <LoaderCircle className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-amber-200" />
              <div>
                <div className="text-sm font-medium text-amber-100">Indexing is in progress</div>
                <p className="mt-1 text-sm leading-6 text-amber-100/80">
                  Wait for the upload queue to complete before asking document-specific questions.
                </p>
              </div>
            </div>
          ) : null}

          <div className="mt-8">
            <div className="app-label">How it works</div>
            <ol className="mt-4 grid gap-3 sm:grid-cols-2">
              {DEMO_STEPS.map((item) => (
                <li key={item.step} className="flex gap-3 rounded-2xl border border-border bg-white/[0.03] p-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-sky-500/30 bg-sky-500/10 text-sm font-semibold text-sky-100">
                    {item.step}
                  </div>
                  <div>
                    <div className="text-sm font-medium text-white">{item.label}</div>
                    <div className="mt-1 text-sm text-gray-400">{item.detail}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div className="mt-6 rounded-2xl border border-border bg-black/20 p-4 text-sm text-gray-400">
            <span className="font-medium text-gray-300">Local-first:</span> answers come from your uploaded documents, with sources and pipeline
            details you can review after each response.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col px-4 py-6" data-testid="chat-empty-state">
      <div className="rounded-[28px] border border-border bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.12),transparent_40%),rgba(255,255,255,0.02)] p-8 shadow-[0_30px_80px_rgba(0,0,0,0.25)]">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-3 text-sky-300">
            <MessageSquareText className="h-6 w-6" />
          </div>

          <div className="flex-1">
            <div className="app-label">Ready to chat</div>
            <h2 className="mt-2 text-2xl font-semibold text-white">Ask a grounded question</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-gray-300">
              The assistant retrieves relevant chunks, streams an answer, and attaches sources you can inspect in the evidence panel.
            </p>
          </div>
        </div>

        {hasActiveUploads ? (
          <div className="mt-6 flex items-start gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
            <LoaderCircle className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-amber-200" />
            <div>
              <div className="text-sm font-medium text-amber-100">Indexing is in progress</div>
              <p className="mt-1 text-sm leading-6 text-amber-100/80">
                Additional files are still indexing. You can ask now, or wait for the upload queue to finish.
              </p>
            </div>
          </div>
        ) : null}

        <div className="mt-8">
          <div className="app-label">Try asking</div>
          <div className="mt-4 flex flex-wrap gap-2">
            {STARTER_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                data-testid="empty-state-suggestion"
                onClick={() => void onSuggestionSelect(prompt)}
                className="rounded-full border border-border bg-white/[0.03] px-4 py-2 text-left text-sm text-gray-200 transition hover:border-sky-500/40 hover:bg-sky-500/10 hover:text-white"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-8 grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
            <FileSearch className="h-5 w-5 text-emerald-300" />
            <div className="mt-3 text-sm font-medium text-white">What you can inspect</div>
            <div className="mt-1 text-sm text-gray-400">
              Source excerpts, relevance scores, reranking details, and pipeline debug after each answer.
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
            <Sparkles className="h-5 w-5 text-violet-300" />
            <div className="mt-3 text-sm font-medium text-white">Document scope</div>
            <div className="mt-1 text-sm text-gray-400">
              Select documents in the sidebar to limit retrieval, or leave none selected to search the full knowledge base.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
