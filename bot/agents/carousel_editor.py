from __future__ import annotations

import re

from config import settings
from bot.agents.platform_rules import HUMAN_WRITING_RULES, get_brand_context
from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.humanizer import humanize
from bot.services.policy_engine import enforce_policy, load_policy_config

_EDITOR_PROMPT = """\
{brand_context}

Ты — главред контента для Instagram с 10-летним опытом в нише wellbeing и психологии.
Цель карусели: человек дочитывает и думает «хочу попробовать» — пишет в ДМ или сохраняет.

Структура 6 слайдов:
SLIDE1 — Hook: первая строка останавливает скролл. Факт, провокация или \
  узнаваемая ситуация. Не вопрос «А вы знали, что...».
SLIDE2 — Проблема: конкретная ситуация из жизни, не абстракция. «Голова не \
  крутится до ночи» — да. «Стресс мешает нам жить» — нет.
SLIDE3 — Механизм: почему так происходит — просто, телесно, без науки и \
  без «парасимпатика активируется».
SLIDE4 — Инсайт: момент «ага». Переключение угла зрения. Не вывод, а открытие.
SLIDE5 — Решение: конкретная практика или шаг. Без обещаний «изменит всё».
SLIDE6 — CTA: человеческое приглашение, не рекламная фраза. CTA может быть разным, \
  но должен звучать по-русски и по-человечески. «Если хочешь попробовать, напиши», \
  «Если откликается, расскажу подробнее» — да. «Записывайся прямо сейчас!» — нет.

Критические правила:
- Максимум 5-6 строк на слайд, каждая строка ≤ 10 слов
- 1 мысль = 1 строка. Разговорный, живой язык — как говорит умная подруга, не как лектор
- Каждый следующий слайд должен логично продолжать предыдущий. Внутри одного слайда все детали должны описывать одну согласованную сцену. Человек должен читать и чувствовать, что его спокойно ведут дальше, а не кидают из мысли в мысль.
- Пиши мягко, понятно и по-человечески. Без жёстких формулировок, без "умничающего" тона, без ощущения, что текст старается звучать глубоко любой ценой.
- Лучше простая и ясная фраза, чем красивая, но странная. Если строка звучит неестественно в обычной речи, перепиши проще.
- Убери AI-штампы: «погружаясь в», «исследуя», «позволь себе», «мощный инструмент»
- Убери умные термины там, где можно сказать проще. \
  Плохо: «активация парасимпатики», «интеграция опыта», «ресурсное состояние». \
  Хорошо: «стало чуть легче», «голова не отключается», «не можешь уснуть»
- Никаких литературных метафор. Конкретность = слова из живого разговора, не из книги. \
  Плохо: «плечи в камне», «душа не отпускает», «тело как свинец». \
  Хорошо: «плечи не расслабляются», «не можешь уснуть», «голова не отключается»
- Не используй жёсткие, странные или неуклюжие фразы. \
  Плохо: "запах попадает быстрее мыслей", "нервная система не спорит", "аромат вскрывает женскую природу", \
  "тазовая волна", "занимать место без извинений", "боимся быть слишком много", \
  "на волне контроля", "минуя фильтры", "мы сжимаем живот", "надо быть острым", \
  "и тело и ум слышат это мгновенно", "чувствовать без стены". \
  Хорошо: "запах срабатывает очень быстро", "тело замечает аромат почти сразу", "у нас часто напряжено тело"
- Каждая строка слайда должна быть логически завершённой мыслью. Никаких оборванных фраз. \
  Плохо: «раскрыть женское», «надо быть острым». Хорошо: «расслабиться и почувствовать себя живой».
- Если описываешь проблему, уточняй, что именно не сработало. Не пиши размыто: «ничего не помогает». Покажи 1-2 конкретные попытки или симптома.
- Если пишешь про тело, избегай туманных слов вроде «сигнал», если не объясняешь, какой именно. Лучше сразу назвать ощущение или реакцию тела.
- Фразы вроде «у каждого свой аромат» или «земляная база» звучат незаконченно или искусственно. Пиши яснее: что именно дает аромат и в каком состоянии.
- В CTA не используй «ДМ». Пиши по-русски и естественно для автора: «напиши», «в личные сообщения», «расскажу подробнее».
- Не увеличивай текст — лучше сократи
- Слайд должен погружать читателя в ситуацию напрямую. Никакого мета-языка: не описывай сценарий, \
не проси представить, не комментируй текст изнутри. Пиши так, будто читатель уже внутри ситуации.
- Логическая целостность: вся сцена в одном слайде должна быть физически возможной. Если описываешь \
ощущение — убедись, что обстоятельства позволяют его испытать. Перечитай сцену глазами читателя \
и проверь: нет ли противоречий?
- Каждый слайд описывает одну конкретную микро-ситуацию. Не смешивай разные места и времена в одном слайде.
- Тон: спокойный, тёплый, живой. Без эзотерики, пафоса, инфоцыганства
- Слайды должны быть приятными на слух. Не руби фразы ради эффекта, не делай текст нарочито "инстаграмным".
- Ориентир по тону: понятно, мягко, логично, как в хорошем объяснении от живого человека.
- Пиши "каждый человек", а не "каждое тело". Тело — объект, а человек — субъект.
- Каждое сравнение должно логически относиться к теме. \
  Плохо: «это как отпечаток пальца, но для расслабления» (если речь не о расслаблении). \
  Хорошо: «это как отпечаток пальца, только не на коже, а в памяти».
- Не используй грубые медицинские сравнения. \
  Плохо: «таблетка вслепую», «укол наугад». \
  Хорошо: «подбирать наугад», «пробовать по списку».
- Каждое предложение должно быть ясным и самодостаточным. Если пишешь «экономит время» — уточни, время на что именно. Если пишешь «и попытки» — попытки чего. Неконкретные окончания запрещены.
- Вводная фраза должна быть понятна с первого прочтения. \
  Плохо: «вы пробовали лаванду и не поняли шума» (непонятно, какого шума). \
  Хорошо: «вы пробовали лаванду и не почувствовали эффекта».
- Не используй эти фразы и их близкие варианты:
{forbidden_phrases}

{human_writing_rules}

Тема карусели: {topic}

Черновик слайдов:
{raw_slides}

Верни строго в формате (ничего кроме этого):
SLIDE1: [текст]
SLIDE2: [текст]
SLIDE3: [текст]
SLIDE4: [текст]
SLIDE5: [текст]
SLIDE6: [текст]
"""


