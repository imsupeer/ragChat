'use client';

import { useMemo, useState, type RefObject } from 'react';
import clsx from 'clsx';
import {
  Activity,
  BookOpenText,
  Braces,
  ChevronDown,
  ChevronUp,
  FileText,
  Gauge,
  Layers3,
  SearchCheck,
  Sparkles,
  X,
} from 'lucide-react';
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

function getAnswerModeDisplay(mode?: string | null) {
  if (mode === 'hybrid_assistant') {
    return {
      label: 'Hybrid Assistant',
      summary: 'Answer mode: Hybrid assistant — documents first, general knowledge allowed when needed.',
      description: 'Prioritizes documents, may use general model knowledge when document context is missing or incomplete.',
      raw: mode,
    };
  }

  return {
    label: 'Strict RAG',
    summary: 'Answer mode: Strict RAG — document context only.',
    description: 'Answers only from retrieved document context.',
    raw: mode ?? 'strict_rag',
  };
}

function getQueryRewritingDisplay(queryRewriting?: ChatDebugInfo['query_rewriting']) {
  if (!queryRewriting) {
    return {
      badge: null as string | null,
      line: 'Query rewriting data unavailable for this answer.',
      showSection: false,
      defaultOpen: false,
    };
  }

  if (!queryRewriting.enabled) {
    return {
      badge: null,
      line: null,
      showSection: false,
      defaultOpen: false,
    };
  }

  if (queryRewriting.used) {
    return {
      badge: 'Rewritten for retrieval',
      line: 'Query rewritten for retrieval.',
      showSection: true,
      defaultOpen: true,
    };
  }

  return {
    badge: null,
    line: 'Query rewriting enabled, but this question was already standalone.',
    showSection: true,
    defaultOpen: false,
  };
}

function getScoreHelp(scoreType?: string | null) {
  switch (scoreType) {
    case 'distance':
      return 'Distance: lower is usually a closer match.';
    case 'bm25':
      return 'Keyword match: higher is usually stronger.';
    case 'rrf':
      return 'Combined rank: higher is usually stronger.';
    case 'rerank':
      return 'Rerank score: higher means more relevant after reordering.';
    default:
      return scoreType ? `${scoreType} score from the retrieval pipeline.` : null;
  }
}

function formatScoreLabel(scoreType?: string | null) {
  switch (scoreType) {
    case 'distance':
      return 'distance';
    case 'bm25':
      return 'BM25';
    case 'rrf':
      return 'RRF fused';
    case 'rerank':
      return 'rerank';
    default:
      return scoreType ?? 'score';
  }
}

function formatScoreBadge(score: number | null | undefined, scoreType?: string | null) {
  if (score == null || Number.isNaN(score)) {
    return null;
  }

  return `${formatScoreLabel(scoreType)} ${formatNumber(score)}`;
}

function answerSnippet(content: string, maxLength = 140) {
  const singleLine = content.replace(/\s+/g, ' ').trim();
  if (singleLine.length <= maxLength) {
    return singleLine;
  }

  return `${singleLine.slice(0, maxLength).trim()}…`;
}

function enrichSources(message: ChatMessage): Array<SourceReference & { debugResult?: RetrievalResultDebug }> {
  const debugByKey = new Map<string, RetrievalResultDebug>();

  for (const result of message.debug?.prompt?.used_chunks ?? []) {
    debugByKey.set(result.chunk_id ?? `${result.source ?? 'unknown'}:${result.chunk_index ?? 'na'}`, result);
  }

  for (const result of message.debug?.reranking?.results ?? []) {
    const key = result.chunk_id ?? `${result.source ?? 'unknown'}:${result.chunk_index ?? 'na'}`;
    if (!debugByKey.has(key)) {
      debugByKey.set(key, result);
    }
  }

  for (const result of message.debug?.retrieval?.results ?? []) {
    const key = result.chunk_id ?? `${result.source ?? 'unknown'}:${result.chunk_index ?? 'na'}`;
    if (!debugByKey.has(key)) {
      debugByKey.set(key, result);
    }
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
      <div className="app-label">{label}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-gray-400">{help}</div>
    </div>
  );
}

function ScoreBadge({ score, scoreType }: { score: number; scoreType?: string | null }) {
  const help = getScoreHelp(scoreType);
  return (
    <span
      title={help ?? undefined}
      className="app-badge"
    >
      {formatScoreBadge(score, scoreType)}
    </span>
  );
}

