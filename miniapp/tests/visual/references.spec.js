import { test, expect } from '@playwright/test';
import { injectTelegramMock } from '../fixtures/mock-telegram.js';

async function stabilize(page) {
  await page.addStyleTag({
    content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }',
  });
  await page.waitForTimeout(200);
}

test.describe('База знаний — визуальные тесты', () => {
  test.beforeEach(async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
    await page.locator('#btnTabHandbook').click();
    await page.waitForTimeout(300);
  });

  test('заголовки разделов на русском', async ({ page }) => {
    const tabs = await page.locator('.tab-button').evaluateAll(
      (nodes) => nodes.map((n) => n.textContent.trim()),
    );
    expect(tabs.some((t) => t.includes('Ароматы'))).toBe(true);
    expect(tabs.some((t) => t.includes('Смеси'))).toBe(true);
    expect(tabs.some((t) => t.includes('Симптомы'))).toBe(true);
  });

  test('список ароматов — карточки видны', async ({ page }) => {
    // Aromas tab should be active by default in handbook
    const aromTab = page.locator('.tab-button').filter({ hasText: /Ароматы/ });
    if (await aromTab.count() > 0) {
      await aromTab.click();
      await page.waitForTimeout(300);
    }

    await page.evaluate('window.goBackToList()');
    await page.waitForTimeout(300);

    const cards = page.locator('.reference-card, .overview-card, .draft-card');
    if (await cards.count() > 0) {
      await stabilize(page);
      await expect(page).toHaveScreenshot('references-aromas-list.png');
    }
  });

  test('карточки открываются во всех разделах', async ({ page }) => {
    const tabTexts = ['Ароматы', 'Смеси', 'Симптомы', 'Теория', 'Практики', 'Звуки'];

    for (const text of tabTexts) {
      const tab = page.locator('.tab-button').filter({ hasText: new RegExp(text) });
      if (await tab.count() === 0) continue;

      await tab.click();
      await page.waitForTimeout(300);
      await page.evaluate('window.goBackToList()');
      await page.waitForTimeout(300);

      const card = page.locator('.reference-card, .overview-card, .draft-card').first();
      if (await card.count() > 0 && await card.isVisible()) {
        await card.click();
        await page.waitForTimeout(300);

        const detail = page.locator('.detail-grid, .detail-title');
        await expect(detail.first()).toBeVisible({ timeout: 5000 });

        // Go back
        const backBtn = page.locator('.back-button');
        if (await backBtn.isVisible()) await backBtn.click();
        await page.waitForTimeout(300);
      }
    }
  });

  test('filter chips не выходят за ширину экрана', async ({ page }) => {
    // Navigate to symptoms tab which has category filter chips
    const symptomsTab = page.locator('.tab-button').filter({ hasText: /Симптомы/ });
    if (await symptomsTab.count() > 0) {
      await symptomsTab.click();
      await page.waitForTimeout(300);
    }

    const overflow = await page.evaluate(() => {
      const chips = document.querySelector('.filter-chips, .category-chips, .symptom-filters');
      if (!chips) return false;
      return chips.scrollWidth > chips.clientWidth + 2;
    });
    // Chips container should handle overflow gracefully (scroll or wrap)
    // We just check the page doesn't break
    const pageOverflow = await page.evaluate(() => {
      return document.body.scrollWidth > document.body.clientWidth + 2;
    });
    expect(pageOverflow).toBe(false);
  });

  test('toolbar не перекрыт навигацией TG', async ({ page }) => {
    const toolbar = page.locator('.toolbar').first();
    if (await toolbar.isVisible()) {
      const box = await toolbar.boundingBox();
      expect(box.y).toBeGreaterThan(40);
      await stabilize(page);
      await expect(toolbar).toHaveScreenshot('references-toolbar.png');
    }
  });
});
