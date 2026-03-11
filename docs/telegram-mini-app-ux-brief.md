# Telegram Mini App UX Brief

## Goal

Спроектировать Telegram Mini App как рабочую панель для контент-команды, чтобы основные тяжёлые сценарии не упирались в длинные цепочки сообщений внутри чата.

Mini App не заменяет бот. Он берёт на себя обзор, редактуру, согласование и работу с активами. Бот остаётся входной точкой, генератором и каналом уведомлений.

## Product Role

Mini App должен закрыть четыре задачи:

1. Показать весь контент-конвейер в одном месте: идеи, черновики, согласование, публикация.
2. Сократить трение на длинных сценариях `/plan`, `/content`, `/carousel`, `/reels`, `/drafts`.
3. Дать UX-слой для редактора и UX-команды: карточки, статусы, версии, визуальные сравнения.
4. Подготовить основу для совместной работы через PR-like lifecycle внутри продукта: draft, review, approved, published, feedback.

## Primary Users

- Основатель / контент-стратег: смотрит план, выбирает идеи, утверждает материалы.
- Редактор: правит тексты, проверяет CTA, доводит до publish-ready состояния.
- Визуальный/UX-участник: проверяет storyboard, визуальные референсы и consistency.

## MVP Scope

### 1. Dashboard

- список последних draft'ов
- фильтры по формату: content, carousel, reels, threads
- фильтры по статусу: draft, in_review, approved, published
- быстрые действия: открыть, согласовать, вернуть на доработку

### 2. Draft Detail

- заголовок, формат, тема, дата, статус
- основной текст или структура слайдов/сценария
- история версий
- блок feedback: worked / missed
- комментарии редактора

### 3. Reels Workspace

- сценарий с таймкодами
- storyboard из 4 кадров
- открытие каждого кадра отдельно
- regenerate frame
- комментарий к кадру
- shot list и production notes

### 4. Plan Workspace

- недельный контент-план в виде карточек
- конвертация карточки в draft нужного формата
- видимость связи: plan item -> generated drafts

## UX Principles

1. Сначала обзор, потом детали.
2. Каждый draft должен быть открываемой сущностью, а не одноразовым сообщением.
3. Любое тяжёлое действие должно иметь прогресс и статус.
4. Для визуальных форматов пользователь должен сравнивать версии, а не терять предыдущую.
5. Бот и Mini App должны быть связаны deep link'ами: из Telegram-сообщения можно открыть нужный экран Mini App.

## Navigation Draft

Нижняя навигация MVP:

- Home
- Plan
- Drafts
- Reels
- Settings

## First Key Flows

### Flow A. Plan to Draft

1. Пользователь вызывает `/plan` в боте
2. Бот присылает план и кнопку открытия Mini App
3. В Mini App пользователь видит карточки плана
4. Нажимает `Create Draft`
5. Выбирает формат: Threads / Carousel / Reels / Telegram
6. Получает draft в статусе `draft`

### Flow B. Reels Review

1. Пользователь вызывает `/reels`
2. Бот генерирует сценарий и storyboard
3. Из сообщения открывается экран Reels Workspace
4. Пользователь смотрит 4 кадра, даёт замечание к конкретному кадру
5. Перегенерирует только нужный кадр
6. Согласует весь reels draft

### Flow C. Approval

1. Пользователь открывает draft
2. Видит статус, версию и замечания
3. Нажимает `Approve`
4. Статус меняется на `approved`
5. После публикации ставит `worked` или `missed`

## Data Requirements

Mini App требует устойчивые сущности:

- draft_id
- source flow
- format
- status
- feedback
- versions
- assets
- comments
- timestamps

## Technical Notes

- Первый этап можно строить без отдельного фронтенд-бэкенда: Telegram Mini App + текущий Python backend.
- Нужны HTTP endpoints для списка draft'ов, деталей draft'а, смены статуса, комментариев и версий.
- Нужны deep link'и из Telegram callbacks в конкретный экран Mini App.
- Авторизация должна опираться на Telegram init data.

## Design Deliverables For UX Team

На первый цикл нужны:

1. user flow map для `/plan`, `/drafts`, `/reels`
2. wireframes для Dashboard, Draft Detail, Reels Workspace
3. states: loading, empty, partial failure, approved, failed generation
4. interaction spec для regenerate, approve, feedback
5. visual direction для production-style workspace внутри Telegram

## Definition of Ready for Implementation

Фича считается готовой к разработке, когда есть:

- issue с acceptance criteria
- wireframe или Figma reference
- список backend data requirements
- решение, что остаётся в чат-боте, а что переходит в Mini App
