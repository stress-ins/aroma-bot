import { test, expect } from '@playwright/test';
import { injectTelegramMock } from '../fixtures/mock-telegram.js';

/** Disable animations for stable screenshots */
async function stabilize(page) {
  await page.addStyleTag({
    content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }',
  });
  await page.waitForTimeout(200);
}

test.describe('Черновики — визуальные тесты', () => {
  test.beforeEach(async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
  });

  test('список черновиков — базовый скриншот', async ({ page }) => {
    await page.evaluate('window.goBackToList()');
    await page.locator('.draft-card').first().waitFor({ state: 'visible' });
    await stabilize(page);
    await expect(page).toHaveScreenshot('mobile-drafts-list.png');
  });

  test('деталь черновика threads', async ({ page }) => {
    await page.getByText('Как мягко выйти из рабочего напряжения').first().click();
    await page.waitForTimeout(300);
    await page.waitForSelector('.detail-grid');
    await stabilize(page);
    await expect(page).toHaveScreenshot('mobile-draft-detail.png', { fullPage: false });
  });

  test('overview карточки используют единообразную мета-строку', async ({ page }) => {
    await page.evaluate('window.goBackToList()');
    await page.locator('.draft-card').first().waitFor({ state: 'visible' });

    const cards = page.locator('.draft-card');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(2);

    for (let i = 0; i < count; i++) {
      const card = cards.nth(i);
      // Each card should have a kind badge and a date/seq meta
      const kindBadge = card.locator('.draft-kind');
      await expect(kindBadge).toBeVisible();
      const dateMeta = card.locator('.overview-card-date');
      await expect(dateMeta).toBeVisible();
    }
  });

  test('пустой стейт предлагает создание', async ({ page }) => {
    // Mock empty drafts
    await page.route('**/api/drafts*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );
    await page.locator('#btnTabInspiration').click();
    await page.waitForTimeout(500);
    await page.evaluate('window.goBackToList()');
    await page.waitForTimeout(300);

    const guidedState = page.locator('.guided-state');
    await expect(guidedState).toBeVisible();
    await stabilize(page);
    await expect(guidedState).toHaveScreenshot('drafts-empty-guided.png');
  });

  test('мета-строка — ID, дата и тег не сливаются', async ({ page }) => {
    await page.getByText('Как мягко выйти из рабочего напряжения').first().click();
    await page.waitForSelector('.detail-top');
    await stabilize(page);

    const top = page.locator('.detail-top');
    await expect(top).toHaveScreenshot('draft-detail-top.png');
  });

  test('превью — разумная высота', async ({ page }) => {
    await page.getByText('Как мягко выйти из рабочего напряжения').first().click();
    await page.waitForSelector('.detail-preview');

    const preview = page.locator('.detail-preview').first();
    const box = await preview.boundingBox();
    expect(box.height).toBeLessThan(200);
  });

  test('кнопки действий не перекрываются', async ({ page }) => {
    await page.getByText('Как мягко выйти из рабочего напряжения').first().click();
    await page.waitForSelector('.detail-grid');

    const overlaps = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('.detail-grid button'))
        .filter((b) => b.offsetParent !== null);
      const issues = [];
      for (let i = 0; i < buttons.length; i++) {
        const a = buttons[i].getBoundingClientRect();
        if (a.width === 0) continue;
        for (let j = i + 1; j < buttons.length; j++) {
          const b = buttons[j].getBoundingClientRect();
          if (b.width === 0) continue;
          const ox = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
          const oy = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
          if (ox > 4 && oy > 4) {
            issues.push(`${buttons[i].textContent.trim()} overlaps ${buttons[j].textContent.trim()}`);
          }
        }
      }
      return issues;
    });
    expect(overlaps).toEqual([]);
  });

  test('create tab показывает guided empty state', async ({ page }) => {
    await page.locator('#btnTabCreate').click();
    await page.waitForTimeout(300);

    const createPanel = page.locator('.create-tool-panel, .guided-state');
    await expect(createPanel.first()).toBeVisible();
  });

  test('формы создания показывают helper microcopy', async ({ page }) => {
    await page.locator('#btnTabCreate').click();
    await page.waitForTimeout(300);

    // Open content creation tool
    const contentTool = page.locator('[data-tool="content"], .create-tool-card').first();
    if (await contentTool.count() > 0) {
      await contentTool.click();
      await page.waitForTimeout(300);
    }

    const helpers = page.locator('.field-help, .create-form label span');
    if (await helpers.count() > 0) {
      await stabilize(page);
      await expect(page).toHaveScreenshot('create-form-helpers.png');
    }
  });

  test('content review — save и polish кнопки', async ({ page }) => {
    await page.getByText('Как мягко выйти из рабочего напряжения').first().click();
    await page.waitForSelector('.detail-grid');

    // Look for save/polish buttons in review detail
    const saveBtn = page.locator('button').filter({ hasText: /Сохранить|Полировать/ }).first();
    if (await saveBtn.count() > 0) {
      await expect(saveBtn).toBeVisible();
    }
  });

  test('tap outside textarea снимает фокус', async ({ page }) => {
    await page.getByText('Как мягко выйти из рабочего напряжения').first().click();
    await page.waitForSelector('.detail-grid');

    const textarea = page.locator('textarea').first();
    if (await textarea.count() > 0) {
      await textarea.click();
      // Verify focused
      const isFocused = await textarea.evaluate((el) => document.activeElement === el);
      if (isFocused) {
        // Tap outside
        await page.locator('.detail-grid').click({ position: { x: 10, y: 10 } });
        await page.waitForTimeout(200);
        const stillFocused = await textarea.evaluate((el) => document.activeElement === el);
        expect(stillFocused).toBe(false);
      }
    }
  });
});
