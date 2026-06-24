export function estimateRemainingSeconds(
  progress: number,
  startedAt?: number,
  lastProgress?: number,
  lastProgressAt?: number,
): number | null {
  if (progress >= 100) {
    return 0;
  }

  if (!startedAt || progress <= 0) {
    return null;
  }

  const now = Date.now();
  const elapsedSeconds = (now - startedAt) / 1000;

  if (elapsedSeconds < 4) {
    return null;
  }

  if (
    lastProgressAt != null &&
    lastProgress != null &&
    lastProgress < progress &&
    now > lastProgressAt
  ) {
    const recentSeconds = (now - lastProgressAt) / 1000;
    const recentDelta = progress - lastProgress;

    if (recentSeconds >= 2 && recentDelta > 0) {
      const rate = recentDelta / recentSeconds;
      return Math.max(1, Math.ceil((100 - progress) / rate));
    }
  }

  if (progress < 2) {
    return null;
  }

  const overallRate = progress / elapsedSeconds;
  if (overallRate <= 0) {
    return null;
  }

  return Math.max(1, Math.ceil((100 - progress) / overallRate));
}

export function estimateIndexingFallbackSeconds(fileSizeBytes?: number, indexProgress?: number): number | null {
  if (!fileSizeBytes || fileSizeBytes < 250_000 || (indexProgress ?? 0) > 8) {
    return null;
  }

  const megabytes = fileSizeBytes / (1024 * 1024);
  return Math.max(60, Math.ceil(megabytes * 120));
}

export function formatEta(seconds: number | null): string {
  if (seconds == null) {
    return 'Estimating…';
  }

  if (seconds <= 0) {
    return 'Almost done';
  }

  if (seconds < 60) {
    return `~${seconds}s left`;
  }

  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) {
    return `~${minutes} min left`;
  }

  const hours = Math.floor(minutes / 60);
  const remainderMinutes = minutes % 60;
  return remainderMinutes > 0 ? `~${hours}h ${remainderMinutes}m left` : `~${hours}h left`;
}

export function formatUploadQueueEta(
  phase: 'upload' | 'index',
  progress: number,
  startedAt?: number,
  lastProgress?: number,
  lastProgressAt?: number,
  fileSizeBytes?: number,
): string {
  const fromRate = estimateRemainingSeconds(progress, startedAt, lastProgress, lastProgressAt);

  if (fromRate != null) {
    return formatEta(fromRate);
  }

  if (phase === 'index') {
    const fallback = estimateIndexingFallbackSeconds(fileSizeBytes, progress);
    if (fallback != null) {
      return `${formatEta(fallback)} (large file)`;
    }
  }

  return 'Estimating…';
}
