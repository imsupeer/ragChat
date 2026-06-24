import { apiFetch } from '@/services/api';
import type { HardwareTelemetrySnapshot } from '@/types/hardware';

export async function fetchHardwareTelemetry(): Promise<HardwareTelemetrySnapshot> {
  return apiFetch<HardwareTelemetrySnapshot>('/hardware/telemetry');
}
