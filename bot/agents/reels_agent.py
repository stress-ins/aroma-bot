from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.agents.content import _HUMAN_WRITING_RULES
from bot.services.claude_client import call_claude
from bot.services.brand_settings_store import get_brand_settings_cached
from bot.services.humanizer import humanize

logger = logging.getLogger(__name__)

from bot.agents.prompts.reels_prompts import (
    TOPICS_PROMPT as _TOPICS_PROMPT,
    SCENARIO_PROMPT as _SCENARIO_PROMPT,
    DIRECTOR_PROMPT as _DIRECTOR_PROMPT,
    DRAFT_PROMPT as _DRAFT_PROMPT,
    FRAMES_PROMPT as _FRAMES_PROMPT,
    CAPTION_PROMPT as _CAPTION_PROMPT,
)

_REFERENCE_CONTEXT_MAX_CHARS = 1800

GOAL_LABELS: dict[str, str] = {
    "trust": "доверие и экспертность",
    "sales": "продажи и конверсия",
    "reach": "охват и виральность",
    "community": "сообщество и вовлечение",
    "education": "обучение и польза",
}

EMOTION_LABELS: dict[str, str] = {
    "calm": "спокойствие",
    "inspiration": "вдохновение",
    "curiosity": "любопытство",
    "joy": "радость",
    "trust": "доверие",
    "nostalgia": "ностальгия",
}


@dataclass
class StoryboardFrame:
    timecode: str
    scene: str
    angle: str
    gemini_prompt: str


@dataclass
class ReelsV2Draft:
    concept: str
    hook: str
    scenario: str
    caption: str
    music_mood: str
    production_guide: dict | None = None


@dataclass
class FramePromptV2:
    timecode: str
    overlay_text: str
    image_prompt: str


def _parse_storyboard(raw: str) -> list[StoryboardFrame]:
    normalized_lines: list[str] = []
    for line in raw.splitlines():
        probe = line.strip()
        probe = probe.removeprefix("- ").strip()
        probe = probe.replace("**", "").replace("__", "").strip()
        normalized_lines.append(probe)

    frames: list[StoryboardFrame] = []
    for i in range(1, 5):
        timecode = scene = angle = prompt = ""
        for line in normalized_lines:
            if line.startswith(f"КАДР{i}_ТАЙМКОД:"):
                timecode = line.split(":", 1)[1].strip()
            elif line.startswith(f"КАДР{i}_СЦЕНА:"):
                scene = line.split(":", 1)[1].strip()
            elif line.startswith(f"КАДР{i}_РАКУРС:"):
                angle = line.split(":", 1)[1].strip()
            elif line.startswith(f"КАДР{i}_ПРОМПТ:"):
                prompt = line.split(":", 1)[1].strip()
        if timecode or scene:
            frames.append(StoryboardFrame(
                timecode=timecode, scene=scene, angle=angle, gemini_prompt=prompt
            ))
    return frames


def generate_reels_topics_sync(trends_text: str) -> list[str]:
    from cache.store import cache
    bs = get_brand_settings_cached()
    prompt = _TOPICS_PROMPT.format(brand_context=bs.brand_voice, trends_text=trends_text)
    try:
        text = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            context="reels topics",
        )
        topics: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line and line[0].isdigit() and ". " in line:
                topics.append(line.split(". ", 1)[1].strip())
        topics = topics[:7]
        if topics:
            cache.set("topics:reels", topics)
        return topics
    except Exception:
        logger.warning("generate_reels_topics_sync failed, trying cache", exc_info=True)
        return cache.get("topics:reels") or []


def _render_reference_context_block(reference_context: str) -> str:
    text = str(reference_context or "").strip()
    if not text:
        return ""
    bounded = text[:_REFERENCE_CONTEXT_MAX_CHARS].rstrip()
    return (
        "\nДанные из нашего справочника (используй для точности описаний и формулировок):\n"
        + bounded
        + "\n"
    )


def generate_reels_scenario_sync(topic: str, reference_context: str = "") -> str:
    bs = get_brand_settings_cached()
    forbidden_block = "\n".join(f"- {p}" for p in bs.forbidden_phrases) if bs.forbidden_phrases else ""
    prompt = _SCENARIO_PROMPT.format(
        brand_context=bs.brand_voice,
        reference_context_block=_render_reference_context_block(reference_context),
        topic=topic,
        forbidden_phrases=forbidden_block,
        human_writing_rules=_HUMAN_WRITING_RULES,
    )
    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1600,
        context="reels scenario",
    )
    return humanize(text)


