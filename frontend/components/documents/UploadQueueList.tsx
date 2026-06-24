'use client';

import { useEffect, useState } from 'react';
import type { UploadQueueItem } from '@/types/document';
import { formatUploadQueueEta } from '@/utils/uploadEta';

function getStatusTone(status: UploadQueueItem['status']) {
  switch (status) {
    case 'completed':
      return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100';
    case 'failed':
      return 'border-red-500/20 bg-red-500/10 text-red-200';
    case 'processing':
    case 'uploading':
      return 'border-sky-500/20 bg-sky-500/10 text-sky-100';
    default:
      return 'border-border bg-white/[0.03] text-gray-300';
  }
}

function formatStatusLabel(status: UploadQueueItem['status']) {
  switch (status) {
    case 'completed':
      return 'Indexed';
    case 'processing':
      return 'Indexing';
    case 'uploading':
      return 'Uploading';
    case 'failed':
      return 'Failed';
    case 'queued':
      return 'Queued';
    default:
      return status;
  }
}

export function UploadQueueList({
  items,
  onRetry,
}: {
  items: UploadQueueItem[];
  onRetry?: (localId: string) => void;
}) {
  const [expandedDetails, setExpandedDetails] = useState<Record<string, boolean>>({});
  const [, setEtaTick] = useState(0);

  useEffect(() => {
    const hasActiveUpload = items.some((item) => item.status === 'uploading' || item.status === 'processing');
    if (!hasActiveUpload) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setEtaTick((tick) => tick + 1);
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [items]);

  if (!items.length) return null;

  return (
    <div className="space-y-2">
      {items.map((item) => {
        const showUploadEta = item.status === 'uploading';
        const showIndexEta =
          item.status === 'processing' ||
          item.indexProgress > 0 ||
          (item.uploadProgress >= 100 && item.status !== 'queued' && item.status !== 'failed' && item.status !== 'completed');
        const uploadEta = showUploadEta
          ? formatUploadQueueEta(
              'upload',
              item.uploadProgress,
              item.uploadStartedAt,
              item.lastUploadProgress,
              item.lastUploadProgressAt,
            )
          : null;
        const indexEta = showIndexEta
          ? formatUploadQueueEta(
              'index',
              item.indexProgress,
              item.indexingStartedAt,
              item.lastIndexProgress,
              item.lastIndexProgressAt,
              item.fileSize,
            )
          : null;
        const showLargeFileHint =
          showIndexEta &&
          item.indexProgress < 10 &&
          (item.fileSize ?? 0) >= 250_000 &&
          indexEta?.includes('large file');

        return (
          <div
            key={item.localId}
            data-testid="upload-queue-item"
            data-status={item.status}
            className="rounded-2xl border border-border bg-white/[0.03] p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-white">{item.filename}</div>
                <div className="mt-1 text-[11px] text-gray-500">
                  {item.source === 'recovered' ? 'Recovered after refresh' : 'Local upload'}
                  {item.retryCount > 0 ? ` | retry ${item.retryCount}` : ''}
                </div>
              </div>
              <div
                className={`app-badge text-[11px] ${getStatusTone(item.status)}`}
                data-testid={item.status === 'completed' ? 'upload-queue-completed' : undefined}
              >
                {formatStatusLabel(item.status)}
              </div>
            </div>

            {item.status !== 'completed' ? (
              <>
                <div className="mb-1 mt-3 flex items-center justify-between gap-2 text-[11px] text-gray-400">
                  <span>Upload {item.uploadProgress}%</span>
                  {uploadEta ? <span className="shrink-0 tabular-nums text-gray-500">{uploadEta}</span> : null}
                </div>
                <div className="h-2 w-full rounded-full bg-black/30">
                  <div className="h-2 rounded-full bg-sky-500 transition-all" style={{ width: `${item.uploadProgress}%` }} />
                </div>

                <div className="mb-1 mt-3 flex items-center justify-between gap-2 text-[11px] text-gray-400">
                  <span>Indexing {item.indexProgress}%</span>
                  {indexEta ? <span className="shrink-0 tabular-nums text-gray-500">{indexEta}</span> : null}
                </div>
                <div className="h-2 w-full rounded-full bg-black/30">
                  <div className="h-2 rounded-full bg-emerald-500 transition-all" style={{ width: `${item.indexProgress}%` }} />
                </div>
                {showLargeFileHint ? (
                  <p className="mt-2 text-[11px] text-gray-500">Large files can take several minutes to index.</p>
                ) : null}
              </>
            ) : (
              <div className="mt-3 text-sm text-emerald-200">Indexed successfully. Clearing from queue shortly.</div>
            )}

            {item.error ? (
              <div role="alert" className="mt-2 text-[11px] text-red-300">
                {item.error}
              </div>
            ) : null}

            {item.jobId ? (
              <div className="mt-2">
                <button
                  type="button"
                  id={`upload-details-toggle-${item.localId}`}
                  aria-expanded={Boolean(expandedDetails[item.localId])}
                  aria-controls={`upload-details-${item.localId}`}
                  onClick={() =>
                    setExpandedDetails((current) => ({
                      ...current,
                      [item.localId]: !current[item.localId],
                    }))
                  }
                  className="focus-ring rounded text-[11px] text-gray-500 transition hover:text-gray-300"
                >
                  {expandedDetails[item.localId] ? 'Hide technical details' : 'Show technical details'}
                </button>
                {expandedDetails[item.localId] ? (
                  <div
                    id={`upload-details-${item.localId}`}
                    className="mt-2 rounded-xl border border-border bg-black/20 px-3 py-2 text-[11px] text-gray-400"
                  >
                    Job ID: {item.jobId}
                  </div>
                ) : null}
              </div>
            ) : null}

            {item.status === 'failed' && item.recoverable && item.jobId && onRetry ? (
              <button
                type="button"
                data-testid="upload-queue-retry"
                onClick={() => onRetry(item.localId)}
                aria-label={`Retry indexing for ${item.filename}`}
                className="focus-ring mt-3 rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-100 transition hover:bg-sky-500/20"
              >
                Retry indexing
              </button>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
