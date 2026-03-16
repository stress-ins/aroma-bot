/**
 * Seed test database with schema and test data.
 * Replicates the Python fixture from tests/ui/test_miniapp_ui.py.
 */
import Database from 'better-sqlite3';
import { mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';

// 1x1 transparent PNG
const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Zk6cAAAAASUVORK5CYII=',
  'base64',
);

const SCHEMA = [
  `CREATE TABLE drafts (
    id INTEGER PRIMARY KEY,
    draft_id VARCHAR(32) UNIQUE,
    kind VARCHAR(64),
    topic VARCHAR(255),
    source VARCHAR(64),
    status VARCHAR(32),
    feedback VARCHAR(255),
    payload JSON,
    scheduled_at DATETIME,
    publish_platforms JSON DEFAULT '[]',
    external_ids JSON DEFAULT '{}',
    revision_notes VARCHAR(2000) DEFAULT '',
    published_at DATETIME,
    error VARCHAR(2000) DEFAULT '',
    created_at DATETIME
  )`,
  `CREATE TABLE draft_revisions (
    id INTEGER PRIMARY KEY,
    draft_id VARCHAR(32),
    rev_num INTEGER,
    payload JSON,
    author VARCHAR(64) DEFAULT 'user',
    note VARCHAR(512) DEFAULT '',
    created_at DATETIME
  )`,
  `CREATE TABLE publish_log (
    id INTEGER PRIMARY KEY,
    draft_id VARCHAR(32),
    platform VARCHAR(32),
    action VARCHAR(32),
    status VARCHAR(32) DEFAULT 'pending',
    external_id VARCHAR(255) DEFAULT '',
    error_message VARCHAR(1000) DEFAULT '',
    attempt_num INTEGER DEFAULT 1,
    created_at DATETIME
  )`,
  `CREATE TABLE todos (
    id INTEGER PRIMARY KEY,
    todo_id VARCHAR(36) UNIQUE,
    text VARCHAR(1000),
    created_at DATETIME
  )`,
  `CREATE TABLE aroma_cards (
    id INTEGER PRIMARY KEY,
    category VARCHAR(32) DEFAULT 'aroma',
    slug VARCHAR(64) UNIQUE,
    name VARCHAR(255),
    source_type VARCHAR(32),
    aliases JSON,
    payload JSON,
    created_at DATETIME,
    updated_at DATETIME
  )`,
  `CREATE TABLE plans (
    id INTEGER PRIMARY KEY,
    plan_id VARCHAR(32) UNIQUE,
    raw_text TEXT,
    entries JSON,
    created_at DATETIME
  )`,
  `CREATE TABLE brand_settings (
    id INTEGER PRIMARY KEY,
    brand_voice VARCHAR(4000) DEFAULT '',
    forbidden_phrases JSON DEFAULT '[]',
    base_instructions VARCHAR(4000) DEFAULT '',
    target_platforms JSON DEFAULT '[]',
    upload_post_user VARCHAR(255) DEFAULT '',
    upload_post_api_key VARCHAR(255) DEFAULT '',
    updated_at DATETIME
  )`,
  `CREATE TABLE blends (
    id INTEGER PRIMARY KEY,
    slug VARCHAR(128) UNIQUE,
    name VARCHAR(255),
    goal VARCHAR(512) DEFAULT '',
    ingredients JSON DEFAULT '[]',
    indications VARCHAR(2000) DEFAULT '',
    contraindications VARCHAR(2000) DEFAULT '',
    compatibility_notes VARCHAR(2000) DEFAULT '',
    source_pdf VARCHAR(255) DEFAULT '',
    created_at DATETIME,
    updated_at DATETIME
  )`,
  `CREATE TABLE mentions (
    id INTEGER PRIMARY KEY,
    mention_id VARCHAR(36) UNIQUE,
    platform VARCHAR(32),
    external_id VARCHAR(255),
    type VARCHAR(32),
    author_username VARCHAR(255),
    author_name VARCHAR(255),
    content VARCHAR(4000),
    url VARCHAR(1024),
    context_post VARCHAR(4000),
    received_at DATETIME,
    status VARCHAR(32) DEFAULT 'pending'
  )`,
  `CREATE TABLE mention_replies (
    id INTEGER PRIMARY KEY,
    reply_id VARCHAR(36) UNIQUE,
    mention_id VARCHAR(36),
    tone VARCHAR(32),
    content VARCHAR(2000),
    generated_at DATETIME,
    selected BOOLEAN DEFAULT 0,
    published_at DATETIME,
    publish_error VARCHAR(1000)
  )`,
  `CREATE TABLE platform_tokens (
    id INTEGER PRIMARY KEY,
    platform VARCHAR(32) UNIQUE,
    access_token VARCHAR(1024),
    expires_at DATETIME,
    updated_at DATETIME
  )`,
  `CREATE TABLE subscription_users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE,
    tier VARCHAR(32) DEFAULT 'free',
    tier_expires_at DATETIME,
    daily_usage INTEGER DEFAULT 0,
    daily_usage_date VARCHAR(10) DEFAULT '',
    created_at DATETIME,
    updated_at DATETIME
  )`,
];

