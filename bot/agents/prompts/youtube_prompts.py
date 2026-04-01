"""Prompt templates for the YouTube script agent (bot/agents/youtube_script_agent.py).

All constants are plain str.format()-style templates; the calling code
in youtube_script_agent.py fills in the placeholders.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared rules for all YouTube formats
# ---------------------------------------------------------------------------

_YOUTUBE_SHARED_RULES = """\
ОБЯЗАТЕЛЬНЫЕ ОГРАНИЧЕНИЯ (для всех форматов):
- Формат видео: горизонтальный 16:9 (YouTube standard).
- Язык: русский. Тон: экспертный, но доступный — как лектор TED, а не учебник.
- Каждая секция должна быть логически завершена — никаких оборванных мыслей.
- НЕ использовать: дымящийся ладан, горящие смолы, капли масла в воде.
- Масло на экране: каплю на ладонь → растереть → вдыхать. Либо диффузор.
- В каждой секции обязательно указать [B-ROLL: описание] — подсказку для визуальной вставки.
- B-ROLL должен быть конкретным: не «красивые кадры природы», а «крупный план: капли росы на лепестках лаванды, утренний свет».
"""

# ---------------------------------------------------------------------------
# Topic generation
# ---------------------------------------------------------------------------

TOPICS_PROMPT = """\
{brand_context}

Предложи 7 тем для YouTube-видео ({subformat_label}, {duration_label}).

Тренды для вдохновения:
{trends_text}

Требования к темам:
- Чёткая обещанная ценность для зрителя (чему научится, что узнает)
- Потенциал для удержания (retention) — тема должна раскрываться постепенно
- SEO-потенциал: тема формулируется как поисковый запрос или ответ на вопрос
- Подходит для формата {subformat_label}

Верни строго нумерованный список без пояснений:
1. ...
7. ...
"""

# ---------------------------------------------------------------------------
# Talking Head script
# ---------------------------------------------------------------------------

TALKING_HEAD_PROMPT = """\
{brand_context}
{reference_context_block}

Напиши детальный сценарий YouTube-видео в формате «Talking Head» (один спикер перед камерой).
Тема: «{topic}»
Цель: {goal_label}
Желаемая эмоция зрителя: {emotion_label}
Целевая длительность: {duration_target} минут.

Структура сценария — СТРОГО в этом формате:

TITLE: [заголовок видео, ≤70 символов, SEO-оптимизированный]

SECTION: HOOK
TIMECODE: 0:00–0:30
SPEAKER_TEXT: [дословный текст спикера — провокационный вопрос, статистика или миф]
SCREEN_TEXT: [ключевая фраза для оверлея, ≤6 слов]
ENERGY: high
[B-ROLL: описание визуальной вставки, 3-5 сек]

SECTION: INTRO
TIMECODE: 0:30–1:30
SPEAKER_TEXT: [представление, обещание ценности, краткое оглавление видео]
SCREEN_TEXT: [пункты оглавления]
ENERGY: medium
[B-ROLL: описание]

SECTION: MAIN_1
TIMECODE: 1:30–{section_end_1}
LABEL: [название секции — что зритель узнает]
SPEAKER_TEXT: [основной тезис + примеры + практическое применение]
SCREEN_TEXT: [ключевой факт/цифра]
ENERGY: medium
[B-ROLL: описание визуала к теме секции]

SECTION: MAIN_2
TIMECODE: {section_end_1}–{section_end_2}
LABEL: [название секции]
SPEAKER_TEXT: [углубление / практика / неожиданный поворот]
SCREEN_TEXT: [ключевой факт/цифра]
ENERGY: medium-high
[B-ROLL: описание]

SECTION: MAIN_3
TIMECODE: {section_end_2}–{section_end_3}
LABEL: [название секции]
SPEAKER_TEXT: [продвинутый уровень / личный опыт / кейс]
SCREEN_TEXT: [ключевой факт/цифра]
ENERGY: high
[B-ROLL: описание]

SECTION: RECAP
TIMECODE: {section_end_3}–{recap_end}
SPEAKER_TEXT: [3 ключевых вывода — резюме видео]
SCREEN_TEXT: [3 пункта списком]
ENERGY: medium
[B-ROLL: описание]

SECTION: CTA
TIMECODE: {recap_end}–{total_end}
SPEAKER_TEXT: [призыв: подписка, комментарий, следующее видео]
SCREEN_TEXT: [«Подпишись» / ссылка]
ENERGY: high
[B-ROLL: описание]

MUSIC_MOOD: [настроение фоновой музыки — темп, инструменты, атмосфера]

{forbidden_block}
{human_writing_rules}
{_youtube_shared_rules}
"""

# ---------------------------------------------------------------------------
# Listicle / Top-N script
# ---------------------------------------------------------------------------

LISTICLE_PROMPT = """\
{brand_context}
{reference_context_block}

Напиши детальный сценарий YouTube-видео в формате «Listicle / Top-N» (список).
Тема: «{topic}»
Цель: {goal_label}
Желаемая эмоция зрителя: {emotion_label}
Целевая длительность: {duration_target} минут.
Количество пунктов: {item_count}

