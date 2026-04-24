'use client';

import clsx from 'clsx';
import type { ChatDebugInfo } from '@/types/chat';
import type { PipelineStage } from '@/store/useAppStore';

function formatLatency(value?: number) {
  if (value == null) {
    return '—';
  }

  return `${Math.round(value)} ms`;
}

type StepStatus = 'pending' | 'active' | 'complete';

function getSummary(stage: PipelineStage, debug: ChatDebugInfo | null, isStreaming: boolean) {
  if (stage === 'retrieving' && isStreaming) {
    return 'Searching for the most relevant chunks...';
  }

  if (stage === 'reranking' && isStreaming) {
    return 'Re-ranking results to improve answer quality...';
  }

  if (stage === 'generating' && isStreaming) {
    return 'Generating response grounded in retrieved context...';
  }

  if (stage === 'error') {
    return 'The response stream failed before completion.';
  }

  if (debug?.generation && stage === 'complete') {
    return 'Response completed with retrieval and generation diagnostics available.';
  }

  return 'Ask a question to see retrieval, reranking, and generation stages.';
}

function StagePill({ label, status, meta }: { label: string; status: StepStatus; meta: string }) {
  return (
    <div
      className={clsx(
        'rounded-2xl border px-3 py-2 transition',
        status === 'complete' && 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
        status === 'active' && 'border-sky-500/40 bg-sky-500/10 text-sky-100 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]',
        status === 'pending' && 'border-border bg-white/[0.03] text-gray-400',
      )}
    >
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em]">{label}</div>
      <div className="mt-1 text-sm">{meta}</div>
    </div>
  );
}

export function ChatStageIndicator({ isStreaming, stage, debug }: { isStreaming: boolean; stage: PipelineStage; debug: ChatDebugInfo | null }) {
  const retrievalStatus: StepStatus =
    stage === 'retrieving' ? 'active' : debug?.retrieval || ['reranking', 'generating', 'complete', 'error'].includes(stage) ? 'complete' : 'pending';

  const rerankingEnabled = !!debug?.reranking?.enabled;
  const rerankingStatus: StepStatus =
    stage === 'reranking'
      ? 'active'
      : rerankingEnabled && (debug?.reranking || ['generating', 'complete', 'error'].includes(stage))
        ? 'complete'
        : 'pending';

  const generationStatus: StepStatus = stage === 'generating' ? 'active' : debug?.generation || stage === 'complete' ? 'complete' : 'pending';

  return (
    <section className="border-b border-border bg-gradient-to-b from-white/[0.04] to-transparent px-4 py-3">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Pipeline</div>
            <div className="mt-1 text-sm text-gray-200">{getSummary(stage, debug, isStreaming)}</div>
          </div>

          <div className="grid gap-2 md:grid-cols-3">
            <StagePill
              label="Retrieve"
              status={retrievalStatus}
              meta={
                debug?.retrieval
                  ? `${debug.retrieval.retrieved_count} found | ${formatLatency(debug.retrieval.latency_ms)}`
                  : isStreaming && stage === 'retrieving'
                    ? 'Working...'
                    : 'Waiting'
              }
            />
            <StagePill
              label="Rerank"
              status={rerankingStatus}
              meta={
                rerankingEnabled && debug?.reranking
                  ? `${debug.reranking.kept_count}/${debug.reranking.candidate_count} kept | ${formatLatency(debug.reranking.latency_ms)}`
                  : rerankingEnabled
                    ? 'Enabled'
                    : 'Optional'
              }
            />
            <StagePill
              label="Generate"
              status={generationStatus}
              meta={
                debug?.generation
                  ? `${debug.generation.output_token_estimate} tokens | ${formatLatency(debug.generation.latency_ms)}`
                  : isStreaming && stage === 'generating'
                    ? 'Streaming...'
                    : 'Waiting'
              }
            />
          </div>
        </div>
      </div>
    </section>
  );
}
