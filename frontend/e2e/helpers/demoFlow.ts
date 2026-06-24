import path from 'node:path';
import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';

export const FIXTURE_DOC = path.resolve(process.cwd(), '../scripts/eval_data/docs/limitations.md');
export const DEMO_QUESTION = 'Does PDF handling include OCR?';

export async function assertBackendHealth(request: APIRequestContext) {
  const health = await request.get('http://localhost:8000/health');
  expect(health.ok()).toBeTruthy();
}

export async function gotoApp(page: Page) {
  await page.goto('/');
  await expect(page.getByTestId('document-upload')).toBeVisible({ timeout: 30_000 });
}

export async function uploadFixtureDocument(page: Page, fixturePath = FIXTURE_DOC) {
  await page.getByTestId('document-upload-input').setInputFiles(fixturePath);
}

export async function waitForIndexedDocument(page: Page, filename: string): Promise<Locator> {
  const doc = page.locator(`[data-testid="document-item"][data-filename="${filename}"]`).first();
  await expect(doc).toBeVisible({ timeout: 120_000 });
  return doc;
}

export async function assertRetrievalScopeSearchingAll(page: Page) {
  await expect(page.getByTestId('retrieval-scope-badge')).toContainText(/Searching all documents/i);
}

export async function selectDocumentForRetrieval(page: Page, filename: string) {
  const doc = await waitForIndexedDocument(page, filename);
  await doc.click();
  await expect(page.getByTestId('retrieval-scope-badge')).toContainText(/Scoped to 1 selected/i);
  return doc;
}

export async function askQuestion(page: Page, question: string) {
  await page.getByTestId('chat-composer').fill(question);
  await page.getByTestId('chat-send').click();
}

export async function waitForAssistantAnswer(page: Page): Promise<Locator> {
  const assistant = page.getByTestId('chat-assistant-message').last();
  await expect(assistant).toBeVisible({ timeout: 120_000 });
  await expect(assistant).toHaveAttribute('data-is-streaming', 'false', { timeout: 120_000 });
  await expect(assistant.locator('.app-badge').filter({ hasText: /\d+ source/ })).toBeVisible();
  return assistant;
}

export async function runPortfolioChatFlow(page: Page, question = DEMO_QUESTION) {
  await uploadFixtureDocument(page);
  await assertRetrievalScopeSearchingAll(page);
  await selectDocumentForRetrieval(page, 'limitations.md');
  await askQuestion(page, question);
  return waitForAssistantAnswer(page);
}

export async function openEvidenceViaInspect(page: Page) {
  await page.getByTestId('message-action-inspect').last().click();
  await expect(page.getByTestId('insight-panel')).toBeVisible();
}

export async function assertEvidencePanelBasics(page: Page) {
  await expect(page.getByTestId('insight-panel')).toHaveAttribute('aria-label', /Evidence and debug panel/i);
  await expect(page.getByTestId('insight-reviewer-summary')).toBeVisible();
}

export async function assertSourcesTabContent(page: Page, expectedFilename: string) {
  await page.getByTestId('insight-tab-sources').click();
  const sourcesPanel = page.getByTestId('insight-sources-content');
  await expect(sourcesPanel.getByTestId('sources-summary')).toBeVisible();
  await expect(sourcesPanel.getByTestId('source-card').first()).toBeVisible();
  await expect(sourcesPanel).toContainText(expectedFilename);
}

export async function assertDebugUsedInPrompt(page: Page) {
  await page.getByTestId('insight-tab-debug').click();
  await expect(page.getByTestId('insight-debug-content')).toContainText(/Used in Prompt/i);
  await expect(page.getByTestId('debug-used-in-prompt')).toBeVisible();
}

export async function createFreshChat(page: Page) {
  await expect(page.getByRole('button', { name: 'New Chat' })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.animate-pulse')).toHaveCount(0, { timeout: 30_000 });

  const createChatResponse = page.waitForResponse(
    (response) => response.url().includes('/chats') && response.request().method() === 'POST' && response.ok(),
  );
  await page.getByRole('button', { name: 'New Chat' }).click();
  await createChatResponse;

  await expect(page.getByTestId('chat-empty-state')).toBeVisible({ timeout: 30_000 });
}
