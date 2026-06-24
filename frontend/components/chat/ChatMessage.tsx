'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, ChevronDown, ChevronUp, Copy, RotateCcw, SearchCheck, Sparkles } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import clsx from 'clsx';
import type { ChatMessage as ChatMessageType } from '@/types/chat';
import { StreamingMessage } from '@/components/chat/StreamingMessage';
import { ErrorMessage } from '@/components/ui/ErrorMessage';

const PREVIEW_SOURCE_LIMIT = 2;

function SourceReferences({ sources = [], onInspect }: { sources?: ChatMessageType['sources']; onInspect?: () => void }) {
  const [expanded, setExpanded] = useState(false);

  if (!sources?.length) return null;

  const previewSources = sources.slice(0, PREVIEW_SOURCE_LIMIT);
  const remainingCount = sources.length - previewSources.length;

  return (
    <div className="mt-4 rounded-2xl border border-border bg-black/20 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="app-label">Sources in this answer</div>
          <div className="mt-1 text-xs text-gray-500">
            {sources.length} source{sources.length > 1 ? 's' : ''} attached
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onInspect ? (
            <button
              type="button"
              onClick={onInspect}
              aria-label="Inspect answer evidence"
              className="focus-ring rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-xs text-sky-100 transition hover:border-sky-500/40"
            >
              Inspect
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            aria-expanded={expanded}
            aria-label={expanded ? 'Hide source preview' : 'Preview sources'}
            className="focus-ring inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs text-gray-300 transition hover:text-white"
          >
            {expanded ? 'Hide' : 'Preview'}
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {expanded ? (
        <div className="mt-3 space-y-2">
          {previewSources.map((source, index) => (
            <div
              key={`${source.chunk_id ?? source.source ?? source.document}-${index}`}
              className="rounded-xl border border-border bg-white/[0.03] p-3 text-xs text-gray-300"
            >
              <div className="font-medium text-white">{source.source ?? source.document ?? 'Document'}</div>
              <div className="mt-1 text-gray-400">{source.section_path ?? source.section_title ?? 'Unstructured excerpt'}</div>
              <div className="mt-1 text-gray-500">
                Page {source.page ?? 'n/a'} | Chunk {source.chunk_index ?? 'n/a'}
              </div>
              {source.score != null ? (
                <div className="mt-2 app-badge-accent text-[11px]">
                  {source.score_type ?? 'score'} {Number(source.score).toFixed(3)}
                </div>
              ) : null}
              <div className="mt-2 whitespace-pre-wrap leading-6">{source.preview ?? source.text}</div>
            </div>
          ))}

          {remainingCount > 0 && onInspect ? (
            <button
              type="button"
              data-testid="source-preview-more"
              onClick={onInspect}
              aria-label={`View ${remainingCount} more source${remainingCount === 1 ? '' : 's'} in evidence panel`}
              className="focus-ring w-full rounded-xl border border-dashed border-sky-500/30 bg-sky-500/5 px-3 py-2 text-left text-xs text-sky-100 transition hover:border-sky-500/50 hover:bg-sky-500/10"
            >
              +{remainingCount} more source{remainingCount === 1 ? '' : 's'} in the Evidence panel
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function ChatMessage({
  message,
  onRegenerate,
  onInspect,
  selected = false,
}: {
  message: ChatMessageType;
  onRegenerate?: () => void | Promise<void>;
  onInspect?: () => void;
  selected?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const showAssistantActions = !isUser && Boolean(message.content || message.sources?.length || message.debug);

  const bubbleClass = useMemo(
    () =>
      clsx(
        'max-w-[94%] rounded-[28px] px-5 py-4 shadow-[0_20px_45px_rgba(0,0,0,0.18)] transition md:max-w-[82%]',
        isUser
          ? 'ml-auto border border-sky-500/30 bg-[linear-gradient(135deg,rgba(43,108,230,0.95),rgba(59,130,246,0.72))] text-white'
          : 'mr-auto border bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] text-white',
        !isUser && selected
          ? 'border-l-[3px] border-l-sky-400 border-sky-500/50 bg-[linear-gradient(180deg,rgba(56,189,248,0.1),rgba(255,255,255,0.02))] shadow-[0_0_0_1px_rgba(56,189,248,0.28)]'
          : 'border-border',
      ),
    [isUser, selected],
  );

  async function handleCopy() {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div
      className="group"
      data-testid={isUser ? 'chat-user-message' : 'chat-assistant-message'}
      data-message-id={message.id}
      data-is-streaming={!isUser && message.isStreaming ? 'true' : 'false'}
      aria-live={!isUser && message.isStreaming ? 'polite' : undefined}
    >
      <div className={bubbleClass}>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className={clsx('app-label', isUser && 'text-white/60')}>{isUser ? 'You' : 'Assistant'}</div>

          {!isUser ? (
            <div className="flex flex-wrap items-center justify-end gap-2">
              {selected ? (
                <span className="app-badge-accent" data-testid="message-selected-chip">
                  Selected for evidence
                </span>
              ) : null}
              {message.sources?.length ? (
                <span className="app-badge">
                  <Sparkles className="h-3 w-3" aria-hidden="true" />
                  {message.sources.length} source{message.sources.length === 1 ? '' : 's'}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>

        {message.content ? (
          <div className="markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code(props) {
                  const { children, className, node: _node, ref: _ref, ...rest } = props;
                  const match = /language-(\w+)/.exec(className || '');
                  const code = String(children).replace(/\n$/, '');

                  if (match) {
                    return (
                      <SyntaxHighlighter language={match[1]} style={oneDark} PreTag="div">
                        {code}
                      </SyntaxHighlighter>
                    );
                  }

                  return (
                    <code className={className} {...rest}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        ) : message.isStreaming ? (
          <StreamingMessage />
        ) : null}

        {!isUser && message.isStreaming && !message.content ? <div className="mt-3 text-xs text-gray-400">Preparing response...</div> : null}

        {!isUser ? <SourceReferences sources={message.sources} onInspect={onInspect} /> : null}

        {!isUser && message.error && message.errorMessage ? (
          <div className="mt-4">
            <ErrorMessage message={message.errorMessage} />
          </div>
        ) : null}
      </div>

      {showAssistantActions || isUser ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 px-1">
          <button
            type="button"
            data-testid="message-action-copy"
            aria-label={copied ? 'Copied to clipboard' : isUser ? 'Copy message' : 'Copy assistant answer'}
            onClick={handleCopy}
            className="focus-ring inline-flex min-h-10 items-center gap-1 rounded-lg border border-transparent px-3 py-2 text-xs text-gray-400 transition hover:border-border hover:bg-white/5 hover:text-white xl:min-h-0 xl:px-2 xl:py-1"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? 'Copied' : 'Copy'}
          </button>

          {!isUser && onInspect ? (
            <button
              type="button"
              data-testid="message-action-inspect"
              aria-label="Inspect answer evidence"
              onClick={onInspect}
              className="focus-ring inline-flex min-h-10 items-center gap-1 rounded-lg border border-sky-500/20 bg-sky-500/10 px-3 py-2 text-xs text-sky-100 transition hover:border-sky-500/40 xl:min-h-0 xl:px-2 xl:py-1"
            >
              <SearchCheck className="h-3.5 w-3.5" aria-hidden="true" />
              Inspect
            </button>
          ) : null}

          {!isUser && onRegenerate ? (
            <button
              type="button"
              data-testid="message-action-regenerate"
              aria-label="Regenerate answer"
              onClick={onRegenerate}
              className="focus-ring inline-flex min-h-10 items-center gap-1 rounded-lg border border-transparent px-3 py-2 text-xs text-gray-400 transition hover:border-border hover:bg-white/5 hover:text-white xl:min-h-0 xl:px-2 xl:py-1"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Regenerate
            </button>
          ) : null}

          <span aria-live="polite" className="sr-only">
            {copied ? 'Copied to clipboard' : ''}
          </span>
        </div>
      ) : null}
    </div>
  );
}
