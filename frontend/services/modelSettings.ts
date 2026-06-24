import { apiFetch } from '@/services/api';
import type { ModelSettingsState, UpdateModelSettingsInput } from '@/types/models';

export async function fetchModelSettings(): Promise<ModelSettingsState> {
  return apiFetch<ModelSettingsState>('/models/settings');
}

export async function updateModelSettings(
  input: UpdateModelSettingsInput,
): Promise<ModelSettingsState> {
  return apiFetch<ModelSettingsState>('/models/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_model: input.chat_model,
      require_installed: input.require_installed ?? true,
    }),
  });
}

export async function resetModelSettings(): Promise<ModelSettingsState> {
  return apiFetch<ModelSettingsState>('/models/settings/reset', {
    method: 'POST',
  });
}
