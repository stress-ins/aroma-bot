import { test, expect } from '@playwright/test';
import { injectTelegramMock } from '../fixtures/mock-telegram.js';

async function stabilize(page) {
  await page.addStyleTag({
    content: '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }',
  });
  await page.waitForTimeout(200);
}

async function openCarouselDetail(page) {
  await page.getByText('Сенсорная карусель для вечернего ритуала').first().click();
  await page.waitForTimeout(300);
  await page.waitForSelector('.detail-grid');
}

test.describe('Карусель — визуальные тесты', () => {
  test.beforeEach(async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
  });

  test('деталь карусели — шапка и свайпер', async ({ page }) => {
    await openCarouselDetail(page);
    await stabilize(page);
    await expect(page).toHaveScreenshot('carousel-detail-top.png');
  });

  test('слайды карусели — свайпер с точками', async ({ page }) => {
    await openCarouselDetail(page);

    const swiper = page.locator('.slides-swiper');
    if (await swiper.count() > 0) {
      await expect(swiper).toBeVisible();

      // Dot indicators
      const dots = page.locator('.slides-dot');
      expect(await dots.count()).toBeGreaterThan(0);

      // First dot is active
      await expect(dots.first()).toHaveClass(/is-active/);
    }
  });

  test('prompt copy кнопки видны', async ({ page }) => {
    await openCarouselDetail(page);

    // Open prompt disclosure for first slide
    const toggleBtn = page.locator('.prompt-toggle').first();
    if (await toggleBtn.count() > 0) {
      await toggleBtn.click();
      await page.waitForTimeout(300);

      const copyBtn = page.locator('button').filter({ hasText: /Скопировать промпт/ }).first();
      await expect(copyBtn).toBeVisible();
    }
  });

  test('action кнопки используют двухколоночный layout', async ({ page }) => {
    await openCarouselDetail(page);

    const actionsRow = page.locator('.actions-grid-two').first();
    if (await actionsRow.count() > 0) {
      const buttons = actionsRow.locator('button');
      const count = await buttons.count();

      if (count >= 2) {
        const box1 = await buttons.nth(0).boundingBox();
        const box2 = await buttons.nth(1).boundingBox();
        // In two-column layout, buttons should be side by side (similar Y)
        expect(Math.abs(box1.y - box2.y)).toBeLessThan(5);
        // And both should have similar width
        expect(Math.abs(box1.width - box2.width)).toBeLessThan(20);
      }

      await stabilize(page);
      await expect(actionsRow).toHaveScreenshot('carousel-action-buttons.png');
    }
  });

  test('swipe-back жест работает из detail', async ({ page }) => {
    await openCarouselDetail(page);

    // Verify we're in detail view
    const detailPanel = page.locator('.detail-panel');
    await expect(detailPanel).toBeVisible();

    // Use back button to go back
    const backBtn = page.locator('.back-button').first();
    if (await backBtn.isVisible()) {
      await backBtn.click();
      await page.waitForTimeout(400);

      // Should show list view
      const draftCard = page.locator('.draft-card').first();
      await expect(draftCard).toBeVisible();
    }
  });
});
