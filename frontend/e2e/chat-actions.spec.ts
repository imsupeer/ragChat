import { expect, test } from '@playwright/test';
import { assertBackendHealth, gotoApp, runPortfolioChatFlow } from './helpers/demoFlow';

test.describe('Chat action accessibility', () => {
  test('assistant actions and composer controls have accessible names', async ({ page, request }) => {
    await assertBackendHealth(request);
    await gotoApp(page);
    await page.waitForTimeout(2_000);

    await runPortfolioChatFlow(page);

    await expect(page.getByTestId('chat-send')).toHaveAttribute('aria-label', 'Send message');
    await expect(page.getByTestId('message-action-inspect').last()).toBeVisible();
    await expect(page.getByTestId('message-action-inspect').last()).toHaveAttribute('aria-label', /Inspect/i);
    await expect(page.getByTestId('message-action-copy').last()).toHaveAttribute('aria-label', /Copy assistant answer/i);
    await expect(page.getByTestId('message-action-regenerate').last()).toBeVisible();
    await expect(page.getByTestId('message-action-regenerate').last()).toHaveAttribute('aria-label', 'Regenerate answer');
  });
});
