/**
 * Playwright global setup — creates test database before server starts.
 */
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { seedDatabase } from './seed-data.js';

/** Fixed test dir path so config can reference it statically. */
export const TEST_TMP_DIR = join(tmpdir(), 'aroma-playwright-test');
export const TEST_DB_PATH = join(TEST_TMP_DIR, 'test_aroma.db');
export const TEST_ASSETS_DIR = join(TEST_TMP_DIR, 'reels_assets');

export default function globalSetup() {
  mkdirSync(TEST_TMP_DIR, { recursive: true });

  // Skip seeding if DB already exists (avoids corrupting a reused server's connection)
  if (existsSync(TEST_DB_PATH)) return;

  seedDatabase(TEST_DB_PATH, TEST_ASSETS_DIR);
}
