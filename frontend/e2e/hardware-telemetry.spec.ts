import { expect, test } from '@playwright/test';
import { gotoApp } from './helpers/demoFlow';

const DEFAULT_TELEMETRY = {
  status: 'ok',
  checked_at: new Date().toISOString(),
  poll_interval_seconds: 5,
  cpu: {
    status: 'ok',
    usage_percent: 24.5,
    logical_count: 16,
    physical_count: 8,
  },
  memory: {
    status: 'ok',
    total_bytes: 34_359_738_368,
    used_bytes: 17_179_869_184,
    available_bytes: 17_179_869_184,
    usage_percent: 50.0,
  },
  gpu: {
    status: 'unsupported',
    provider: 'none',
    devices: [],
    message:
      'GPU telemetry unavailable. CPU/RAM metrics are still available. Install NVIDIA or AMD monitoring tools to enable GPU/VRAM metrics.',
  },
};

const GPU_TELEMETRY = {
  ...DEFAULT_TELEMETRY,
  gpu: {
    status: 'ok',
    provider: 'nvidia',
    devices: [
      {
        name: 'NVIDIA GeForce RTX 3060',
        vendor: 'NVIDIA',
        usage_percent: 42.0,
        memory_total_bytes: 12_884_901_888,
        memory_used_bytes: 6_442_450_944,
        memory_usage_percent: 50.0,
      },
    ],
    message: null,
  },
};

test.describe('Hardware telemetry', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/hardware/telemetry**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_TELEMETRY),
      });
    });

    await page.route('**/models/runtime**', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          ollama: { reachable: true, status: 'ok', message: null },
          active_model: {
            name: 'llama3.1:8b',
            installed: true,
            loaded: true,
            source: 'default',
          },
          installed_models: [],
          installed_models_count: 0,
          running_models: [],
          settings: { chat_model: 'llama3.1:8b', default_chat_model: 'llama3.1:8b', source: 'default' },
          runtime: {
            keep_alive: '5m',
            preload_supported: true,
            unload_supported: true,
            installed_models_count: 0,
            running_models_count: 0,
            loaded_detection: 'available',
            cold_start_likely: false,
          },
        }),
      });
    });

    await page.route('**/models/settings**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          chat_model: 'llama3.1:8b',
          default_chat_model: 'llama3.1:8b',
          source: 'default',
          installed_status: 'installed',
          installed_models: ['llama3.1:8b'],
        }),
      });
    });
  });

  test('renders CPU and RAM metrics in sidebar', async ({ page }) => {
    await gotoApp(page);

    const panel = page.getByTestId('hardware-telemetry-panel');
    await expect(panel).toBeVisible();
    await expect(page.getByTestId('hardware-telemetry-cpu')).toContainText('24.5%');
    await expect(page.getByTestId('hardware-telemetry-ram')).toContainText('50.0%');
    await expect(page.getByTestId('hardware-telemetry-gpu-fallback')).toContainText(/GPU telemetry unavailable/i);
  });

  test('refresh button requests telemetry again', async ({ page }) => {
    let requestCount = 0;

    await page.route('**/hardware/telemetry**', async (route) => {
      requestCount += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_TELEMETRY),
      });
    });

    await gotoApp(page);
    await expect.poll(() => requestCount).toBeGreaterThanOrEqual(1);

    await page.getByTestId('hardware-telemetry-refresh').click();
    await expect.poll(() => requestCount).toBeGreaterThanOrEqual(2);
  });

  test('renders GPU and VRAM when provider returns devices', async ({ page }) => {
    await page.route('**/hardware/telemetry**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(GPU_TELEMETRY),
      });
    });

    await gotoApp(page);

    await expect(page.getByTestId('hardware-telemetry-gpu')).toBeVisible();
    await expect(page.getByTestId('hardware-telemetry-gpu')).toContainText('NVIDIA GeForce RTX 3060');
    await expect(page.getByTestId('hardware-telemetry-gpu-usage')).toContainText('42.0%');
    await expect(page.getByTestId('hardware-telemetry-vram')).toContainText('50.0%');
  });
});
