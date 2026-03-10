export function Loader({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-gray-400">
      <span className="h-2 w-2 animate-pulse rounded-full bg-sky-400" />
      <span>{label}</span>
    </div>
  );
}
