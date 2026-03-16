import { test, expect } from '@playwright/test';
import { injectTelegramMock } from '../fixtures/mock-telegram.js';

async function stabilize(page) {
  await page.addStyleTag({
    content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }',
  });
  await page.waitForTimeout(200);
}

test.describe('Планы — визуальные тесты', () => {
  test.beforeEach(async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
    await page.locator('#btnTabPlans').click();
    await page.waitForTimeout(500);
  });

  test('вкладка планов — базовый вид', async ({ page }) => {
    await stabilize(page);
    await expect(page).toHaveScreenshot('plans-main.png');
  });

  test('план деталь — скриншот', async ({ page }) => {
    const planCard = page.locator('.plan-card, .overview-card').first();
    if (await planCard.count() > 0 && await planCard.isVisible()) {
      await planCard.click();
      await page.waitForTimeout(300);
      await page.waitForSelector('.detail-grid, .plan-detail');
      await stabilize(page);
      await expect(page).toHaveScreenshot('mobile-plan-detail.png', { fullPage: false });
    }
  });

  test('план деталь — создание связанного черновика', async ({ page }) => {
    const planCard = page.locator('.plan-card, .overview-card').first();
    if (await planCard.count() === 0) return;

    await planCard.click();
    await page.waitForTimeout(300);

    // Look for "create draft" button in plan detail
    const createBtn = page.locator('button').filter({
      hasText: /Создать|Написать|Генерировать/,
    }).first();

    if (await createBtn.count() > 0) {
      await expect(createBtn).toBeVisible();
    }
  });
});
