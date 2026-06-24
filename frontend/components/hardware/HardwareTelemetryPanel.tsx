'use client';

import { useMemo, useState } from 'react';
import { Activity, ChevronDown, ChevronRight, Loader2, RotateCcw } from 'lucide-react';
import { ErrorMessage } from '@/components/ui/ErrorMessage';
import { Skeleton } from '@/components/ui/Skeleton';
import type { HardwareTelemetrySnapshot } from '@/types/hardware';
import type { ModelRuntimeStatus } from '@/types/models';

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null || Number.isNaN(bytes)) {
    return '—';
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const precision = value >= 100 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function usageBarClass(percent?: number) {
  if (percent === undefined || percent === null) {
    return 'bg-white/20';
  }
  if (percent >= 85) {
    return 'bg-rose-400';
  }
  if (percent >= 70) {
    return 'bg-amber-400';
  }
  return 'bg-sky-400';
}

function UsageBar({
  label,
  percent,
  detail,
  testId,
}: {
  label: string;
  percent?: number;
  detail?: string;
  testId: string;
}) {
  const safePercent = percent ?? 0;
  const width = Math.min(100, Math.max(0, safePercent));

  return (
    <div data-testid={testId}>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        <span className="text-gray-300">{label}</span>
        <span className="text-gray-400" aria-label={`${label} usage`}>
          {percent !== undefined ? `${percent.toFixed(1)}%` : '—'}
          {detail ? <span className="ml-1 text-gray-500">({detail})</span> : null}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full border border-border bg-black/30"
        role="progressbar"
        aria-label={`${label} usage`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent !== undefined ? Math.round(safePercent) : undefined}
      >
        <div className={`h-full rounded-full transition-all duration-300 ${usageBarClass(percent)}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function gpuStatusMessage(snapshot: HardwareTelemetrySnapshot): string | null {
  const gpu = snapshot.gpu;
  if (gpu.status === 'ok') {
    return null;
  }
  if (gpu.message) {
    return gpu.message;
  }
  if (gpu.status === 'disabled') {
    return 'GPU telemetry is disabled by configuration.';
  }
  return 'GPU telemetry unavailable. CPU/RAM metrics are still available.';
}

export function HardwareTelemetryPanel({
  telemetry,
  loading,
  error,
  modelRuntime,
  onRefresh,
}: {
  telemetry: HardwareTelemetrySnapshot | null;
  loading: boolean;
  error: string | null;
  modelRuntime: ModelRuntimeStatus | null;
  onRefresh: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const primaryGpu = telemetry?.gpu.devices?.[0];
  const gpuMessage = telemetry ? gpuStatusMessage(telemetry) : null;
  const modelLoaded = modelRuntime?.active_model.loaded === true;
  const showVramHint = Boolean(primaryGpu && modelLoaded);

  const memoryDetail = useMemo(() => {
    if (!telemetry?.memory.used_bytes && telemetry?.memory.used_bytes !== 0) {
      return undefined;
    }
    return `${formatBytes(telemetry.memory.used_bytes)} / ${formatBytes(telemetry.memory.total_bytes)}`;
  }, [telemetry]);

  const vramDetail = useMemo(() => {
    if (!primaryGpu?.memory_used_bytes && primaryGpu?.memory_used_bytes !== 0) {
      return undefined;
    }
    return `${formatBytes(primaryGpu.memory_used_bytes)} / ${formatBytes(primaryGpu.memory_total_bytes)}`;
  }, [primaryGpu]);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="rounded-[24px] border border-border bg-black/15 p-4" data-testid="hardware-telemetry-panel">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-sky-300" aria-hidden="true" />
          <div className="text-sm font-semibold text-white">Local hardware</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={loading || refreshing}
            aria-label="Refresh hardware telemetry"
            data-testid="hardware-telemetry-refresh"
            className="focus-ring inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.03] px-3 py-1 text-xs text-gray-300 transition hover:text-white disabled:opacity-50"
          >
            {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse hardware telemetry' : 'Expand hardware telemetry'}
            className="focus-ring inline-flex items-center gap-1 rounded-full border border-border bg-white/[0.03] px-3 py-1 text-xs text-gray-300 transition hover:text-white"
          >
            {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            {expanded ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>

      <p className="mb-3 text-[11px] leading-5 text-gray-500">
        Useful when testing model preload/unload and local inference load.
        {showVramHint ? ' Active model is loaded — watch VRAM while chatting or preloading.' : null}
      </p>

      {error ? <ErrorMessage message={error} /> : null}

      {!expanded ? null : loading && !telemetry ? (
        <div className="space-y-2" data-testid="hardware-telemetry-loading">
          <Skeleton className="h-10 w-full rounded-xl" />
          <Skeleton className="h-10 w-full rounded-xl" />
        </div>
      ) : telemetry?.status === 'disabled' ? (
        <p className="text-xs text-gray-400" data-testid="hardware-telemetry-disabled">
          Hardware telemetry is disabled on the backend.
        </p>
      ) : telemetry ? (
        <div className="space-y-3" data-testid="hardware-telemetry-metrics">
          <UsageBar
            label="CPU"
            percent={telemetry.cpu.usage_percent}
            detail={
              telemetry.cpu.logical_count
                ? `${telemetry.cpu.physical_count ?? '?'} physical / ${telemetry.cpu.logical_count} logical cores`
                : undefined
            }
            testId="hardware-telemetry-cpu"
          />

          <UsageBar label="RAM" percent={telemetry.memory.usage_percent} detail={memoryDetail} testId="hardware-telemetry-ram" />

          {telemetry.gpu.status === 'ok' && primaryGpu ? (
            <div className="rounded-xl border border-border bg-white/[0.03] p-3" data-testid="hardware-telemetry-gpu">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-xs font-medium text-gray-200">{primaryGpu.name}</div>
                <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-gray-400">
                  {telemetry.gpu.provider ?? primaryGpu.vendor}
                </span>
              </div>
              <div className="space-y-2">
                <UsageBar label="GPU" percent={primaryGpu.usage_percent} testId="hardware-telemetry-gpu-usage" />
                <UsageBar label="VRAM" percent={primaryGpu.memory_usage_percent} detail={vramDetail} testId="hardware-telemetry-vram" />
              </div>
            </div>
          ) : (
            <div
              className="rounded-xl border border-border bg-white/[0.02] p-3 text-[11px] leading-5 text-gray-400"
              data-testid="hardware-telemetry-gpu-fallback"
              role="status"
            >
              {gpuMessage}
            </div>
          )}

          {telemetry.checked_at ? (
            <p className="text-[10px] text-gray-600" data-testid="hardware-telemetry-checked-at">
              Updated {new Date(telemetry.checked_at).toLocaleTimeString()}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
