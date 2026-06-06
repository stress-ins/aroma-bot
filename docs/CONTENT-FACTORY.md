# Content Factory — состав агентов и промптов

Справочник, **читать по необходимости** (не грузится в каждую сессию). Источник истины — сам каталог `bot/agents/` (`ls bot/agents/*.py` → ~47 агентов, `bot/agents/prompts/*.py` → 7 промпт-файлов). Список ниже — навигационная карта по ролям; при расхождении с каталогом верить каталогу.

## Состав по ролям

**Генерация:** content.py (orchestrator), creative_team.py (editor), planner.py, hashtag_recommender.py, platform_optimizer.py, tone_adapter.py, repurpose_agent.py

**Видео:** youtube_script_agent.py, youtube_metadata_agent.py, broll_director.py, reels_agent.py, video_coach.py

**Карусели:** carousel_editor.py, carousel_editorial.py, carousel_preview_agent.py, carousel_export_agent.py, image_prompt_engineer.py, image_prompt_router.py, nanobanana_prompt_expert.py

**Серии:** series_orchestrator.py, series_writer.py, series_coherence.py, thread_scorer.py, threads_replies.py

**Quality gates:** quality_evaluator.py (порог 0.65), brand_guardian.py, medical_reviewer.py, ux_reviewer.py

**Доменные эксперты:** aromatherapy_expert.py, wellness_expert.py, bodywork_expert.py, sound_healing_expert.py

**Рекомендации:** recommendation_agent.py, massage_recommendation_agent.py, protocol_recommendation_agent.py

**Промпты:** content_prompts.py, reels_prompts.py, youtube_prompts.py, series_prompts.py, tone_prompts.py, hashtag_prompts.py

## Codex-фокус при изменении Content Factory

При изменениях в `bot/agents/`, `bot/agents/prompts/`, `bot/services/miniapp_references/` запускать adversarial-review с фокусом:

```
/codex:adversarial-review --base main focus on:
1. Prompt injection vectors — user input flowing into LLM prompts
2. Quality threshold bypass — can weak content pass quality_evaluator?
3. Brand voice drift — are prompts consistent with brand_guardian rules?
4. Retry/fallback behaviour — what happens on LLM failure? Silent data loss?
5. Medical safety — contraindications, healing claims, NAHA/IFA compliance
6. Cross-reference integrity — slug resolution, missing cards, stale references
```
