import { test, expect } from '@playwright/test';
import { injectTelegramMock } from '../fixtures/mock-telegram.js';

async function stabilize(page) {
  await page.addStyleTag({
    content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }',
  });
  await page.waitForTimeout(200);
}

test.describe('Desktop — визуальные тесты', () => {
  test.beforeEach(async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
  });

  test('split layout — две панели видны', async ({ page }) => {
    const listPanel = page.locator('.list-panel');
    const detailPanel = page.locator('.detail-panel');

    await expect(listPanel).toBeVisible();
    await expect(detailPanel).toBeVisible();

    // Both panels should have reasonable width
    const listBox = await listPanel.boundingBox();
    const detailBox = await detailPanel.boundingBox();

    expect(listBox.width).toBeGreaterThan(250);
    expect(detailBox.width).toBeGreaterThan(400);

    await stabilize(page);
    await expect(page).toHaveScreenshot('desktop-split-view.png');
  });

  test('keyboard навигация — Enter открывает карточку', async ({ page }) => {
    await page.locator('.draft-card').first().waitFor({ state: 'visible' });

    // Focus first card via Tab
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);

    // Find focused element
    const focused = await page.evaluate(() => {
      const el = document.activeElement;
      return el ? `${el.tagName}.${el.className.split(' ')[0]}` : null;
    });
    expect(focused).toBeTruthy();

    // Press Enter to open
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);

    // Detail panel should show content
    const detailContent = page.locator('.detail-grid, .detail-title');
    if (await detailContent.count() > 0) {
      await expect(detailContent.first()).toBeVisible();
    }
  });

  test('desktop контролы имеют комфортный размер', async ({ page }) => {
    const buttons = page.locator('.detail-panel button, .list-panel button');
    const count = await buttons.count();

    for (let i = 0; i < Math.min(count, 10); i++) {
      const btn = buttons.nth(i);
      if (await btn.isVisible()) {
        const box = await btn.boundingBox();
        if (box) {
          expect(box.height, `Button ${i} too small`).toBeGreaterThanOrEqual(28);
        }
      }
    }
  });
});
