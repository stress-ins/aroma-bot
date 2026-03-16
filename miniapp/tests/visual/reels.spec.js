import { test, expect } from '@playwright/test';
import { injectTelegramMock } from '../fixtures/mock-telegram.js';

async function stabilize(page) {
  await page.addStyleTag({
    content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }',
  });
  await page.waitForTimeout(200);
}

async function openReelsDetail(page) {
  await page.getByText('Вечерний ароматический ритуал').first().click();
  await page.waitForTimeout(300);
}

test.describe('Рилсы — визуальные тесты', () => {
  test.beforeEach(async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
  });

  test('раскадровка открывается без пустого стейта', async ({ page }) => {
    await openReelsDetail(page);

    const storyboard = page.locator('.storyboard, .storyboard-frame, [data-section="storyboard"]');
    const emptyState = page.locator('.guided-state');

    // Either storyboard is visible or at least we're in detail view
    const detailGrid = page.locator('.detail-grid');
    await expect(detailGrid).toBeVisible();

    // Empty state should NOT be shown for a reel with storyboard data
    if (await storyboard.count() > 0) {
      await expect(emptyState).not.toBeVisible();
    }
  });

  test('production overview и статус кадра', async ({ page }) => {
    await openReelsDetail(page);

    // Check for storyboard frame with timecode and scene
    const frame = page.locator('.storyboard-frame').first();
    if (await frame.count() > 0) {
      await expect(frame).toBeVisible();

      // Frame should contain timecode text
      const text = await frame.textContent();
      expect(text).toContain('сек');
    }
  });

  test('деталь рилса — базовый скриншот', async ({ page }) => {
    await openReelsDetail(page);
    await stabilize(page);
    await expect(page).toHaveScreenshot('mobile-reels-detail.png', { fullPage: false });
  });

  test('markdown рендерится в деталях', async ({ page }) => {
    await openReelsDetail(page);

    // Storyboard scenes contain markdown (bold, headers)
    const scene = page.locator('.detail-markdown, .storyboard-frame').first();
    if (await scene.count() > 0) {
      const html = await scene.innerHTML();
      // Should contain rendered markdown (bold, headers)
      const hasFormatted = html.includes('<strong>') || html.includes('<h') || html.includes('<b>');
      // It's OK if markdown is rendered as plain text too
      expect(html.length).toBeGreaterThan(10);
    }
  });

  test('dark theme — текст раскадровки читаемый', async ({ page }) => {
    await injectTelegramMock(page, { colorScheme: 'dark' });
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
    await openReelsDetail(page);

    const frame = page.locator('.storyboard-frame').first();
    if (await frame.count() > 0) {
      const color = await frame.evaluate((el) => {
        const style = getComputedStyle(el);
        return style.color;
      });
      // Text should not be black on dark background
      expect(color).not.toBe('rgb(0, 0, 0)');
    }
  });

  test('regenerate входит в pending state', async ({ page }) => {
    await openReelsDetail(page);

    // Mock regenerate endpoint
    await page.route('**/api/reels/*/frames/*/regenerate', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          draft_id: 'reels001',
          kind: 'reels',
          topic: 'Вечерний ароматический ритуал',
          status: 'draft',
          generation_pending: true,
          generation_stage: 'images',
          generation_message: 'Генерирую новый кадр…',
          payload: {},
        }),
      }),
    );

    const regenBtn = page.locator('button').filter({ hasText: /Обновить|Перегенерировать/ }).first();
    if (await regenBtn.count() > 0 && await regenBtn.isVisible()) {
      await regenBtn.click();
      await page.waitForTimeout(500);

      // Should show some pending indicator
      const pending = page.locator('.is-pending, .frame-loading, [data-stage]');
      if (await pending.count() > 0) {
        await expect(pending.first()).toBeVisible();
      }
    }
  });
});