Структура сценария — СТРОГО в этом формате:

TITLE: [заголовок видео, ≤70 символов, с числом в заголовке]

SECTION: HOOK
TIMECODE: 0:00–0:30
SPEAKER_TEXT: [«N вещей, которые...» / «Вы точно не знали, что...»]
SCREEN_TEXT: [тизер списка]
ENERGY: high
[B-ROLL: описание]

SECTION: INTRO
TIMECODE: 0:30–1:00
SPEAKER_TEXT: [контекст, почему это важно, что зритель получит]
SCREEN_TEXT: [ключевая фраза]
ENERGY: medium
[B-ROLL: описание]

(Повтори блок ITEM для каждого пункта от 1 до {item_count}:)

SECTION: ITEM_{n}
TIMECODE: {start}–{end}
LABEL: [пункт #{n}: название]
SPEAKER_TEXT: [факт → объяснение «почему это работает» → практический пример]
SCREEN_TEXT: [название пункта + ключевой факт]
ENERGY: {energy}
[B-ROLL: описание визуала к конкретному пункту]

SECTION: BONUS
TIMECODE: ...
LABEL: [Бонус: неожиданный пункт сверх обещанного]
SPEAKER_TEXT: [«А вот ещё кое-что, о чём мало кто знает...»]
SCREEN_TEXT: [бонусный факт]
ENERGY: high
[B-ROLL: описание]

SECTION: RECAP
TIMECODE: ...
SPEAKER_TEXT: [краткий итог всех пунктов]
SCREEN_TEXT: [список всех пунктов кратко]
ENERGY: medium
[B-ROLL: описание]

SECTION: CTA
TIMECODE: ...
SPEAKER_TEXT: [призыв к действию]
SCREEN_TEXT: [«Подпишись»]
ENERGY: high
[B-ROLL: описание]

MUSIC_MOOD: [настроение фоновой музыки]

{forbidden_block}
{human_writing_rules}
{_youtube_shared_rules}
"""

# ---------------------------------------------------------------------------
# Podcast / Interview script
# ---------------------------------------------------------------------------

PODCAST_PROMPT = """\
{brand_context}
{reference_context_block}

Напиши детальный сценарий YouTube-видео в формате «Подкаст / Интервью» (два спикера).
Тема: «{topic}»
Цель: {goal_label}
Желаемая эмоция зрителя: {emotion_label}
Целевая длительность: {duration_target} минут.
Количество основных вопросов: {question_count}

Описание гостя (если есть): {guest_description}

Структура сценария — СТРОГО в этом формате:

TITLE: [заголовок видео, ≤70 символов]
GUEST_NAME: [имя и титул гостя]
GUEST_EXPERTISE: [область экспертизы гостя, 1-2 предложения]

SECTION: COLD_OPEN
TIMECODE: 0:00–0:30
SPEAKER_TEXT: [яркая цитата гостя из середины интервью — тизер]
SCREEN_TEXT: [цитата крупно]
ENERGY: high
[B-ROLL: описание]

SECTION: INTRO
TIMECODE: 0:30–2:00
HOST_TEXT: [ведущий представляет гостя, его экспертизу, тему разговора]
SCREEN_TEXT: [имя гостя + титул]
ENERGY: medium
[B-ROLL: описание]

(Повтори блок QUESTION для каждого вопроса от 1 до {question_count}:)

SECTION: QUESTION_{n}
TIMECODE: {start}–{end}
LABEL: [тема вопроса]
HOST_TEXT: [вопрос ведущего]
GUEST_TALKING_POINTS:
- [ожидаемый тезис 1]
- [ожидаемый тезис 2]
- [ожидаемый тезис 3]
FOLLOW_UP: [уточняющий вопрос ведущего]
ENERGY: {energy}
[B-ROLL: описание визуала к теме вопроса]

SECTION: LIGHTNING_ROUND
TIMECODE: ...
HOST_TEXT: [«Блиц-раунд — быстрые вопросы, быстрые ответы»]
QUESTIONS:
- [быстрый вопрос 1]
- [быстрый вопрос 2]
- [быстрый вопрос 3]
- [быстрый вопрос 4]
- [быстрый вопрос 5]
ENERGY: high
[B-ROLL: описание]

SECTION: OUTRO
TIMECODE: ...
HOST_TEXT: [благодарность гостю, ключевой вывод, призыв]
SCREEN_TEXT: [контакты гостя / ссылки]
ENERGY: medium
[B-ROLL: описание]

SECTION: CTA
TIMECODE: ...
HOST_TEXT: [подписка, комментарий, следующее видео]
SCREEN_TEXT: [«Подпишись»]
ENERGY: high
[B-ROLL: описание]

MUSIC_MOOD: [настроение фоновой музыки]

{forbidden_block}
{human_writing_rules}
{_youtube_shared_rules}
"""

# ---------------------------------------------------------------------------
# B-Roll Director prompt — extracts B-Roll Map from a finished scenario
# ---------------------------------------------------------------------------

BROLL_DIRECTOR_PROMPT = """\
Ты — B-Roll режиссёр для YouTube-видео. Тебе дан готовый сценарий.
Твоя задача: извлечь все маркеры [B-ROLL: ...] и для каждого создать детальное описание вставки.

СЦЕНАРИЙ:
{scenario}

Контекст бренда: регуляция нервной системы через сенсорные практики (ароматерапия, медитации, гонг).
Визуальный стиль: терракота, беж, шалфей; природные текстуры, травы, свечи, руки, мягкий свет.
Формат: горизонтальный 16:9.

Верни ответ строго как JSON-массив (без markdown-обёртки, без текста до/после):

[
  {{
    "section": "имя секции из сценария",
    "timestamp": "1:45",
    "duration": 4,
    "description": "детальное описание визуала на русском",
    "source_type": "stock_photo",
    "search_keywords": ["keyword1", "keyword2", "keyword3"],
    "camera_motion": "slow_zoom_in",
    "mood": "calm"
  }}
]

Допустимые source_type: stock_photo, stock_video, generated_image.
Допустимые camera_motion: slow_zoom_in, pan_left, pan_right, static, parallax, slow_zoom_out.
Допустимые mood: calm, dynamic, educational, warm, mysterious.
Верни ТОЛЬКО валидный JSON-массив, ничего больше.
"""

# ---------------------------------------------------------------------------
# YouTube Metadata prompt — title, description, tags after montage
# ---------------------------------------------------------------------------

METADATA_PROMPT = """\
Ты — SEO-специалист для YouTube-канала по ароматерапии и sound healing.
Тебе дан сценарий видео и реальные таймкоды секций (из финального монтажа).

СЦЕНАРИЙ:
{scenario_preview}

РЕАЛЬНЫЕ ТАЙМКОДЫ СЕКЦИЙ:
{timecodes_block}

ДЛИТЕЛЬНОСТЬ ВИДЕО: {total_duration}

Верни ответ строго как JSON (без markdown-обёртки, без текста до/после):

{{
  "title": "заголовок ≤70 символов, SEO-оптимизированный, с ключевым словом в начале",
  "description": "полное описание видео включая таймкоды, хэштеги и ссылки (multiline string с \\n)",
  "tags": ["keyword1", "keyword2", "до 30 тегов"],
  "category_id": 26,
  "chapters": [
    {{"time": 0, "title": "Intro"}},
    {{"time": 90, "title": "Основная часть"}}
  ]
}}

Правила:
- description включает: 2-3 предложения, таймкоды (HH:MM:SS — Название), ссылки-placeholder, 5-8 хэштегов
- category_id: 22=People&Blogs, 26=Howto&Style, 27=Education
- chapters.time — в секундах от начала видео
- Верни ТОЛЬКО валидный JSON, ничего больше
"""

# ---------------------------------------------------------------------------
# Thumbnail prompt generation
# ---------------------------------------------------------------------------

THUMBNAIL_PROMPT = """\
Ты — дизайнер обложек YouTube. Создай промпт для генерации обложки видео.

ТЕМА ВИДЕО: {topic}
ЗАГОЛОВОК: {title}
ФОРМАТ: {subformat}
ЭМОЦИЯ: {emotion}

Создай промпт на АНГЛИЙСКОМ для генерации изображения 1280×720 (16:9).

Правила обложки YouTube:
- Яркие, контрастные цвета — обложка должна выделяться в ленте
- Минимум текста (2-4 слова максимум, крупным шрифтом)
- Один главный визуальный элемент в центре
- Brand palette: terracotta, warm beige, sage green
- NO faces unless explicitly requested
- NO small details — обложка должна читаться на мобильных устройствах
- Composition: main subject occupies 60%+ of frame

Ответь строго:
PROMPT: [English prompt for image generation, 1280x720 landscape, YouTube thumbnail style]
TEXT_OVERLAY: [2-4 слова для наложения текстом поверх — на русском]
"""

THUMBNAIL_REVISION_PROMPT = """\
Предыдущий промпт для обложки:
{previous_prompt}

Замечание пользователя: {revision_note}

Создай НОВЫЙ промпт, который учитывает замечание. Сохрани формат 1280×720, стиль YouTube thumbnail.

Ответь строго:
PROMPT: [обновлённый English prompt]
TEXT_OVERLAY: [2-4 слова для текста поверх — на русском]
"""

THUMBNAIL_PHOTO_BASED_PROMPT = """\
Пользователь загрузил фотографию для обложки YouTube-видео.
Нужно создать промпт для img2img обработки.

ТЕМА ВИДЕО: {topic}
ЗАГОЛОВОК: {title}
ЭМОЦИЯ: {emotion}

Создай промпт для img2img модели (на основе загруженной фотографии):
- Кадрирование под 16:9
- Усилить яркость и контраст для YouTube
- Добавить атмосферу по теме видео
- Brand palette: terracotta, warm beige, sage green
- Сохранить основной объект фотографии

Ответь строго:
PROMPT: [English img2img prompt]
TEXT_OVERLAY: [2-4 слова для текста поверх — на русском]
"""