def generate_reels_director_sync(topic: str, script: str) -> list[StoryboardFrame]:
    """Director agent: breaks the script into 4 storyboard frames with Gemini prompts."""
    prompt = _DIRECTOR_PROMPT.format(topic=topic, script=script)
    last_raw = ""
    frames: list[StoryboardFrame] = []

    for attempt in range(2):
        last_raw = call_claude(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1400,
            context="reels director",
        )
        frames = _parse_storyboard(last_raw)
        if len(frames) >= 4:
            break
        logger.warning("Reels director parse returned %d frames on attempt %d", len(frames), attempt + 1)

    if not frames:
        logger.warning("Reels director fallback: returning 0 parsed frames")
        if last_raw:
            logger.warning("Reels director raw response preview: %s", last_raw[:800])
        return []

    # Enhance each frame's gemini_prompt with Image Prompt Engineer
    for frame in frames[:4]:
        if frame.gemini_prompt:
            frame.gemini_prompt = _enhance_frame_prompt(frame.gemini_prompt)

    return frames[:4]


def _parse_draft(raw: str) -> ReelsV2Draft:
    """Parse structured Claude response into ReelsV2Draft.

    Handles both plain-text (CONCEPT:) and markdown (**CONCEPT:**) formats.
    """
    concept = hook = caption = music_mood = ""
    in_scenario = False
    scenario_buf: list[str] = []

    for line in raw.splitlines():
        stripped = line.strip()
        # Strip markdown bold/heading markers: **CONCEPT:** → CONCEPT:
        clean = stripped.lstrip("#").strip().replace("**", "").strip()

        if clean.startswith("CONCEPT:"):
            concept = clean[len("CONCEPT:"):].strip()
            in_scenario = False
        elif clean.startswith("HOOK:") or clean.startswith("HOOK "):
            hook = clean.split(":", 1)[1].strip() if ":" in clean else ""
            in_scenario = False
        elif clean.startswith("SCENARIO:") or clean == "SCENARIO":
            in_scenario = True
            tail = clean[len("SCENARIO:"):].strip() if ":" in clean else ""
            if tail:
                scenario_buf.append(tail)
        elif clean.startswith("CAPTION:"):
            in_scenario = False
            caption = clean[len("CAPTION:"):].strip()
        elif clean.startswith("MUSIC_MOOD:") or clean.startswith("MUSIC MOOD:"):
            in_scenario = False
            music_mood = clean.split(":", 1)[1].strip() if ":" in clean else ""
        elif in_scenario:
            scenario_buf.append(line)

    # Fallback: regex extraction if concept still empty
    if not concept:
        import re
        m = re.search(r'CONCEPT:\s*(.+)', raw, re.IGNORECASE)
        if m:
            concept = m.group(1).strip().strip("*").strip()

    return ReelsV2Draft(
        concept=concept,
        hook=hook,
        scenario="\n".join(scenario_buf).strip(),
        caption=caption,
        music_mood=music_mood,
    )


def _parse_frame_prompts(raw: str, n_frames: int = 4) -> list[FramePromptV2]:
    """Parse structured FRAME1_TIMECODE / FRAME1_OVERLAY / FRAME1_PROMPT blocks."""
    frames: list[FramePromptV2] = []
    for i in range(1, n_frames + 1):
        timecode = overlay = prompt = ""
        for line in raw.splitlines():
            # Strip markdown bold/heading markers
            clean = line.strip().lstrip("#").strip().replace("**", "").strip()
            key_tc = f"FRAME{i}_TIMECODE:"
            key_ov = f"FRAME{i}_OVERLAY:"
            key_pr = f"FRAME{i}_PROMPT:"
            if clean.startswith(key_tc):
                timecode = clean[len(key_tc):].strip()
            elif clean.startswith(key_ov):
                overlay = clean[len(key_ov):].strip()
            elif clean.startswith(key_pr):
                prompt = clean[len(key_pr):].strip()
        if timecode or overlay or prompt:
            frames.append(FramePromptV2(timecode=timecode, overlay_text=overlay, image_prompt=prompt))
    return frames


