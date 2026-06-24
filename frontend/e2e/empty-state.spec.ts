import { expect, test } from '@playwright/test';
import { createFreshChat, gotoApp } from './helpers/demoFlow';

test.describe('Empty state guidance', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript(() => {
      localStorage.clear();
    });
  });

  test('shows contextual empty state when chat has no messages', async ({ page }) => {
    await gotoApp(page);
    await createFreshChat(page);

    const uploadGuidance = page.getByTestId('empty-state-upload-guidance');
    if (await uploadGuidance.isVisible()) {
      await expect(page.getByText(/How it works/i)).toBeVisible();
      return;
    }

    await expect(page.getByTestId('empty-state-suggestion').first()).toBeVisible();
  });
});
