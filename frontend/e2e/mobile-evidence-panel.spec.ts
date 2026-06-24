import { expect, test } from '@playwright/test';
import {
  assertBackendHealth,
  assertEvidencePanelBasics,
  gotoApp,
  openEvidenceViaInspect,
  runPortfolioChatFlow,
} from './helpers/demoFlow';

test.use({ viewport: { width: 1024, height: 768 } });

test.describe('Mobile evidence panel', () => {
  test('drawer opens via Inspect and closes via close control', async ({ page, request }) => {
    await assertBackendHealth(request);
    await gotoApp(page);
    await page.waitForTimeout(2_000);

    await runPortfolioChatFlow(page);

    await openEvidenceViaInspect(page);
    await assertEvidencePanelBasics(page);
    await expect(page.getByTestId('evidence-panel-shell')).toBeVisible();

    await page.getByTestId('evidence-panel-close').click();
    await expect(page.getByTestId('insight-panel')).not.toBeVisible();

    await page.getByTestId('evidence-panel-toggle').click();
    await expect(page.getByTestId('insight-reviewer-summary')).toBeVisible();
    await expect(page.getByTestId('evidence-panel-shell')).toBeVisible();
  });
});
