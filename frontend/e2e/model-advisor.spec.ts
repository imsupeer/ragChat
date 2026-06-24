import { expect, test } from '@playwright/test';
import { gotoApp } from './helpers/demoFlow';

const DEFAULT_SETTINGS = {
  status: 'ok',
  chat_model: 'llama3.1:8b',
  default_chat_model: 'llama3.1:8b',
  query_rewrite_model: null,
  use_chat_model_for_query_rewrite: false,
  source: 'default',
  installed_status: 'installed',
  installed_models: ['llama3.1:8b', 'qwen3:8b'],
  catalog_known: true,
  installed: true,
  installed_match: 'llama3.1:8b',
  match_type: 'exact',
  install_command: 'ollama pull llama3.1:8b',
  run_command: 'ollama run llama3.1:8b',
  query_rewrite: {
    use_chat_model: false,
    configured_model: 'llama3.1:8b',
    effective_model: 'llama3.1:8b',
  },
};

const DEFAULT_RUNTIME = {
  status: 'ok',
  ollama: { reachable: true, status: 'ok', message: null },
  active_model: {
    name: 'llama3.1:8b',
    installed: true,
    installed_match: 'llama3.1:8b',
    match_type: 'exact',
    loaded: true,
    loaded_match: 'llama3.1:8b',
    loaded_match_type: 'exact',
    source: 'default',
    catalog_known: true,
    family: 'llama',
  },
  installed_models: [
    { name: 'llama3.1:8b', family: 'llama', size: 1, modified_at: 'now' },
    { name: 'qwen3:8b', family: 'qwen', size: 1, modified_at: 'now' },
  ],
  installed_models_count: 2,
  running_models: [{ name: 'llama3.1:8b', expires_at: 'now', size: 1, size_vram: 1 }],
  settings: {
    chat_model: 'llama3.1:8b',
    default_chat_model: 'llama3.1:8b',
    source: 'default',
  },
  runtime: {
    keep_alive: '5m',
    preload_supported: true,
    unload_supported: true,
    installed_models_count: 2,
    running_models_count: 1,
    loaded_detection: 'available',
    cold_start_likely: false,
  },
};

