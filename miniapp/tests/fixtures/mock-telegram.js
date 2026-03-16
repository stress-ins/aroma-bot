/**
 * Mock Telegram WebApp SDK.
 * Injected via page.addInitScript() before app loads.
 */

/**
 * @param {import('@playwright/test').Page} page
 * @param {object} [options]
 * @param {number} [options.userId=12345]
 * @param {string} [options.firstName='Test']
 * @param {string} [options.colorScheme='dark']
 * @param {number} [options.dynamicIslandHeight=59]
 */
export async function injectTelegramMock(page, options = {}) {
  const {
    userId = 12345,
    firstName = 'Test',
    colorScheme = 'dark',
    dynamicIslandHeight = 59,
  } = options;

  await page.addInitScript(({ userId, firstName, colorScheme, dynamicIslandHeight }) => {
    // Skip onboarding
    localStorage.setItem('aroma_onboarded', '1');

    window.Telegram = {
      WebApp: {
        initData: `user=%7B%22id%22%3A${userId}%2C%22username%22%3A%22test%22%7D&hash=test`,
        initDataUnsafe: {
          user: { id: userId, first_name: firstName, username: 'test', language_code: 'ru' },
          hash: 'test_hash',
        },
        colorScheme,
        themeParams: {
          bg_color: '#1a1512',
          text_color: '#f0e8df',
          hint_color: '#a58f80',
          link_color: '#b45c3d',
          button_color: '#b45c3d',
          button_text_color: '#ffffff',
          secondary_bg_color: '#251e18',
        },
        contentSafeAreaInset: { top: dynamicIslandHeight },
        safeAreaInset: { top: dynamicIslandHeight, bottom: 34, left: 0, right: 0 },
        ready() {},
        expand() {},
        close() {},
        enableClosingConfirmation() {},
        disableClosingConfirmation() {},
        setHeaderColor() {},
        setBackgroundColor() {},
        showPopup(params, cb) { if (cb) cb('ok'); },
        showAlert(msg, cb) { if (cb) cb(); },
        showConfirm(msg, cb) { if (cb) cb(true); },
        openLink() {},
        openTelegramLink() {},
        HapticFeedback: {
          impactOccurred() {},
          notificationOccurred() {},
          selectionChanged() {},
        },
        MainButton: {
          text: '',
          color: '#b45c3d',
          textColor: '#ffffff',
          isVisible: false,
          isActive: true,
          show() { this.isVisible = true; },
          hide() { this.isVisible = false; },
          enable() { this.isActive = true; },
          disable() { this.isActive = false; },
          setText(t) { this.text = t; },
          onClick(fn) { this._onClick = fn; },
          offClick() {},
        },
        BackButton: {
          isVisible: false,
          show() { this.isVisible = true; },
          hide() { this.isVisible = false; },
          onClick(fn) { this._onClick = fn; },
          offClick() {},
        },
        version: '7.0',
        platform: 'ios',
        isExpanded: true,
        viewportHeight: 844,
        viewportStableHeight: 844,
      },
    };

    if (document.documentElement) {
      document.documentElement.style.setProperty(
        '--tg-content-inset-top', `${dynamicIslandHeight}px`,
      );
    }
  }, { userId, firstName, colorScheme, dynamicIslandHeight });
}

/**
 * Telegram mock without Dynamic Island (iPhone SE / older devices).
 */
export async function injectTelegramMockNoIsland(page, options = {}) {
  return injectTelegramMock(page, { ...options, dynamicIslandHeight: 0 });
}
