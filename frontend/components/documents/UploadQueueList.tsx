'use client';

import type { UploadQueueItem } from '@/types/document';

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

export function UploadQueueList({ items }: { items: UploadQueueItem[] }) {
  if (!items.length) return null;

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.localId} className="rounded-2xl border border-border bg-white/[0.03] p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-white">{item.filename}</div>
              <div className="mt-1 text-[11px] text-gray-500">
                {item.source === 'recovered' ? 'Recovered after refresh' : 'Local upload'}
                {item.retryCount > 0 ? ` | retry ${item.retryCount}` : ''}
              </div>
            </div>
            <div className={`rounded-full border px-2.5 py-1 text-[11px] ${getStatusTone(item.status)}`}>{item.status}</div>
          </div>

          <div className="mb-1 mt-3 text-[11px] text-gray-400">Upload {item.uploadProgress}%</div>
          <div className="h-2 w-full rounded-full bg-black/30">
            <div className="h-2 rounded-full bg-sky-500 transition-all" style={{ width: `${item.uploadProgress}%` }} />
          </div>

          <div className="mb-1 mt-3 text-[11px] text-gray-400">Indexing {item.indexProgress}%</div>
          <div className="h-2 w-full rounded-full bg-black/30">
            <div className="h-2 rounded-full bg-emerald-500 transition-all" style={{ width: `${item.indexProgress}%` }} />
          </div>

          {item.jobId ? <div className="mt-2 text-[11px] text-gray-500">job {item.jobId}</div> : null}
          {item.error ? <div className="mt-2 text-[11px] text-red-300">{item.error}</div> : null}
        </div>
      ))}
    </div>
  );
}
