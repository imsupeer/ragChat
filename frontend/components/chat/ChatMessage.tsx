'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, ChevronDown, ChevronRight, Copy, RotateCcw } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import clsx from 'clsx';
import type { ChatMessage as ChatMessageType } from '@/types/chat';
import { StreamingMessage } from '@/components/chat/StreamingMessage';

function SourceReferences({ sources = [] }: { sources?: ChatMessageType['sources'] }) {
  const [expanded, setExpanded] = useState(false);

  if (!sources?.length) return null;

  return (
    <div className="mt-4 rounded-xl border border-border bg-black/20 p-3">
      <button type="button" onClick={() => setExpanded((prev) => !prev)} className="flex w-full items-center justify-between gap-3 text-left">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">Sources</div>
          <div className="mt-1 text-xs text-gray-500">
            {sources.length} reference{sources.length > 1 ? 's' : ''}
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span>{expanded ? 'Hide' : 'Show'}</span>
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </div>
      </button>

      {expanded ? (
        <div className="mt-3 space-y-2">
          {sources.map((source, index) => (
            <div key={`${source.source ?? source.document}-${index}`} className="rounded-lg bg-white/5 p-2 text-xs text-gray-300">
              <div className="font-medium text-white">{source.source ?? source.document ?? 'Document'}</div>
              <div className="text-gray-400">
                Page: {source.page ?? 'n/a'} • Chunk: {source.chunk_index ?? 'n/a'}
              </div>
              <div className="mt-1 whitespace-pre-wrap">{source.preview ?? source.text}</div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ChatMessage({ message, onRegenerate }: { message: ChatMessageType; onRegenerate?: () => void | Promise<void> }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const bubbleClass = useMemo(
    () =>
      clsx(
        'max-w-[90%] rounded-2xl px-4 py-3 shadow-sm md:max-w-[80%]',
        isUser ? 'ml-auto bg-user text-white' : 'mr-auto border border-border bg-assistant text-white',
      ),
    [isUser],
  );

  async function handleCopy() {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <div className="group">
      <div className={bubbleClass}>
        {message.content ? (
          <div className="markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code(props) {
                  const { children, className, ...rest } = props;
                  const match = /language-(\w+)/.exec(className || '');
                  const code = String(children).replace(/\n$/, '');

                  if (match) {
                    return (
                      <SyntaxHighlighter {...rest} language={match[1]} style={oneDark} PreTag="div">
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

        {!isUser && message.isStreaming && !message.content ? <div className="mt-2 text-xs text-gray-400">Thinking...</div> : null}

        {!isUser ? <SourceReferences sources={message.sources} /> : null}
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
