export function StreamingMessage() {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-gray-400">
      <span className="text-xs uppercase tracking-[0.2em] text-gray-500">Thinking</span>
      <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.2s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.1s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400" />
    </div>
  );
}
