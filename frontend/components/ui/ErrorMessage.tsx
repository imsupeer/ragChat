'use client';

import { AlertCircle } from 'lucide-react';

export function ErrorMessage({ message, id }: { message: string; id?: string }) {
  return (
    <div
      id={id}
      role="alert"
      aria-live="assertive"
      className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
