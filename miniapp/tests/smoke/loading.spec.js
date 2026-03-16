import { test, expect } from '@playwright/test';
import { injectTelegramMock } from '../fixtures/mock-telegram.js';

test.describe('Загрузка — smoke-тесты', () => {
  test('приложение загружается без JS-ошибок', async ({ page }) => {
    const jsErrors = [];
    page.on('pageerror', (err) => jsErrors.push(err.message));

    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });

    expect(jsErrors, `JS errors on load: ${jsErrors.join('; ')}`).toEqual([]);
  });

  test('splash screen исчезает после загрузки', async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });

    const splash = page.locator('#splash');
    // Splash should be hidden or removed after app is ready
    const isGone = await splash.evaluate((el) => {
      if (!el) return true;
      const style = getComputedStyle(el);
      return (
        style.display === 'none' ||
        style.opacity === '0' ||
        style.visibility === 'hidden' ||
        style.pointerEvents === 'none' ||
        el.hidden ||
        el.classList.contains('hidden')
      );
    }).catch(() => true);
    expect(isGone).toBe(true);
  });

  test('dark theme применяется корректно', async ({ page }) => {
    const jsErrors = [];
    page.on('pageerror', (err) => jsErrors.push(err.message));

    await injectTelegramMock(page, { colorScheme: 'dark' });
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });

    expect(jsErrors).toEqual([]);

    // Bottom tab bar should have dark background
    const tabBar = page.locator('#bottomTabBar');
    if (await tabBar.isVisible()) {
      const bg = await tabBar.evaluate((el) => getComputedStyle(el).backgroundColor);
      // Should not be white/light
      expect(bg).not.toBe('rgb(255, 255, 255)');
    }
  });

  test('скриншот после загрузки — базовый вид', async ({ page }) => {
    await injectTelegramMock(page);
    await page.goto('/');
    await page.waitForSelector('body.app-ready', { timeout: 15_000 });
    // Disable animations for stable screenshots
    await page.addStyleTag({
      content: '*, *::before, *::after { animation: none !important; transition: none !important; }',
    });
    await page.waitForTimeout(200);
    await expect(page).toHaveScreenshot('app-loaded.png');
  });
});
