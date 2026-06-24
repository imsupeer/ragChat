import { apiFetch } from '@/services/api';
import type { ModelRuntimeActionResponse, ModelRuntimeStatus } from '@/types/models';

export async function fetchModelRuntime(): Promise<ModelRuntimeStatus> {
  return apiFetch<ModelRuntimeStatus>('/models/runtime');
}

export async function preloadActiveModel(): Promise<ModelRuntimeActionResponse> {
  return apiFetch<ModelRuntimeActionResponse>('/models/runtime/preload', {
    method: 'POST',
  });
}

export async function unloadActiveModel(): Promise<ModelRuntimeActionResponse> {
  return apiFetch<ModelRuntimeActionResponse>('/models/runtime/unload', {
    method: 'POST',
  });
}