const NOW = '2026-03-11T18:00:00+00:00';

const REELS_PAYLOAD = {
  scenario: 'Короткий сценарий рилса про вечернее переключение.',
  images_ready: 1,
  storyboard: [
    {
      timecode: '0-3 сек',
      scene: '**Текст на экране:** Попробуй сегодня\n\n## Сцена\nРуки закрывают ноутбук',
      angle: 'Крупный план',
      gemini_prompt: 'warm evening desk, close-up hands closing laptop',
      current_asset: {
        url: '/generated/reels_assets/reels001/frame_1.png',
        filename: 'frame_1.png',
        generated_at: NOW,
      },
    },
  ],
};

const THREADS_PAYLOAD = {
  angle: 'Через телесный переключатель, а не силу воли.',
  hook: 'Иногда телу нужен не совет, а сигнал безопасности.',
  caption: 'Короткий текст для Threads про переключение после работы.',
  cta: 'Если откликается, напиши мне.',
  visual_prompt: 'warm calm evening ritual, soft light, cozy interior',
};

const CAROUSEL_PAYLOAD = {
  slides: [
    'Стресс часто начинается с перегрузки ощущений.',
    'Запах и звук помогают мягко вернуть фокус.',
  ],
  img_prompts: [
    'calm sensory ritual, soft amber light, minimalist editorial photo',
    'wellness still life, aroma bottle, warm shadows, premium composition',
  ],
  slide_images: [
    { url: '/generated/carousel_assets/carousel001/slide_1.png', filename: 'slide_1.png', generated_at: NOW },
    null,
  ],
  slide_image_versions: [
    [{ url: '/generated/carousel_assets/carousel001/slide_1.png', filename: 'slide_1.png', generated_at: NOW, prompt: 'prompt 1' }],
    [],
  ],
  img_prompt_notes: ['', ''],
  cta: 'Напиши, если хочешь такую карусель под свой проект.',
};

const REFERENCE_CARDS = [
  { slug: 'lavender', name: 'Лаванда', category: 'aroma', source_type: 'herb' },
  { slug: 'grounding', name: 'Grounding', category: 'blend', source_type: 'blend' },
  { slug: 'stress', name: 'Стресс', category: 'symptom', source_type: 'symptom' },
  { slug: 'limbic-system', name: 'Лимбическая система', category: 'concept', source_type: 'theory' },
  { slug: 'box-breathing', name: 'Квадратное дыхание', category: 'practice', source_type: 'practice' },
  { slug: 'gong', name: 'Гонг', category: 'sound', source_type: 'instrument' },
];

