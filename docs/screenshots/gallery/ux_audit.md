# UX-аудит: тёмная тема + safe area

## Методология
- Все скриншоты сняты с safe area overlay (красные зоны: top 59px, bottom 34px)
- Telegram WebApp stub с `contentSafeAreaInset.top=59`, `safeAreaInset.bottom=34`
- Viewport: 390×844 (iPhone 14 Pro)
- Проверены обе темы: светлая и тёмная

## Карта проверки

| # | Экран | Dark OK | Safe Area OK | Проблемы |
|---|-------|---------|--------------|----------|
| 1 | create | | | |
| 2 | inbox | | | |
| 3 | drafts | | | |
| 4 | plans | | | |
| 5 | reels | | | |
| 6 | schedule | | | |
| 7 | keywords | | | |
| 8 | status | | | |
| 9 | drafts-detail-threads | | | |
| 10 | drafts-detail-carousel | | | |
| 11 | drafts-detail-reels | | | |
| 12 | drafts-detail-threads-series | | | |
| 13 | drafts-detail-scheduled | | | |
| 14 | drafts-detail-published | | | |
| 15 | inbox-detail | | | |
| 16 | plans-detail | | | |
| 17 | reels-detail | | | |
| 18 | create-threads | | | |
| 19 | create-carousel | | | |
| 20 | create-reels | | | |
| 21 | create-threads-series | | | |
| 22 | create-plan | | | |
| 23 | settings-menu | | | |
| 24 | settings-status | | | |
| 25 | settings-promo | | | |
| 26 | settings-team | | | |
| 27 | settings-accounts | | | |
| 28 | settings-brand | | | |
| 29 | aromas | | | |
| 30 | blends | | | |
| 31 | symptoms | | | |
| 32 | concepts | | | |
| 33 | practices | | | |
| 34 | sounds | | | |
| 35 | aromas-detail | | | |
| 36 | blends-detail | | | |
| 37 | symptoms-detail | | | |
| 38 | concepts-detail | | | |
| 39 | practices-detail | | | |
| 40 | sounds-detail | | | |
| 41 | blend-constructor | | | |
| 42 | recommendations-wizard | | | |
| 43 | reco-wizard-step2 | | | |
| 44 | reco-wizard-step3 | | | |
| 45 | saved-blends | | | |
| 46 | smart-search-results | | | |
| 47 | smart-search-empty | | | |
| 48 | reels-preview | | | |
| 49 | drafts-filter-kind-reels | | | |
| 50 | drafts-filter-status-approved | | | |
| 51 | drafts-search | | | |
| 52 | plans-mentions | | | |
| 53 | onboarding | | | |
| 54 | privacy | | | |

## Известные проблемы из анализа кода

### P1 — Серьёзно

| # | Что | Где | Описание |
|---|-----|-----|----------|
| 1 | Splash screen: `inset: 0` без safe area padding | `app.css:450-458` | Splash overlay растягивается на весь экран включая safe area. Контент splash может оказаться под notch |
| 2 | Onboarding overlay: `inset: 0` без safe area | `app.css:4389+` | Аналогично splash — overlay без учёта safe area insets |

### P2 — Улучшения

| # | Что | Где | Описание |
|---|-----|-----|----------|
| 3 | `padding-bottom: 100px` hardcoded | `app.css:2100` | Используется `calc(100px + env(safe-area-inset-bottom))` — корректно, но значение 100px может не совпадать с реальной высотой tab bar при изменении дизайна |
| 4 | Pull-to-refresh перекрывает status bar | `app.css:1854` | By design — pull indicator появляется в верхней зоне, но это стандартное поведение |
| 5 | Back button z-index=9 | `app.css:2128` | Может перекрываться модалками с высоким z-index. Рекомендуется поднять до z-index: 100+ |

## Заполняется после визуального аудита скриншотов

_Запустить `python scripts/make_screenshots.py --prod-data --baseline` и заполнить таблицу выше._
