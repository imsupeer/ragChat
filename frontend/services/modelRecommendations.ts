import { apiFetch } from '@/services/api';
import type { HardwareProfileInput, ModelRecommendationResponse } from '@/types/models';

export async function fetchModelRecommendations(
  profile: HardwareProfileInput,
): Promise<ModelRecommendationResponse> {
  return apiFetch<ModelRecommendationResponse>('/models/recommendations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
}
