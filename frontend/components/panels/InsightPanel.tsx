'use client';

import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { BookOpenText, Bug, ChevronDown, ChevronUp, FileText, Gauge, Layers3, SearchCheck } from 'lucide-react';
import type { ChatDebugInfo, ChatMessage, RetrievalResultDebug, SourceReference } from '@/types/chat';

type PanelTab = 'sources' | 'debug';

function getSourceKey(item: Pick<SourceReference, 'chunk_id' | 'source' | 'chunk_index'>) {
  return item.chunk_id ?? `${item.source ?? 'unknown'}:${item.chunk_index ?? 'na'}`;
}

function formatNumber(value?: number | null, digits = 3) {
  if (value == null || Number.isNaN(value)) {
    return '—';
  }

  return Number(value).toFixed(digits);
}

function formatLatency(value?: number | null) {
  if (value == null || Number.isNaN(value)) {
    return '—';
  }

  return `${Math.round(value)} ms`;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightExcerpt(text: string, query: string | null) {
  const terms = (query ?? '')
    .toLowerCase()
    .split(/\s+/)
    .filter((term) => term.length >= 4)
    .slice(0, 6);

  if (!terms.length) {
    return text;
  }

  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'ig');
  const parts = text.split(pattern);

  return parts.map((part, index) =>
    terms.includes(part.toLowerCase()) ? (
      <mark key={`${part}-${index}`} className="rounded bg-sky-500/20 px-1 text-sky-100">
        {part}
      </mark>
    ) : (
      <span key={`${part}-${index}`}>{part}</span>
    ),
  );
}

function enrichSources(message: ChatMessage): Array<SourceReference & { debugResult?: RetrievalResultDebug }> {
  const debugByKey = new Map<string, RetrievalResultDebug>();

  for (const result of message.debug?.retrieval?.results ?? []) {
    debugByKey.set(result.chunk_id ?? `${result.source ?? 'unknown'}:${result.chunk_index ?? 'na'}`, result);
  }

  return (message.sources ?? []).map((source) => {
    const debugResult = debugByKey.get(getSourceKey(source));
    return {
      ...source,
      section_title: source.section_title ?? debugResult?.section_title ?? null,
      section_path: source.section_path ?? debugResult?.section_path ?? null,
      score: source.score ?? debugResult?.score ?? null,
      score_type: source.score_type ?? debugResult?.score_type ?? null,
      dense_score: source.dense_score ?? debugResult?.dense_score ?? null,
      lexical_score: source.lexical_score ?? debugResult?.lexical_score ?? null,
      rerank_score: source.rerank_score ?? debugResult?.rerank_score ?? null,
      retrieval_method: source.retrieval_method ?? debugResult?.retrieval_method ?? null,
      retrieval_methods: source.retrieval_methods ?? debugResult?.retrieval_methods,
      metadata: source.metadata ?? debugResult?.metadata,
      debugResult,
    };
  });
}

function MetricCard({ label, value, help }: { label: string; value: string; help: string }) {
  return (
    <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">{label}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-gray-400">{help}</div>
    </div>
  );
}

