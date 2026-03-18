'use client';

import type { UploadQueueItem } from '@/types/document';

export function UploadQueueList({ items }: { items: UploadQueueItem[] }) {
  if (!items.length) return null;

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.localId} className="rounded-xl border border-border bg-white/5 p-3">
          <div className="mb-2 truncate text-sm font-medium">{item.file.name}</div>

          <div className="mb-1 text-[11px] text-gray-400">Upload: {item.uploadProgress}%</div>
          <div className="h-2 w-full rounded-full bg-black/30">
            <div className="h-2 rounded-full bg-sky-500 transition-all" style={{ width: `${item.uploadProgress}%` }} />
          </div>

          <div className="mb-1 mt-3 text-[11px] text-gray-400">Indexing: {item.indexProgress}%</div>
          <div className="h-2 w-full rounded-full bg-black/30">
            <div className="h-2 rounded-full bg-emerald-500 transition-all" style={{ width: `${item.indexProgress}%` }} />
          </div>

          <div className="mt-2 text-[11px] text-gray-400">Status: {item.status}</div>

          {item.error ? <div className="mt-2 text-[11px] text-red-300">{item.error}</div> : null}
        </div>
      ))}
    </div>
  );
}
