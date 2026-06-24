'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchHardwareTelemetry } from '@/services/hardwareTelemetry';
import type { HardwareTelemetrySnapshot } from '@/types/hardware';

const DEFAULT_POLL_MS = 5000;

type UseHardwareTelemetryOptions = {
  enablePolling?: boolean;
};

export function useHardwareTelemetry(options: UseHardwareTelemetryOptions = {}) {
  const { enablePolling = false } = options;
  const [telemetry, setTelemetry] = useState<HardwareTelemetrySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshInFlight = useRef(false);
  const pollMsRef = useRef(DEFAULT_POLL_MS);

  const applyTelemetry = useCallback((next: HardwareTelemetrySnapshot) => {
    setTelemetry(next);
    if (next.poll_interval_seconds > 0) {
      pollMsRef.current = Math.round(next.poll_interval_seconds * 1000);
    }
  }, []);

  const refreshSilent = useCallback(async () => {
    if (refreshInFlight.current) {
      return;
    }

    refreshInFlight.current = true;
    try {
      const next = await fetchHardwareTelemetry();
      applyTelemetry(next);
      setError(null);
    } catch (refreshError) {
      setTelemetry(null);
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to load hardware telemetry');
    } finally {
      refreshInFlight.current = false;
    }
  }, [applyTelemetry]);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) {
      return;
    }

    refreshInFlight.current = true;
    setLoading(true);
    setError(null);

    try {
      const next = await fetchHardwareTelemetry();
      applyTelemetry(next);
    } catch (refreshError) {
      setTelemetry(null);
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to load hardware telemetry');
    } finally {
      setLoading(false);
      refreshInFlight.current = false;
    }
  }, [applyTelemetry]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!enablePolling) {
      return;
    }

    let intervalId: number | null = null;

    function startPolling() {
      if (intervalId !== null) {
        return;
      }
      intervalId = window.setInterval(() => {
        if (document.visibilityState === 'hidden') {
          return;
        }
        void refreshSilent();
      }, pollMsRef.current);
    }

    function stopPolling() {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
    }

    function handleVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        stopPolling();
      } else {
        void refreshSilent();
        startPolling();
      }
    }

    if (document.visibilityState !== 'hidden') {
      startPolling();
    }

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      stopPolling();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enablePolling, refreshSilent]);

  return {
    telemetry,
    loading,
    error,
    refresh,
    refreshSilent,
  };
}
