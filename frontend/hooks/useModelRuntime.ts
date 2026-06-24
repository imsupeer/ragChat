'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchModelRuntime, preloadActiveModel, unloadActiveModel } from '@/services/modelRuntime';
import type { ModelRuntimeStatus } from '@/types/models';

const POLL_MS = 30_000;
const DELAYED_REFRESH_MS = 1500;

type UseModelRuntimeOptions = {
  enablePolling?: boolean;
};

export function useModelRuntime(options: UseModelRuntimeOptions = {}) {
  const { enablePolling = false } = options;
  const [runtime, setRuntime] = useState<ModelRuntimeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<'preload' | 'unload' | null>(null);
  const refreshInFlight = useRef(false);
  const lastReachable = useRef<boolean | null>(null);
  const delayedRefreshTimer = useRef<number | null>(null);

  const applyRuntime = useCallback((next: ModelRuntimeStatus) => {
    setRuntime(next);
    lastReachable.current = next.ollama.reachable;
  }, []);

  const refreshSilent = useCallback(async () => {
    if (refreshInFlight.current) {
      return;
    }

    refreshInFlight.current = true;
    try {
      const next = await fetchModelRuntime();
      applyRuntime(next);
      setError(null);
    } catch (refreshError) {
      setRuntime(null);
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to load model runtime');
    } finally {
      refreshInFlight.current = false;
    }
  }, [applyRuntime]);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) {
      return;
    }

    refreshInFlight.current = true;
    setLoading(true);
    setError(null);

    try {
      const next = await fetchModelRuntime();
      applyRuntime(next);
    } catch (refreshError) {
      setRuntime(null);
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to load model runtime');
    } finally {
      setLoading(false);
      refreshInFlight.current = false;
    }
  }, [applyRuntime]);

  const scheduleDelayedRefresh = useCallback(() => {
    if (delayedRefreshTimer.current !== null) {
      window.clearTimeout(delayedRefreshTimer.current);
    }
    delayedRefreshTimer.current = window.setTimeout(() => {
      delayedRefreshTimer.current = null;
      void refreshSilent();
    }, DELAYED_REFRESH_MS);
  }, [refreshSilent]);

  const refreshAfterAction = useCallback(
    async (actionResult?: { runtime?: ModelRuntimeStatus }) => {
      if (actionResult?.runtime) {
        applyRuntime(actionResult.runtime);
      }
      await refreshSilent();
      scheduleDelayedRefresh();
    },
    [applyRuntime, refreshSilent, scheduleDelayedRefresh],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!enablePolling) {
      return;
    }

    const interval = window.setInterval(() => {
      void refreshSilent();
    }, POLL_MS);

    return () => window.clearInterval(interval);
  }, [enablePolling, refreshSilent]);

  useEffect(() => {
    return () => {
      if (delayedRefreshTimer.current !== null) {
        window.clearTimeout(delayedRefreshTimer.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!runtime) {
      return;
    }

    const reachable = runtime.ollama.reachable;
    if (lastReachable.current !== null && lastReachable.current !== reachable) {
      void refreshSilent();
    }
    lastReachable.current = reachable;
  }, [runtime, refreshSilent]);

  const preload = useCallback(async () => {
    setActionLoading('preload');
    setActionMessage(null);
    setError(null);

    try {
      const result = await preloadActiveModel();
      setActionMessage(result.message);
      await refreshAfterAction(result.runtime ? { runtime: result.runtime } : undefined);
      return result;
    } catch (preloadError) {
      const message = preloadError instanceof Error ? preloadError.message : 'Failed to preload model';
      setError(message);
      throw preloadError;
    } finally {
      setActionLoading(null);
    }
  }, [refreshAfterAction]);

  const unload = useCallback(async () => {
    setActionLoading('unload');
    setActionMessage(null);
    setError(null);

    try {
      const result = await unloadActiveModel();
      setActionMessage(result.message);
      await refreshAfterAction(result.runtime ? { runtime: result.runtime } : undefined);
      return result;
    } catch (unloadError) {
      const message = unloadError instanceof Error ? unloadError.message : 'Failed to unload model';
      setError(message);
      throw unloadError;
    } finally {
      setActionLoading(null);
    }
  }, [refreshAfterAction]);

  return {
    runtime,
    loading,
    error,
    actionMessage,
    actionLoading,
    refresh,
    preload,
    unload,
    clearActionMessage: () => setActionMessage(null),
  };
}
