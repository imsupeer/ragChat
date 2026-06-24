'use client';

import { useCallback, useEffect, useState } from 'react';
import { fetchModelSettings, resetModelSettings, updateModelSettings } from '@/services/modelSettings';
import type { ModelSettingsState } from '@/types/models';

export function useModelSettings() {
  const [settings, setSettings] = useState<ModelSettingsState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const next = await fetchModelSettings();
      setSettings(next);
    } catch (refreshError) {
      setSettings(null);
      setError(refreshError instanceof Error ? refreshError.message : 'Failed to load model settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applyChatModel = useCallback(
    async (chatModel: string, requireInstalled = true) => {
      setActionMessage(null);
      setError(null);

      try {
        const next = await updateModelSettings({
          chat_model: chatModel,
          require_installed: requireInstalled,
        });
        setSettings(next);
        if (next.warning) {
          setActionMessage(next.warning);
        } else {
          setActionMessage(`Chat model set to ${next.chat_model}.`);
        }
        return next;
      } catch (applyError) {
        const message = applyError instanceof Error ? applyError.message : 'Failed to update chat model';
        setError(message);
        throw applyError;
      }
    },
    [],
  );

  const resetChatModel = useCallback(async () => {
    setActionMessage(null);
    setError(null);

    try {
      const next = await resetModelSettings();
      setSettings(next);
      setActionMessage(`Reset to default chat model (${next.chat_model}).`);
      return next;
    } catch (resetError) {
      const message = resetError instanceof Error ? resetError.message : 'Failed to reset chat model';
      setError(message);
      throw resetError;
    }
  }, []);

  return {
    settings,
    loading,
    error,
    actionMessage,
    refresh,
    applyChatModel,
    resetChatModel,
    clearActionMessage: () => setActionMessage(null),
  };
}