function ChunkDebugCard({ result, index }: { result: RetrievalResultDebug; index: number }) {
  const primaryScoreType = result.score_type ?? result.retrieval_score_type ?? (result.rerank_score != null ? 'rerank' : null);
  const primaryScore = result.score ?? result.rerank_score ?? result.fused_score ?? result.dense_score ?? result.lexical_score;
  const scoreHelp = getScoreHelp(primaryScoreType);

  return (
    <div className="rounded-2xl border border-border bg-black/20 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-white">
          {result.source ?? 'Document'} · chunk {result.chunk_index ?? 'n/a'}
        </div>
        <div className="text-xs text-gray-400">rank {result.rank ?? index + 1}</div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {result.dense_score != null ? <ScoreBadge score={result.dense_score} scoreType="distance" /> : null}
        {result.lexical_score != null ? <ScoreBadge score={result.lexical_score} scoreType="bm25" /> : null}
        {result.fused_score != null ? <ScoreBadge score={result.fused_score} scoreType="rrf" /> : null}
        {result.rerank_score != null ? <ScoreBadge score={result.rerank_score} scoreType="rerank" /> : null}
        {result.score != null ? (
          <ScoreBadge score={result.score} scoreType={result.score_type ?? result.retrieval_score_type} />
        ) : null}
      </div>
      {scoreHelp && primaryScore != null ? <div className="mt-2 text-[11px] text-gray-500">{scoreHelp}</div> : null}
      <div className="mt-3 text-sm leading-7 text-gray-300">{result.preview}</div>
    </div>
  );
}

