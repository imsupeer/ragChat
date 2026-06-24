export type HardwareTelemetryStatus = 'ok' | 'degraded' | 'disabled';

export type HardwareMetricStatus = 'ok' | 'disabled' | 'error';

export type GpuTelemetryStatus = 'ok' | 'unsupported' | 'unavailable' | 'disabled' | 'error';

export type CpuTelemetry = {
  status: HardwareMetricStatus | 'error';
  usage_percent?: number;
  logical_count?: number;
  physical_count?: number;
  message?: string;
};

export type MemoryTelemetry = {
  status: HardwareMetricStatus | 'error';
  total_bytes?: number;
  used_bytes?: number;
  available_bytes?: number;
  usage_percent?: number;
  message?: string;
};

export type GpuDeviceTelemetry = {
  name: string;
  vendor: string;
  usage_percent?: number;
  memory_total_bytes?: number;
  memory_used_bytes?: number;
  memory_free_bytes?: number;
  memory_usage_percent?: number;
  temperature_c?: number;
};

export type GpuTelemetry = {
  status: GpuTelemetryStatus;
  provider?: string;
  devices: GpuDeviceTelemetry[];
  message?: string | null;
};

export type HardwareTelemetrySnapshot = {
  status: HardwareTelemetryStatus;
  checked_at: string;
  poll_interval_seconds: number;
  cpu: CpuTelemetry;
  memory: MemoryTelemetry;
  gpu: GpuTelemetry;
};