def generate_reels_v2_draft_sync(
    topic: str,
    goal: str = "trust",
    emotion: str = "calm",
    blend_context: dict | None = None,
) -> ReelsV2Draft:
    """Generate a v2 reels draft: concept, hook, scenario, caption, music mood."""
    bs = get_brand_settings_cached()
    forbidden_block = (
        "НЕ использовать следующие фразы:\n"
        + "\n".join(f"- {p}" for p in bs.forbidden_phrases)
        if bs.forbidden_phrases
        else ""
    )
    goal_label = GOAL_LABELS.get(goal, goal)
    emotion_label = EMOTION_LABELS.get(emotion, emotion)
    blend_block = ""
    if blend_context:
        from bot.agents.blend_content_context import build_blend_reels_concept
        blend_block = "\nКонтекст смеси:\n" + build_blend_reels_concept(blend_context) + "\n"
    prompt = _DRAFT_PROMPT.format(
        brand_context=bs.brand_voice,
        topic=topic + ("\n" + blend_block if blend_block else ""),
        goal_label=goal_label,
        emotion_label=emotion_label,
        forbidden_block=forbidden_block,
    )
    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1800,
        context="reels draft",
    )
    draft = _parse_draft(text)

    # Video Coach: attach production guidance (non-blocking, never breaks pipeline)
    try:
        from bot.agents.video_coach import review_scenario_sync

        draft.production_guide = review_scenario_sync(
            scenario_text=draft.scenario,
            target_duration=30.0,
        )
    except Exception:
        logger.warning("Video Coach failed, skipping production guide", exc_info=True)

    return draft


def _enhance_frame_prompt(raw_prompt: str, aspect_ratio: str = "9:16") -> str:
    """Enhance a frame prompt using the Image Prompt Engineer agent.

    Falls back to the original prompt if the agent fails.
    """
    try:
        from bot.agents.image_prompt_engineer import craft_image_prompt_sync

        result = craft_image_prompt_sync(
            scene_description=raw_prompt,
            style="botanical_wellness",
            aspect_ratio=aspect_ratio,
        )
        return result.get("prompt", raw_prompt)
    except Exception:
        logger.warning("Image Prompt Engineer fallback for frame prompt", exc_info=True)
        return raw_prompt


def generate_frame_prompts_sync(
    topic: str,
    scenario: str,
    n_frames: int = 4,
    blend_context: dict | None = None,
) -> list[FramePromptV2]:
    """Generate per-frame image prompts and overlay texts."""
    blend_visual_block = ""
    if blend_context:
        from bot.agents.blend_content_context import mood_to_visual_directive
        visual = mood_to_visual_directive(blend_context.get("profile", {}))
        oil_names = [o.get("name_en", "") for o in blend_context.get("oils", []) if o.get("name_en")]
        if visual:
            blend_visual_block = f"\nBlend visual mood: {visual}\n"
        if oil_names:
            blend_visual_block += f"Featured botanicals: {', '.join(oil_names)}\n"
    prompt = _FRAMES_PROMPT.format(
        topic=topic,
        scenario=scenario[:2000] + ("\n" + blend_visual_block if blend_visual_block else ""),
        n_frames=n_frames,
    )
    text = call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        context="reels frame_prompts",
    )
    frames = _parse_frame_prompts(text, n_frames=n_frames)

    # Enhance each frame prompt with Image Prompt Engineer
    for frame in frames:
        if frame.image_prompt:
            frame.image_prompt = _enhance_frame_prompt(frame.image_prompt)

    return frames


def generate_reels_v2_caption_sync(
    topic: str,
    concept: str,
    scenario: str,
) -> str:
    """Regenerate caption for a v2 reels draft."""
    bs = get_brand_settings_cached()
    forbidden_block = (
        "НЕ использовать следующие фразы:\n"
        + "\n".join(f"- {p}" for p in bs.forbidden_phrases)
        if bs.forbidden_phrases
        else ""
    )
    prompt = _CAPTION_PROMPT.format(
        brand_context=bs.brand_voice,
        topic=topic,
        concept=concept,
        scenario_preview=scenario[:800],
        forbidden_block=forbidden_block,
    )
    return call_claude(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        context="reels caption",
    )
