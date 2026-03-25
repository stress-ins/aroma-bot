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

В черновике {slide_count} слайдов. Сохрани это количество. Структура:
- Первый слайд — Hook: первая строка останавливает скролл. Факт, провокация или \
  узнаваемая ситуация. Не вопрос «А вы знали, что...».
- Средние слайды — раскрытие темы: проблема, механизм, инсайт, решение — в зависимости \
  от количества слайдов. Каждый слайд = одна мысль, конкретная ситуация из жизни.
- Последний слайд — CTA: человеческое приглашение, не рекламная фраза. CTA может быть разным, \
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
{slide_format}
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


def _build_editor_prompt(topic: str, raw_slides: str, slide_count: int = 6) -> str:
    slide_format = "\n".join(f"SLIDE{i}: [текст]" for i in range(1, slide_count + 1))
    return _EDITOR_PROMPT.format(
        brand_context=get_brand_context(),
        topic=topic,
        raw_slides=raw_slides,
        forbidden_phrases=_render_forbidden_phrases_block(),
        human_writing_rules=HUMAN_WRITING_RULES,
        slide_count=slide_count,
        slide_format=slide_format,
    )


def _sanitize_slide_text(text: str) -> str:
    result = enforce_policy(text, platform="instagram")
    return result.text.strip()


def edit_carousel_sync(raw_slides: list[str], topic: str, user_forbidden: list[str] | None = None) -> list[str]:
    from bot.services.claude_client import call_claude

    slide_count = len(raw_slides)
    raw_text = "\n".join(f"Слайд {i + 1}: {s}" for i, s in enumerate(raw_slides))
    prompt = _build_editor_prompt(topic=topic, raw_slides=raw_text, slide_count=slide_count)
    if user_forbidden:
        extra = "\n".join(f"- {p}" for p in user_forbidden)
        prompt += f"\n\nДополнительные запрещённые фразы (указаны пользователем):\n{extra}"

    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1400,
        context="carousel editor",
    )

    slides = [humanize(_sanitize_slide_text(item), "instagram") for item in _parse_slides(text, count=slide_count)]

    # Fallback: return originals if parsing failed
    return slides[:slide_count] if len(slides) >= max(4, slide_count - 1) else raw_slides


def _normalize_line(line: str) -> str:
    """Strip markdown bold/italic and leading punctuation from a line."""
    s = line.strip()
    # Remove **...** and __...__ wrappers at the start
    for marker in ("**", "__", "*", "_"):
        if s.startswith(marker):
            s = s[len(marker):]
    return s


def _parse_slides(text: str, count: int | None = None) -> list[str]:
    """Parse SLIDE1: ... SLIDE{N}: blocks, handling multi-line content
    and common Claude formatting variations (bold markers, spaces in numbers).

    When *count* is None (default), auto-detects how many slides the LLM returned.
    When *count* is given, parses exactly that many (backwards compat).
    """
    import re

    # Auto-detect max slide number if count not specified
    max_slide = count or 0
    if not count:
        for line in text.splitlines():
            stripped = _normalize_line(line).upper()
            m = re.match(r"SLIDE\s*(\d+)\s*:", stripped)
            if m:
                max_slide = max(max_slide, int(m.group(1)))
        max_slide = max(max_slide, 1)

    slots: dict[int, list[str]] = {}
    current: int | None = None

    for line in text.splitlines():
        stripped = _normalize_line(line)
        matched = False
        for i in range(1, max_slide + 1):
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
    for i in range(1, max_slide + 1):
        if i in slots:
            result.append(" ".join(slots[i]))
    return result
