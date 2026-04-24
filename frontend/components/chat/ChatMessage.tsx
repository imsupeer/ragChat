'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Braces, Check, ChevronDown, ChevronUp, Copy, RotateCcw, Sparkles } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import clsx from 'clsx';
import type { ChatMessage as ChatMessageType } from '@/types/chat';
import { StreamingMessage } from '@/components/chat/StreamingMessage';

function SourceReferences({ sources = [], onInspect }: { sources?: ChatMessageType['sources']; onInspect?: () => void }) {
  const [expanded, setExpanded] = useState(false);

  if (!sources?.length) return null;

  return (
    <div className="mt-4 rounded-2xl border border-border bg-black/20 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-gray-400">Evidence</div>
          <div className="mt-1 text-xs text-gray-500">
            {sources.length} source{sources.length > 1 ? 's' : ''} attached
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onInspect ? (
            <button
              type="button"
              onClick={onInspect}
              className="rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-xs text-sky-100 transition hover:border-sky-500/40"
            >
              Inspect
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs text-gray-300 transition hover:text-white"
          >
            {expanded ? 'Hide' : 'Preview'}
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {expanded ? (
        <div className="mt-3 space-y-2">
          {sources.slice(0, 2).map((source, index) => (
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
                <div className="mt-2 inline-flex rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-1 text-[11px] text-sky-100">
                  {source.score_type ?? 'score'} {Number(source.score).toFixed(3)}
                </div>
              ) : null}
              <div className="mt-2 whitespace-pre-wrap leading-6">{source.preview ?? source.text}</div>
            </div>
          ))}
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

  const bubbleClass = useMemo(
    () =>
      clsx(
        'max-w-[94%] rounded-[28px] px-5 py-4 shadow-[0_20px_45px_rgba(0,0,0,0.18)] transition md:max-w-[82%]',
        isUser
          ? 'ml-auto border border-sky-500/30 bg-[linear-gradient(135deg,rgba(43,108,230,0.95),rgba(59,130,246,0.72))] text-white'
          : 'mr-auto border bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] text-white',
        !isUser && selected ? 'border-sky-500/40 shadow-[0_0_0_1px_rgba(56,189,248,0.16)]' : 'border-border',
      ),
    [isUser, selected],
  );

  async function handleCopy() {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="group" aria-live={!isUser && message.isStreaming ? 'polite' : undefined}>
      <div className={bubbleClass}>
        <div className="mb-3 flex items-center justify-between gap-3 text-[11px] font-semibold uppercase tracking-[0.22em]">
          <div className={clsx(isUser ? 'text-white/70' : 'text-gray-400')}>{isUser ? 'You' : 'Assistant'}</div>

          {!isUser ? (
            <div className="flex items-center gap-2">
              {message.debug ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-border bg-black/20 px-2 py-1 text-[10px] text-gray-300">
                  <Braces className="h-3 w-3" />
                  debug
                </span>
              ) : null}
              {message.sources?.length ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-border bg-black/20 px-2 py-1 text-[10px] text-gray-300">
                  <Sparkles className="h-3 w-3" />
                  {message.sources.length} sources
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
      </div>

      <div className="mt-2 flex items-center gap-2 px-1 opacity-100 md:opacity-0 md:group-hover:opacity-100">
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:bg-white/5 hover:text-white"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>

        {!isUser && onInspect ? (
          <button
            type="button"
            onClick={onInspect}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:bg-white/5 hover:text-white"
          >
            <Braces className="h-3.5 w-3.5" />
            Inspect
          </button>
        ) : null}

        {!isUser && onRegenerate ? (
          <button
            type="button"
            onClick={onRegenerate}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:bg-white/5 hover:text-white"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Regenerate
          </button>
        ) : null}
      </div>
    </div>
  );
}