function CollapsibleSection({
  title,
  icon,
  defaultOpen,
  testId,
  subtitle,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  defaultOpen: boolean;
  testId: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <details
      open={defaultOpen}
      data-testid={testId}
      className="group rounded-2xl border border-border bg-white/[0.03] p-4"
    >
      <summary className="focus-ring flex min-h-10 cursor-pointer list-none items-start justify-between gap-3 rounded-lg px-1 py-1 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium text-white">
            {icon}
            {title}
          </div>
          {subtitle ? <div className="mt-1 text-xs text-gray-400">{subtitle}</div> : null}
        </div>
        <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-gray-400 transition group-open:rotate-180" />
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

function ReviewerSummary({
  message,
  question,
  debug,
}: {
  message: ChatMessage;
  question: string | null;
  debug: ChatDebugInfo | null;
}) {
  const answerMode = getAnswerModeDisplay(debug?.prompt?.answer_mode);
  const queryRewriting = getQueryRewritingDisplay(debug?.query_rewriting);
  const sourceCount = message.sources?.length ?? 0;
  const usedChunkCount = debug?.prompt?.used_chunk_count ?? debug?.retrieval?.used_count ?? 0;
  const rerankingEnabled = debug?.reranking?.enabled ?? false;

  return (
    <div
      data-testid="insight-reviewer-summary"
      className="rounded-2xl border border-violet-500/20 bg-violet-500/5 p-4"
    >
      <div className="app-label flex items-center gap-2 text-violet-300/90">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        Reviewer summary
      </div>

      <div className="mt-3 space-y-2 text-sm text-gray-200">
        <p>{answerMode.summary}</p>
        {queryRewriting.line ? <p>{queryRewriting.line}</p> : null}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {queryRewriting.badge ? (
          <span className="app-badge border-amber-500/30 bg-amber-500/10 text-amber-100">{queryRewriting.badge}</span>
        ) : null}
        <span className="app-badge">{sourceCount} source{sourceCount === 1 ? '' : 's'}</span>
        <span className="app-badge">{usedChunkCount} chunk{usedChunkCount === 1 ? '' : 's'} in prompt</span>
        {rerankingEnabled ? (
          <span className="app-badge border-emerald-500/30 bg-emerald-500/10 text-emerald-100">Reranking applied</span>
        ) : null}
        {debug?.total_latency_ms != null ? (
          <span className="app-badge">{formatLatency(debug.total_latency_ms)} total</span>
        ) : null}
      </div>

      {question ? (
        <div className="mt-3 rounded-xl border border-border bg-black/20 p-3 text-xs text-gray-300">
          <span className="text-gray-500">Question</span>: {question}
        </div>
      ) : null}

      {debug ? (
        <p className="mt-3 text-xs text-gray-500">
          Pipeline details are saved for this answer{message.created_at ? ' and persist after reload.' : '.'}
        </p>
      ) : (
        <p className="mt-3 text-xs text-gray-500">Pipeline details are not available for this answer yet.</p>
      )}

      <p className="mt-2 text-xs text-gray-500">
        Answer mode setting: <span className="text-gray-400">{answerMode.raw}</span>
      </p>
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
  const scoreType = source.score_type ?? source.debugResult?.retrieval_score_type;
  const scoreHelp = source.score != null ? getScoreHelp(scoreType) : null;

  return (
    <article data-testid="source-card" className="rounded-2xl border border-border bg-white/[0.03] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 app-label">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
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
          aria-expanded={expanded}
          aria-label={expanded ? 'Hide full source context' : 'See full source context'}
          className="focus-ring inline-flex min-h-10 shrink-0 items-center gap-1 rounded-full border border-border px-3 py-2 text-xs text-gray-300 transition hover:border-sky-500/40 hover:text-white xl:min-h-0 xl:px-2.5 xl:py-1"
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
          <span
            title={scoreHelp ?? undefined}
            className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2.5 py-1 text-sky-100"
          >
            {formatScoreBadge(source.score, scoreType)}
          </span>
        ) : null}
        {debugMode && source.rerank_score != null ? (
          <span
            title={getScoreHelp('rerank') ?? undefined}
            className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-emerald-100"
          >
            {formatScoreBadge(source.rerank_score, 'rerank')}
          </span>
        ) : null}
      </div>
      {scoreHelp ? <div className="mt-2 text-[11px] text-gray-500">{scoreHelp}</div> : null}

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

function DebugPanel({ debug, tabsPrefix }: { debug: ChatDebugInfo; tabsPrefix: string }) {
  const usedChunks =
    debug.prompt?.used_chunks ??
    (debug.reranking?.enabled ? debug.reranking.results : debug.retrieval?.results?.slice(0, debug.retrieval?.used_count ?? 0)) ??
    [];
  const retrievedCandidates = debug.retrieval?.results ?? [];
  const rerankedCandidates = debug.reranking?.enabled ? debug.reranking.results ?? [] : [];
  const queryRewriting = getQueryRewritingDisplay(debug.query_rewriting);
  const answerMode = getAnswerModeDisplay(debug.prompt?.answer_mode);

  return (
    <div
      id={`${tabsPrefix}-tabpanel-debug`}
      role="tabpanel"
      aria-labelledby={`${tabsPrefix}-tab-debug-button`}
      className="space-y-4"
      data-testid="insight-debug-content"
    >
      {queryRewriting.showSection && debug.query_rewriting ? (
        <CollapsibleSection
          title="Query Rewriting"
          icon={<SearchCheck className="h-4 w-4 text-amber-300" />}
          defaultOpen={queryRewriting.defaultOpen}
          testId="debug-query-rewriting"
          subtitle={queryRewriting.line ?? undefined}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <MetricCard
              label="Used"
              value={debug.query_rewriting.used ? 'Yes' : 'No'}
              help="Whether chat history changed the retrieval query."
            />
            <MetricCard
              label="Latency"
              value={formatLatency(debug.query_rewriting.latency_ms)}
              help="Time spent rewriting the retrieval query."
            />
            <MetricCard
              label="History Turns"
              value={String(debug.query_rewriting.history_turns_used)}
              help="Recent user/assistant turns considered for rewriting."
            />
          </div>
          <div className="mt-4 space-y-3 text-sm text-gray-200">
            <div className="rounded-2xl border border-border bg-black/20 p-3">
              <div className="app-label">Original question</div>
              <div className="mt-2 leading-7">{debug.query_rewriting.original_question}</div>
            </div>
            <div className="rounded-2xl border border-border bg-black/20 p-3">
              <div className="app-label">Retrieval query</div>
              <div className="mt-2 leading-7">{debug.query_rewriting.rewritten_query}</div>
            </div>
          </div>
        </CollapsibleSection>
      ) : null}

      <CollapsibleSection
        title="Used in Prompt"
        icon={<Gauge className="h-4 w-4 text-violet-300" />}
        defaultOpen
        testId="debug-used-in-prompt"
        subtitle="Chunks that were included in the final answer prompt."
      >
        <div className="space-y-3">
          {usedChunks.length ? (
            usedChunks.map((result, index) => (
              <ChunkDebugCard key={result.chunk_id ?? `${result.source}-${index}`} result={result} index={index} />
            ))
          ) : (
            <div className="text-sm text-gray-400">No prompt chunk metadata available.</div>
          )}
        </div>
      </CollapsibleSection>

      {debug.reranking?.enabled ? (
        <>
          <CollapsibleSection
            title="Reranking Summary"
            icon={<Layers3 className="h-4 w-4 text-emerald-300" />}
            defaultOpen={false}
            testId="debug-reranking-summary"
            subtitle={`${debug.reranking.kept_count}/${debug.reranking.candidate_count} candidates kept · ${formatLatency(debug.reranking.latency_ms)}`}
          >
            <div className="grid gap-3 md:grid-cols-2">
              <MetricCard label="Latency" value={formatLatency(debug.reranking.latency_ms)} help="Post-retrieval scoring time." />
              <MetricCard
                label="Candidates"
                value={`${debug.reranking.kept_count}/${debug.reranking.candidate_count}`}
                help="Candidates kept after reranking."
              />
            </div>
          </CollapsibleSection>

          <CollapsibleSection
            title="Reranked Candidates"
            icon={<Layers3 className="h-4 w-4 text-emerald-300" />}
            defaultOpen={false}
            testId="debug-reranked-candidates"
            subtitle={`${rerankedCandidates.length} candidates after reranking`}
          >
            <div className="space-y-3">
              {rerankedCandidates.map((result, index) => (
                <ChunkDebugCard key={result.chunk_id ?? `${result.source}-rerank-${index}`} result={result} index={index} />
              ))}
            </div>
          </CollapsibleSection>
        </>
      ) : null}

      <CollapsibleSection
        title="Retrieved Candidates"
        icon={<SearchCheck className="h-4 w-4 text-sky-300" />}
        defaultOpen={false}
        testId="debug-retrieved-candidates"
        subtitle={`${retrievedCandidates.length} candidates before prompt trimming · ${formatLatency(debug.retrieval?.latency_ms)} retrieval`}
      >
        <p className="mb-3 text-xs text-gray-500">
          All chunks returned by retrieval. Only a subset may appear in the final prompt.
        </p>
        <div className="space-y-3">
          {retrievedCandidates.length ? (
            retrievedCandidates.map((result, index) => (
              <ChunkDebugCard key={result.chunk_id ?? `${result.source}-candidate-${index}`} result={result} index={index} />
            ))
          ) : (
            <div className="text-sm text-gray-400">No retrieval candidate metadata available.</div>
          )}
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Technical Metrics"
        icon={<Activity className="h-4 w-4 text-gray-300" />}
        defaultOpen={false}
        testId="debug-technical-metrics"
        subtitle="Trace, tokens, latency, and raw configuration"
      >
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
          <MetricCard label="Answer Mode" value={answerMode.label} help={answerMode.description} />
          <MetricCard
            label="Retrieval Chunks"
            value={`${debug.retrieval?.used_count ?? 0}/${debug.retrieval?.candidate_count ?? debug.retrieval?.retrieved_count ?? 0}`}
            help="Chunks used in prompt vs retrieved candidates."
          />
        </div>
        <div className="mt-3 text-xs text-gray-500">
          Raw answer mode value: <span className="text-gray-400">{answerMode.raw}</span>
        </div>
      </CollapsibleSection>
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
  panelId,
  panelLabel = 'Evidence and debug panel',
  onClose,
  closeButtonRef,
}: {
  panelTab: PanelTab;
  onTabChange: (tab: PanelTab) => void;
  debugMode: boolean;
  onToggleDebugMode: (enabled: boolean) => void;
  message: ChatMessage | null;
  question: string | null;
  className?: string;
  panelId?: string;
  panelLabel?: string;
  onClose?: () => void;
  closeButtonRef?: RefObject<HTMLButtonElement>;
}) {
  const enrichedSources = useMemo(() => (message ? enrichSources(message) : []), [message]);

  const debug = message?.debug ?? null;
  const sourceCount = message?.sources?.length ?? 0;
  const usedChunkCount = debug?.prompt?.used_chunk_count ?? debug?.retrieval?.used_count ?? 0;
  const tabsPrefix = panelId ?? 'insight-panel';

  return (
    <aside
      id={panelId}
      aria-label={panelLabel}
      data-testid="insight-panel"
      className={clsx('flex min-h-0 w-full flex-col border-l border-border bg-panel/95 backdrop-blur', className)}
    >
      {onClose ? (
        <div className="flex items-center justify-between border-b border-border px-4 py-3 xl:hidden">
          <div>
            <div className="text-sm font-semibold text-white">Evidence &amp; debug</div>
            <div className="text-xs text-gray-400">Sources and pipeline details for the selected answer</div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            data-testid="evidence-panel-close"
            aria-label="Close evidence panel"
            onClick={onClose}
            className="focus-ring inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border bg-white/[0.04] text-gray-300 transition hover:bg-white/[0.08] hover:text-white"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <div className="border-b border-border px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="app-label">Evidence panel</div>
            <div className="mt-2 text-sm text-gray-200 xl:block">
              Sources, scores, and pipeline details for the selected answer.
            </div>
          </div>

          <button
            type="button"
            onClick={() => onToggleDebugMode(!debugMode)}
            aria-pressed={debugMode}
            aria-label={debugMode ? 'Hide technical metadata' : 'Show technical metadata'}
            className={clsx(
              'focus-ring inline-flex min-h-10 shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-xs transition xl:min-h-0 xl:px-3 xl:py-1.5',
              debugMode ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.03] text-gray-300',
            )}
          >
            <Braces className="h-3.5 w-3.5" aria-hidden="true" />
            {debugMode ? 'Hide metadata' : 'Show technical metadata'}
          </button>
        </div>

        <div className="mt-4 flex gap-2" role="tablist" aria-label="Evidence panel views">
          <button
            type="button"
            role="tab"
            id={`${tabsPrefix}-tab-sources-button`}
            aria-selected={panelTab === 'sources'}
            aria-controls={`${tabsPrefix}-tabpanel-sources`}
            data-testid="insight-tab-sources"
            onClick={() => onTabChange('sources')}
            className={clsx(
              'focus-ring inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-full border px-4 py-2.5 text-sm transition xl:min-h-0 xl:flex-none xl:px-3 xl:py-1.5 xl:text-xs',
              panelTab === 'sources' ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.03] text-gray-300',
            )}
          >
            <BookOpenText className="h-4 w-4 shrink-0 xl:h-3.5 xl:w-3.5" aria-hidden="true" />
            Sources
          </button>
          <button
            type="button"
            role="tab"
            id={`${tabsPrefix}-tab-debug-button`}
            aria-selected={panelTab === 'debug'}
            aria-controls={`${tabsPrefix}-tabpanel-debug`}
            data-testid="insight-tab-debug"
            onClick={() => onTabChange('debug')}
            className={clsx(
              'focus-ring inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-full border px-4 py-2.5 text-sm transition xl:min-h-0 xl:flex-none xl:px-3 xl:py-1.5 xl:text-xs',
              panelTab === 'debug' ? 'border-sky-500/40 bg-sky-500/10 text-sky-100' : 'border-border bg-white/[0.03] text-gray-300',
            )}
          >
            <Activity className="h-4 w-4 shrink-0 xl:h-3.5 xl:w-3.5" aria-hidden="true" />
            Pipeline Debug
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {!message ? (
          <div className="rounded-3xl border border-border bg-white/[0.03] p-6 text-sm text-gray-300">
            Select or generate an assistant message to inspect its retrieval evidence and pipeline metadata.
          </div>
        ) : (
          <div className="space-y-4">
            <ReviewerSummary message={message} question={question} debug={debug} />

            {panelTab === 'sources' ? (
              <div
                id={`${tabsPrefix}-tabpanel-sources`}
                role="tabpanel"
                aria-labelledby={`${tabsPrefix}-tab-sources-button`}
                className="space-y-4"
                data-testid="insight-sources-content"
              >
                <div className="rounded-2xl border border-border bg-white/[0.03] p-4" data-testid="sources-summary">
                  <div className="app-label">Evidence summary</div>
                  <div className="mt-2 text-sm text-gray-200">
                    {sourceCount} source{sourceCount === 1 ? '' : 's'} · {usedChunkCount} chunk{usedChunkCount === 1 ? '' : 's'} used in
                    prompt
                  </div>
                  {message.content ? (
                    <div className="mt-3 rounded-xl border border-border bg-black/20 p-3 text-xs leading-6 text-gray-300">
                      <span className="text-gray-500">Answer snippet</span>: {answerSnippet(message.content)}
                    </div>
                  ) : null}
                  <p className="mt-3 text-xs leading-5 text-gray-500">
                    Sources below are the chunks cited or used by this answer. Open Pipeline Debug for retrieval and reranking details.
                  </p>
                </div>

                {enrichedSources.length ? (
                  enrichedSources.map((source, index) => (
                    <SourceCard
                      key={getSourceKey(source) ?? `${source.source}-${index}`}
                      source={source}
                      debugMode={debugMode}
                      query={question}
                    />
                  ))
                ) : (
                  <div className="rounded-3xl border border-border bg-white/[0.03] p-6 text-sm text-gray-300">
                    This answer does not have source metadata attached.
                  </div>
                )}
              </div>
            ) : debug ? (
              <DebugPanel debug={debug} tabsPrefix={tabsPrefix} />
            ) : (
              <div
                id={`${tabsPrefix}-tabpanel-debug`}
                role="tabpanel"
                aria-labelledby={`${tabsPrefix}-tab-debug-button`}
                className="rounded-3xl border border-border bg-white/[0.03] p-6 text-sm text-gray-300"
              >
                Debug metadata is not available for this message.
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