function SourceCard({
  source,
  debugMode,
  query,
}: {
  source: SourceReference & { debugResult?: RetrievalResultDebug };
  debugMode: boolean;
  query: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const excerpt = source.preview ?? source.text ?? source.debugResult?.preview ?? 'No excerpt available.';

  return (
    <article className="rounded-2xl border border-border bg-white/[0.03] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">
            <FileText className="h-3.5 w-3.5" />
            Source
          </div>
          <div className="mt-2 truncate text-sm font-medium text-white">{source.source ?? source.document ?? 'Document'}</div>
          <div className="mt-1 text-xs text-gray-400">
            Page {source.page ?? 'n/a'} | Chunk {source.chunk_index ?? 'n/a'}
          </div>
          {source.section_path ? (
            <div className="mt-2 text-xs text-sky-200">{source.section_path}</div>
          ) : source.section_title ? (
            <div className="mt-2 text-xs text-sky-200">{source.section_title}</div>
          ) : null}
        </div>

        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-gray-300 transition hover:border-sky-500/40 hover:text-white"
        >
          {expanded ? 'Hide context' : 'See full context'}
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      <div className="mt-4 rounded-2xl bg-black/20 p-3 text-sm leading-7 text-gray-200">{highlightExcerpt(excerpt, query)}</div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        {source.retrieval_methods?.map((method) => (
          <span key={method} className="rounded-full border border-border bg-white/[0.03] px-2.5 py-1 text-gray-300">
            {method}
          </span>
        ))}
        {source.score != null ? (
          <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2.5 py-1 text-sky-100">
            {source.score_type ?? 'score'} {formatNumber(source.score)}
          </span>
        ) : null}
        {debugMode && source.rerank_score != null ? (
          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-emerald-100">
            rerank {formatNumber(source.rerank_score)}
          </span>
        ) : null}
      </div>

      {expanded ? (
        <div className="mt-4 grid gap-2 text-xs text-gray-300">
          {source.chunk_id ? (
            <div className="rounded-xl border border-border bg-black/20 px-3 py-2">
              <span className="text-gray-500">chunk_id</span>: {source.chunk_id}
            </div>
          ) : null}
          {source.document_id ? (
            <div className="rounded-xl border border-border bg-black/20 px-3 py-2">
              <span className="text-gray-500">document_id</span>: {source.document_id}
            </div>
          ) : null}
          {debugMode && source.metadata ? (
            <pre className="overflow-x-auto rounded-2xl border border-border bg-black/30 p-3 text-[11px] text-gray-300">
              {JSON.stringify(source.metadata, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function DebugPanel({ debug }: { debug: ChatDebugInfo }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <MetricCard label="Trace" value={debug.trace_id.slice(0, 8)} help="Request-scoped trace identifier for correlating logs." />
        <MetricCard label="Total Latency" value={formatLatency(debug.total_latency_ms)} help="End-to-end request time reported by the backend." />
        <MetricCard
          label="Prompt Tokens"
          value={String(debug.prompt?.prompt_token_estimate ?? '—')}
          help="Estimated prompt token count after context assembly."
        />
        <MetricCard
          label="Output Tokens"
          value={String(debug.generation?.output_token_estimate ?? '—')}
          help="Estimated number of generated output tokens."
        />
      </div>

      <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-white">
          <SearchCheck className="h-4 w-4 text-sky-300" />
          Retrieval
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <MetricCard label="Latency" value={formatLatency(debug.retrieval?.latency_ms)} help="Dense/hybrid retrieval time." />
          <MetricCard
            label="Chunks"
            value={`${debug.retrieval?.used_count ?? 0}/${debug.retrieval?.retrieved_count ?? 0}`}
            help="Chunks used in prompt vs retrieved candidates."
          />
        </div>
      </div>

      {debug.reranking?.enabled ? (
        <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-white">
            <Layers3 className="h-4 w-4 text-emerald-300" />
            Reranking
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <MetricCard label="Latency" value={formatLatency(debug.reranking.latency_ms)} help="Post-retrieval scoring time." />
            <MetricCard
              label="Candidates"
              value={`${debug.reranking.kept_count}/${debug.reranking.candidate_count}`}
              help="Candidates kept after reranking."
            />
          </div>
        </div>
      ) : null}

      <div className="rounded-2xl border border-border bg-white/[0.03] p-4">
        <div className="flex items-center gap-2 text-sm font-medium text-white">
          <Gauge className="h-4 w-4 text-violet-300" />
          Retrieved Chunks
        </div>
        <div className="mt-4 space-y-3">
          {(debug.retrieval?.results ?? []).map((result, index) => (
            <div key={result.chunk_id ?? `${result.source}-${index}`} className="rounded-2xl border border-border bg-black/20 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-medium text-white">
                  {result.source ?? 'Document'} · chunk {result.chunk_index ?? 'n/a'}
                </div>
                <div className="text-xs text-gray-400">rank {result.rank ?? index + 1}</div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-300">
                {result.dense_score != null ? (
                  <span className="rounded-full border border-border px-2 py-1">dense {formatNumber(result.dense_score)}</span>
                ) : null}
                {result.lexical_score != null ? (
                  <span className="rounded-full border border-border px-2 py-1">lexical {formatNumber(result.lexical_score)}</span>
                ) : null}
                {result.rerank_score != null ? (
                  <span className="rounded-full border border-border px-2 py-1">rerank {formatNumber(result.rerank_score)}</span>
                ) : null}
                {result.score != null ? (
                  <span className="rounded-full border border-border px-2 py-1">
                    {result.score_type ?? 'score'} {formatNumber(result.score)}
                  </span>
                ) : null}
              </div>
              <div className="mt-3 text-sm leading-7 text-gray-300">{result.preview}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function InsightPanel({
  panelTab,
  onTabChange,
  debugMode,
  onToggleDebugMode,
  message,
  question,
  className,
}: {
  panelTab: PanelTab;
  onTabChange: (tab: PanelTab) => void;
  debugMode: boolean;
  onToggleDebugMode: (enabled: boolean) => void;
  message: ChatMessage | null;
  question: string | null;
  className?: string;
}) {
  const enrichedSources = useMemo(() => (message ? enrichSources(message) : []), [message]);

  const debug = message?.debug ?? null;

  return (
    <aside className={clsx('flex min-h-0 w-full flex-col border-l border-border bg-panel/95 backdrop-blur', className)}>
      <div className="border-b border-border px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Evidence Workspace</div>
            <div className="mt-2 text-sm text-gray-200">Inspect sources, retrieval metrics, and debug details for the selected answer.</div>
          </div>

          <button
            type="button"
            onClick={() => onToggleDebugMode(!debugMode)}
            className={clsx(
              'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition',
              debugMode ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.03] text-gray-300',
            )}
          >
            <Bug className="h-3.5 w-3.5" />
            Debug {debugMode ? 'On' : 'Off'}
          </button>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => onTabChange('sources')}
            className={clsx(
              'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition',
              panelTab === 'sources' ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.03] text-gray-300',
            )}
          >
            <BookOpenText className="h-3.5 w-3.5" />
            Sources
          </button>
          <button
            type="button"
            onClick={() => onTabChange('debug')}
            className={clsx(
              'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition',
              panelTab === 'debug' ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.03] text-gray-300',
            )}
          >
            <Bug className="h-3.5 w-3.5" />
            Debug
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {!message ? (
          <div className="rounded-3xl border border-border bg-white/[0.03] p-6 text-sm text-gray-300">
            Select or generate an assistant message to inspect its retrieval evidence and pipeline metadata.
          </div>
        ) : panelTab === 'sources' ? (
          <div className="space-y-4">
            <div className="rounded-3xl border border-border bg-white/[0.03] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-gray-400">Selected answer</div>
              <div className="mt-3 text-sm leading-7 text-gray-200">{message.content || 'Streaming...'}</div>
              {question ? (
                <div className="mt-4 rounded-2xl border border-border bg-black/20 p-3 text-xs text-gray-300">
                  <span className="text-gray-500">Question</span>: {question}
                </div>
              ) : null}
            </div>

            {enrichedSources.length ? (
              enrichedSources.map((source, index) => (
                <SourceCard key={getSourceKey(source) ?? `${source.source}-${index}`} source={source} debugMode={debugMode} query={question} />
              ))
            ) : (
              <div className="rounded-3xl border border-border bg-white/[0.03] p-6 text-sm text-gray-300">
                This answer does not have source metadata attached.
              </div>
            )}
          </div>
        ) : debug ? (
          <DebugPanel debug={debug} />
        ) : (
          <div className="rounded-3xl border border-border bg-white/[0.03] p-6 text-sm text-gray-300">
            Debug data is only available for answers generated in the current session.
          </div>
        )}
      </div>
    </aside>
  );
}
