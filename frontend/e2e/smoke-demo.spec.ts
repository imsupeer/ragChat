import { expect, test } from '@playwright/test';
import {
  assertBackendHealth,
  assertDebugUsedInPrompt,
  assertEvidencePanelBasics,
  assertRetrievalScopeSearchingAll,
  assertSourcesTabContent,
  DEMO_QUESTION,
  gotoApp,
  openEvidenceViaInspect,
  selectDocumentForRetrieval,
  uploadFixtureDocument,
  waitForAssistantAnswer,
} from './helpers/demoFlow';

test.describe('RAG portfolio smoke demo', () => {
  test('upload fixture, chat, inspect sources and persisted debug', async ({ page, request }) => {
    await assertBackendHealth(request);
    await gotoApp(page);
    await page.waitForTimeout(2_000);

    await uploadFixtureDocument(page);
    await assertRetrievalScopeSearchingAll(page);
    await selectDocumentForRetrieval(page, 'limitations.md');

    await page.getByTestId('chat-composer').fill(DEMO_QUESTION);
    await expect(page.getByTestId('chat-send')).toHaveAttribute('aria-label', 'Send message');
    await page.getByTestId('chat-send').click();

    const assistant = await waitForAssistantAnswer(page);
    await expect(assistant).not.toContainText('Streaming...');
    await expect(page.getByTestId('message-action-inspect').last()).toBeVisible();

    await openEvidenceViaInspect(page);
    await assertEvidencePanelBasics(page);
    await assertSourcesTabContent(page, 'limitations.md');
    await assertDebugUsedInPrompt(page);

    await page.reload();

    const persistedAssistant = page.getByTestId('chat-assistant-message').last();
    await expect(persistedAssistant.locator('.app-badge').filter({ hasText: /\d+ source/ })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('insight-panel')).toBeVisible();
    await assertDebugUsedInPrompt(page);
    await expect(page.getByTestId('retrieval-scope-badge')).toBeVisible();
  });
});