def _forbidden_phrases() -> list[str]:
    cfg = load_policy_config()
    bs = get_brand_settings_cached()
    seen: set[str] = set()
    result: list[str] = []
    for phrase in [*cfg.forbidden_phrases, *bs.forbidden_phrases, *getattr(settings, "carousel_forbidden_phrases_list", [])]:
        value = str(phrase).strip()
        lowered = value.lower()
        if not value or lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return result


def _render_forbidden_phrases_block() -> str:
    return "\n".join(f"- {item}" for item in _forbidden_phrases())


def _build_editor_prompt(topic: str, raw_slides: str) -> str:
    return _EDITOR_PROMPT.format(
        brand_context=get_brand_context(),
        topic=topic,
        raw_slides=raw_slides,
        forbidden_phrases=_render_forbidden_phrases_block(),
        human_writing_rules=HUMAN_WRITING_RULES,
    )


def _sanitize_slide_text(text: str) -> str:
    result = enforce_policy(text, platform="instagram")
    return result.text.strip()


def edit_carousel_sync(raw_slides: list[str], topic: str, user_forbidden: list[str] | None = None) -> list[str]:
    from bot.services.claude_client import call_claude

    raw_text = "\n".join(f"Слайд {i + 1}: {s}" for i, s in enumerate(raw_slides))
    prompt = _build_editor_prompt(topic=topic, raw_slides=raw_text)
    if user_forbidden:
        extra = "\n".join(f"- {p}" for p in user_forbidden)
        prompt += f"\n\nДополнительные запрещённые фразы (указаны пользователем):\n{extra}"

    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1400,
        context="carousel editor",
    )

    slides = [humanize(_sanitize_slide_text(item), "instagram") for item in _parse_slides(text, count=6)]

    # Fallback: return originals if parsing failed
    return slides[:6] if len(slides) >= 4 else raw_slides


def _normalize_line(line: str) -> str:
    """Strip markdown bold/italic and leading punctuation from a line."""
    s = line.strip()
    # Remove **...** and __...__ wrappers at the start
    for marker in ("**", "__", "*", "_"):
        if s.startswith(marker):
            s = s[len(marker):]
    return s


def _parse_slides(text: str, count: int = 6) -> list[str]:
    """Parse SLIDE1: ... SLIDE{count}: blocks, handling multi-line content
    and common Claude formatting variations (bold markers, spaces in numbers)."""
    import re
    slots: dict[int, list[str]] = {}
    current: int | None = None

    for line in text.splitlines():
        stripped = _normalize_line(line)
        matched = False
        for i in range(1, count + 1):
            # Match SLIDE1: or SLIDE 1: (with optional space)
            prefix = f"SLIDE{i}:"
            prefix_spaced = f"SLIDE {i}:"
            if stripped.upper().startswith(prefix.upper()) or \
               stripped.upper().startswith(prefix_spaced.upper()):
                current = i
                slots[i] = []
                plen = len(prefix_spaced) if stripped.upper().startswith(prefix_spaced.upper()) else len(prefix)
                after = stripped[plen:].strip().lstrip("*_").rstrip("*_").strip()
                if after:
                    slots[i].append(after)
                matched = True
                break
        if not matched and current is not None:
            # Stop accumulating at IMG_PROMPT or empty separator between slides
            if stripped.upper().startswith("IMG_PROMPT"):
                current = None
            elif stripped:
                slots[current].append(stripped)

    result = []
    for i in range(1, count + 1):
        if i in slots:
            result.append(" ".join(slots[i]))
    return result