const SYMPTOM_CARDS = [
  { slug: 'headache', name: 'Головная боль', group: 'НЕРВНАЯ СИСТЕМА' },
  { slug: 'anxiety', name: 'Тревожность', group: 'НЕРВНАЯ СИСТЕМА' },
  { slug: 'indigestion', name: 'Несварение желудка', group: 'ПИЩЕВАРЕНИЕ' },
  { slug: 'insomnia', name: 'Бессонница', group: 'СОН И ОТДЫХ' },
  { slug: 'fatigue', name: 'Усталость и истощение', group: 'ЭНЕРГИЯ' },
  { slug: 'hypertension', name: 'Гипертония', group: 'СЕРДЕЧНО-СОСУДИСТАЯ' },
  { slug: 'depression', name: 'Депрессия', group: 'ПСИХОЭМОЦИОНАЛЬНОЕ' },
  { slug: 'allergy', name: 'Аллергия', group: 'ИММУНИТЕТ И КОЖА' },
];

const PLAN_ENTRIES = [
  {
    day_label: 'Понедельник',
    platform: 'Threads',
    format_label: 'пост',
    goal: 'Доверие',
    topic: 'Почему вечерний ритуал помогает нервной системе',
    angle: 'Через простые телесные сигналы.',
  },
];

/**
 * @param {string} dbPath - Absolute path to SQLite database file
 * @param {string} assetsDir - Absolute path to assets directory
 */
export function seedDatabase(dbPath, assetsDir) {
  const db = new Database(dbPath);

  // Create schema
  for (const sql of SCHEMA) {
    db.exec(sql);
  }

  // Create reels asset file
  const reelsAssetDir = join(assetsDir, 'reels001');
  mkdirSync(reelsAssetDir, { recursive: true });
  writeFileSync(join(reelsAssetDir, 'frame_1.png'), PNG_1X1);

  // Create carousel asset dir + placeholder
  const carouselAssetDir = join(assetsDir.replace('reels_assets', 'carousel_assets'), 'carousel001');
  mkdirSync(carouselAssetDir, { recursive: true });
  writeFileSync(join(carouselAssetDir, 'slide_1.png'), PNG_1X1);

  // Insert drafts
  const insertDraft = db.prepare(
    'INSERT INTO drafts (draft_id, kind, topic, source, status, feedback, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
  );
  insertDraft.run('reels001', 'reels', 'Вечерний ароматический ритуал', '/miniapp', 'draft', '', JSON.stringify(REELS_PAYLOAD), NOW);
  insertDraft.run('threads001', 'threads', 'Как мягко выйти из рабочего напряжения', '/content', 'in_review', 'worked', JSON.stringify(THREADS_PAYLOAD), NOW);
  insertDraft.run('carousel001', 'carousel', 'Сенсорная карусель для вечернего ритуала', '/miniapp', 'draft', '', JSON.stringify(CAROUSEL_PAYLOAD), NOW);

  // Insert reference cards
  const insertCard = db.prepare(
    'INSERT INTO aroma_cards (slug, name, category, source_type, aliases, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
  );
  for (const card of REFERENCE_CARDS) {
    insertCard.run(card.slug, card.name, card.category, card.source_type, '[]', '{}', NOW, NOW);
  }

  // Insert symptom cards
  for (const s of SYMPTOM_CARDS) {
    insertCard.run(
      s.slug, s.name, 'symptom', 'symptom', '[]',
      JSON.stringify({ category_group: s.group, parent_group: s.group }),
      NOW, NOW,
    );
  }

  // Insert plan
  db.prepare('INSERT INTO plans (plan_id, raw_text, entries, created_at) VALUES (?, ?, ?, ?)').run(
    '20260311180000',
    '## Контент-план\n- Понедельник: Threads\n- Среда: Reels',
    JSON.stringify(PLAN_ENTRIES),
    NOW,
  );

  db.close();
}
