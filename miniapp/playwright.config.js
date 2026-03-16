import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'url';
import { join } from 'path';
import { tmpdir } from 'os';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');
const testTmpDir = join(tmpdir(), 'aroma-playwright-test');
const testDbPath = join(testTmpDir, 'test_aroma.db');
const testAssetsDir = join(testTmpDir, 'reels_assets');

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,

  globalSetup: './tests/fixtures/global-setup.js',

  use: {
    baseURL: 'http://127.0.0.1:8199',
    extraHTTPHeaders: {
      'X-Telegram-Init-Data': 'user=%7B%22id%22%3A12345%2C%22username%22%3A%22test%22%7D',
    },
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'iphone-14',
      testIgnore: '**/desktop.spec.js',
      use: {
        ...devices['iPhone 14'],
        browserName: 'webkit',
      },
    },
    {
      name: 'desktop',
      use: {
        browserName: 'webkit',
        viewport: { width: 1280, height: 900 },
        isMobile: false,
      },
      testMatch: '**/desktop.spec.js',
    },
  ],

  webServer: {
    command: `.venv/bin/python -m uvicorn miniapp_server:app --host 127.0.0.1 --port 8199`,
    port: 8199,
    cwd: projectRoot,
    reuseExistingServer: !process.env.CI,
    timeout: 20_000,
    env: {
      TELEGRAM_BOT_TOKEN: 'test-token',
      REPORT_TARGET_CHAT_ID: 'test-chat',
      AROMA_BYPASS_AUTH: '1',
      MINIAPP_AROMA_ALLOWED_USER_IDS: '12345',
      AROMA_DATABASE_URL: `sqlite+aiosqlite:///${testDbPath}`,
      AROMA_REELS_ASSETS_DIR: testAssetsDir,
      AROMA_CAROUSEL_ASSETS_DIR: join(testTmpDir, 'carousel_assets'),
    },
  },

  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.005,
      animations: 'disabled',
    },
  },

  reporter: [
    ['list'],
    ['html', { outputFolder: 'tests/report', open: 'on-failure' }],
  ],
});