test.describe('Model Advisor', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/models/runtime**', async (route) => {
      const request = route.request();
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DEFAULT_RUNTIME),
        });
        return;
      }

      if (request.url().includes('/preload')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            model: 'llama3.1:8b',
            message: 'Model preload request completed.',
            keep_alive: '5m',
          }),
        });
        return;
      }

      if (request.url().includes('/unload')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            model: 'llama3.1:8b',
            message: 'Unload request completed. The selected chat model remains unchanged.',
          }),
        });
        return;
      }

      await route.continue();
    });

    await page.route('**/models/settings', async (route) => {
      const request = route.request();
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DEFAULT_SETTINGS),
        });
        return;
      }

      if (request.method() === 'PUT') {
        const body = JSON.parse(request.postData() || '{}');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...DEFAULT_SETTINGS,
            chat_model: body.chat_model,
            source: 'user',
            installed_status: 'installed',
          }),
        });
        return;
      }

      if (request.method() === 'POST' && request.url().includes('/reset')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DEFAULT_SETTINGS),
        });
        return;
      }

      await route.continue();
    });
  });

  test('renders model advisor section in sidebar', async ({ page }) => {
    await gotoApp(page);

    const advisor = page.getByTestId('model-advisor');
    await expect(advisor).toBeVisible();
    await expect(advisor.getByText('Model Advisor')).toBeVisible();
    await expect(advisor.getByText(/Estimates are approximate/i)).toBeVisible();
    await expect(page.getByTestId('model-runtime-status')).toBeVisible();
    await expect(page.getByTestId('model-runtime-header-status')).toContainText(/Loaded/i);
    await expect(page.getByTestId('model-advisor-current-model')).toContainText('llama3.1:8b');
  });

  test('expands form and shows hardware inputs with accessibility labels', async ({ page }) => {
    await gotoApp(page);

    const advisor = page.getByTestId('model-advisor');
    await advisor.getByRole('button', { name: /Expand model advisor/i }).click();

    await expect(advisor.getByLabel('VRAM (GB)')).toBeVisible();
    await expect(advisor.getByLabel('RAM (GB)', { exact: true })).toBeVisible();
    await expect(advisor.getByLabel('GPU model')).toBeVisible();
    await expect(advisor.getByLabel('CPU model')).toBeVisible();
    await expect(advisor.getByTestId('model-advisor-submit')).toBeVisible();
    await expect(page.getByTestId('active-chat-model-badge')).toContainText('llama3.1:8b');
  });

  test('shows recommendations with run command when API responds', async ({ page }) => {
    await page.route('**/models/recommendations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          confidence: 'high',
          hardware_summary: {
            vram_gb: 12,
            ram_gb: 32,
            detected_tier: 'mid_range_local_ai',
          },
          recommendations: [
            {
              rank: 1,
              model_id: 'qwen3-8b',
              display_name: 'Qwen 3 8B',
              ollama_name: 'qwen3:8b',
              category: 'best_overall',
              fit: 'comfortable',
              estimated_vram_gb: 6,
              why: ['Good balance for 12GB VRAM'],
              tradeoffs: ['Not as strong as larger coding models'],
              suggested_context: '4k-16k',
              run_command: 'ollama run qwen3:8b',
              install_command: 'ollama pull qwen3:8b',
              catalog_known: true,
              installed: true,
              match_type: 'exact',
            },
          ],
          avoid: [],
          notes: ['Estimates are approximate.'],
        }),
      });
    });

    await gotoApp(page);

    const advisor = page.getByTestId('model-advisor');
    await advisor.getByRole('button', { name: /Expand model advisor/i }).click();
    await advisor.getByLabel('VRAM (GB)').fill('12');
    await advisor.getByLabel('RAM (GB)', { exact: true }).fill('32');
    await advisor.getByTestId('model-advisor-submit').click();

    const results = page.getByTestId('model-advisor-results');
    await expect(results).toBeVisible();
    await expect(page.getByTestId('model-recommendation-best_overall')).toBeVisible();
    await expect(page.getByTestId('model-run-command')).toContainText('ollama run qwen3:8b');
  });

  test('use for chat updates settings and header badge', async ({ page }) => {
    await page.route('**/models/recommendations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          confidence: 'high',
          hardware_summary: { vram_gb: 12, ram_gb: 32, detected_tier: 'mid_range_local_ai' },
          recommendations: [
            {
              rank: 1,
              model_id: 'qwen3-8b',
              display_name: 'Qwen 3 8B',
              ollama_name: 'qwen3:8b',
              category: 'best_overall',
              fit: 'comfortable',
              estimated_vram_gb: 6,
              why: ['Good balance'],
              tradeoffs: [],
              suggested_context: '4k-16k',
              run_command: 'ollama run qwen3:8b',
              install_command: 'ollama pull qwen3:8b',
              catalog_known: true,
              installed: true,
              match_type: 'exact',
            },
          ],
          avoid: [],
          notes: [],
        }),
      });
    });

    await gotoApp(page);

    const advisor = page.getByTestId('model-advisor');
    await advisor.getByRole('button', { name: /Expand model advisor/i }).click();
    await advisor.getByTestId('model-advisor-submit').click();
    await page.getByTestId('model-use-for-chat-best_overall').click();

    await expect(page.getByTestId('model-advisor-current-model')).toContainText('qwen3:8b');
    await expect(page.getByTestId('active-chat-model-badge')).toContainText('qwen3:8b');
  });

  test('reset to default restores chat model display', async ({ page }) => {
    await gotoApp(page);

    const advisor = page.getByTestId('model-advisor');
    await advisor.getByRole('button', { name: /Expand model advisor/i }).click();
    await page.getByTestId('model-advisor-reset').click();

    await expect(page.getByTestId('model-advisor-current-model')).toContainText('llama3.1:8b');
    await expect(page.getByTestId('active-chat-model-badge')).toContainText('llama3.1:8b');
  });

  test('not-installed response shows install guidance', async ({ page }) => {
    await page.route('**/models/settings', async (route) => {
      if (route.request().method() === 'PUT') {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Model is not installed locally. Install it with `ollama pull mistral:7b` or choose another installed model.',
          }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DEFAULT_SETTINGS),
      });
    });

    await page.route('**/models/recommendations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          confidence: 'high',
          hardware_summary: { vram_gb: 12, ram_gb: 32, detected_tier: 'mid_range_local_ai' },
          recommendations: [
            {
              rank: 1,
              model_id: 'mistral-7b',
              display_name: 'Mistral 7B',
              ollama_name: 'mistral:7b',
              category: 'best_overall',
              fit: 'comfortable',
              estimated_vram_gb: 5,
              why: ['Balanced'],
              tradeoffs: [],
              suggested_context: '4k-16k',
              run_command: 'ollama run mistral:7b',
              install_command: 'ollama pull mistral:7b',
              catalog_known: true,
              installed: false,
              match_type: 'none',
            },
          ],
          avoid: [],
          notes: [],
        }),
      });
    });

    await gotoApp(page);

    const advisor = page.getByTestId('model-advisor');
    await advisor.getByRole('button', { name: /Expand model advisor/i }).click();
    await advisor.getByTestId('model-advisor-submit').click();
    await page.getByTestId('model-use-for-chat-best_overall').click();

    await expect(advisor.getByTestId('model-install-command')).toContainText('ollama pull mistral:7b');
  });

  test('missing model runtime shows header guidance', async ({ page }) => {
    await page.route('**/models/runtime**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...DEFAULT_RUNTIME,
            ollama: {
              reachable: true,
              status: 'degraded',
              message: 'Active chat model `mistral:7b` is not installed locally.',
            },
            active_model: {
              name: 'mistral:7b',
              installed: false,
              installed_match: null,
              match_type: 'none',
              source: 'user',
              catalog_known: true,
              family: 'mistral',
            },
          }),
        });
        return;
      }
      await route.continue();
    });

    await gotoApp(page);
    await expect(page.getByTestId('model-runtime-header-status')).toContainText(/Missing/i);
  });

  test('cold start guidance when installed but not loaded', async ({ page }) => {
    await page.route('**/models/runtime**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...DEFAULT_RUNTIME,
            active_model: {
              ...DEFAULT_RUNTIME.active_model,
              loaded: false,
              loaded_match: null,
              loaded_match_type: 'none',
            },
            running_models: [],
            runtime: {
              ...DEFAULT_RUNTIME.runtime,
              running_models_count: 0,
              cold_start_likely: true,
            },
          }),
        });
        return;
      }
      await route.continue();
    });

    await gotoApp(page);
    await expect(page.getByTestId('model-runtime-loaded-status')).toContainText('Not loaded');
    await expect(page.getByTestId('model-runtime-guidance')).toContainText(/cold-start latency/i);
    await expect(page.getByTestId('model-runtime-header-status')).toContainText(/Cold start likely/i);
  });

  test('loaded detection unsupported shows unknown guidance', async ({ page }) => {
    await page.route('**/models/runtime**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...DEFAULT_RUNTIME,
            active_model: {
              ...DEFAULT_RUNTIME.active_model,
              loaded: null,
              loaded_match: null,
              loaded_match_type: 'unknown',
            },
            running_models: [],
            runtime: {
              ...DEFAULT_RUNTIME.runtime,
              loaded_detection: 'unsupported',
              running_models_count: 0,
              cold_start_likely: null,
            },
          }),
        });
        return;
      }
      await route.continue();
    });

    await gotoApp(page);
    await expect(page.getByTestId('model-runtime-loaded-status')).toContainText('Unknown');
    await expect(page.getByTestId('model-runtime-guidance')).toContainText(/does not expose loaded-model detection/i);
  });

  test('preload action refreshes loaded state', async ({ page }) => {
    let loaded = false;

    await page.route('**/models/runtime**', async (route) => {
      const request = route.request();
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...DEFAULT_RUNTIME,
            active_model: {
              ...DEFAULT_RUNTIME.active_model,
              loaded,
              loaded_match: loaded ? 'llama3.1:8b' : null,
              loaded_match_type: loaded ? 'exact' : 'none',
            },
            running_models: loaded ? DEFAULT_RUNTIME.running_models : [],
            runtime: {
              ...DEFAULT_RUNTIME.runtime,
              running_models_count: loaded ? 1 : 0,
              cold_start_likely: !loaded,
            },
          }),
        });
        return;
      }

      if (request.url().includes('/preload')) {
        loaded = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            model: 'llama3.1:8b',
            message: 'Model preload request completed.',
            keep_alive: '5m',
            runtime: {
              ...DEFAULT_RUNTIME,
              active_model: { ...DEFAULT_RUNTIME.active_model, loaded: true },
            },
          }),
        });
        return;
      }

      await route.continue();
    });

    await gotoApp(page);
    const advisor = page.getByTestId('model-advisor');
    await advisor.getByRole('button', { name: /Expand model advisor/i }).click();
    await expect(page.getByTestId('model-runtime-loaded-status')).toContainText('Not loaded');
    await page.getByTestId('model-runtime-preload').click();
    await expect(page.getByTestId('model-runtime-loaded-status')).toContainText('Loaded');
  });

  test('model advisor explains selected vs installed guidance', async ({ page }) => {
    await gotoApp(page);
    await expect(page.getByTestId('model-advisor-current-model')).toContainText(/Selected chat model:/i);
    await expect(page.getByText(/Selected vs installed vs loaded vs preload/i)).toBeVisible();
    await expect(page.getByTestId('model-advisor-query-rewrite-policy')).toContainText(/Query rewriting uses the configured rewrite model/i);
  });

  test('header does not call browser ollama tags endpoint', async ({ page }) => {
    let ollamaDirectCalls = 0;
    await page.route('http://localhost:11434/**', async (route) => {
      ollamaDirectCalls += 1;
      await route.abort();
    });

    await gotoApp(page);
    await expect(page.getByTestId('ollama-status-badge')).toBeVisible();
    expect(ollamaDirectCalls).toBe(0);
  });

  test('preload and unload runtime actions show success', async ({ page }) => {
    await gotoApp(page);

    const advisor = page.getByTestId('model-advisor');
    await advisor.getByRole('button', { name: /Expand model advisor/i }).click();
    await page.getByTestId('model-runtime-preload').click();
    await expect(advisor.getByText(/Model preload request completed/i)).toBeVisible();
    await page.getByTestId('model-runtime-unload').click();
    await expect(advisor.getByText(/Unload request completed/i)).toBeVisible();
  });
});
