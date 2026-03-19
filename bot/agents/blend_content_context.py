"""Blend Content Context — utilities for enriching content prompts with blend data.

When a user creates content from a blend, these functions build structured
context blocks for each agent in the pipeline (strategist, writer,
art-director, carousel narrator, reels concept).
"""
from __future__ import annotations


def build_blend_strategist_block(bc: dict) -> str:
    """For the strategist: profile, tags, brief, expert_note."""
    parts: list[str] = []
    if bc.get("title"):
        parts.append(f"Смесь: {bc['title']}")
    if bc.get("brief"):
        parts.append(f"Задача: {bc['brief']}")
    profile = bc.get("profile", {})
    if profile:
        profile_parts = [f"{k} {v}%" for k, v in profile.items() if v]
        if profile_parts:
            parts.append(f"Профиль: {', '.join(profile_parts)}")
    oils = bc.get("oils", [])
    if oils:
        oil_names = [o.get("name_ru", "") for o in oils if o.get("name_ru")]
        if oil_names:
            parts.append(f"Масла: {', '.join(oil_names)}")
    if bc.get("tags"):
        parts.append(f"Теги: {', '.join(bc['tags'])}")
    if bc.get("expert_note"):
        parts.append(f"Синергия: {bc['expert_note'][:300]}")
    return "\n".join(parts)


def build_blend_writer_block(bc: dict, oil_cards: list[dict] | None = None) -> str:
    """For the writer: oils with roles, properties from DB, expert_note, application_guide."""
    parts: list[str] = []
    if bc.get("title"):
        parts.append(f"Смесь: {bc['title']}")

    oils = bc.get("oils", [])
    oil_card_map = {}
    if oil_cards:
        for card in oil_cards:
            name = (card.get("name") or "").lower()
            name_en = (card.get("name_en") or "").lower()
            if name:
                oil_card_map[name] = card
            if name_en:
                oil_card_map[name_en] = card

    if oils:
        parts.append("Состав:")
        for o in oils:
            line = f"  - {o.get('name_ru', '?')} ({o.get('drops', 0)} кап.)"
            if o.get("role"):
                line += f" — {o['role']}"
            # Enrich with DB properties
            card = oil_card_map.get((o.get("name_ru") or "").lower()) or oil_card_map.get((o.get("name_en") or "").lower())
            if card:
                props = []
                if card.get("mind_effect"):
                    props.append(f"действие: {card['mind_effect'][:80]}")
                if card.get("therapeutic_properties"):
                    props.append(f"свойства: {card['therapeutic_properties'][:80]}")
                if props:
                    line += f" [{'; '.join(props)}]"
            parts.append(line)

    if bc.get("expert_note"):
        parts.append(f"\nСинергия: {bc['expert_note']}")
    if bc.get("application_guide"):
        parts.append(f"Применение: {bc['application_guide']}")
    return "\n".join(parts)


def build_blend_carousel_narrative(bc: dict) -> str:
    """5-slide arc: hook → oils → synergy → application → CTA."""
    oils = bc.get("oils", [])
    oil_names = [o.get("name_ru", "") for o in oils if o.get("name_ru")]
    title = bc.get("title", "Смесь")
    profile = bc.get("profile", {})

    # Determine dominant trait
    dominant = max(profile, key=lambda k: profile.get(k, 0), default="") if profile else ""
    trait_labels = {"focus": "концентрацию", "energy": "энергию", "creativity": "творчество", "calm": "спокойствие"}
    trait = trait_labels.get(dominant, "баланс")

    return (
        f"Карусель посвящена смеси «{title}», которая усиливает {trait}.\n\n"
        f"Slide 1: Хук — проблема или состояние, к которому обращена смесь. "
        f"Не упоминай масла, говори о том что чувствует человек.\n"
        f"Slide 2-3: По маслу на слайд — {', '.join(oil_names[:3])}. "
        f"Для каждого: роль в смеси и конкретный эффект на состояние.\n"
        f"Slide 4: Синергия — как масла работают вместе. "
        f"{'Используй: ' + bc['expert_note'][:200] if bc.get('expert_note') else 'Объясни общий эффект.'}\n"
        f"Slide 5: CTA — как собрать и применить смесь. "
        f"{'Способ: ' + bc['application_guide'][:150] if bc.get('application_guide') else 'Призови попробовать.'}"
    )


def build_blend_reels_concept(bc: dict) -> str:
    """Transformation arc: before → blend → after. Frames with oils."""
    oils = bc.get("oils", [])
    oil_names = [o.get("name_ru", "") for o in oils if o.get("name_ru")]
    title = bc.get("title", "Смесь")
    profile = bc.get("profile", {})

    dominant = max(profile, key=lambda k: profile.get(k, 0), default="") if profile else ""
    trait_labels = {"focus": "фокус и ясность", "energy": "энергию и тонус", "creativity": "вдохновение и креативность", "calm": "спокойствие и расслабление"}
    trait = trait_labels.get(dominant, "баланс и гармонию")

    return (
        f"Рилс про смесь «{title}»: трансформация через аромат.\n\n"
        f"Нарратив: ДО (проблема/состояние) → СМЕСЬ (процесс создания) → ПОСЛЕ ({trait}).\n"
        f"Масла в кадрах: {', '.join(oil_names[:3])}.\n"
        f"{'Синергия: ' + bc['expert_note'][:200] + chr(10) if bc.get('expert_note') else ''}"
        f"{'Применение: ' + bc['application_guide'][:150] if bc.get('application_guide') else ''}"
    )


def mood_to_visual_directive(profile: dict) -> str:
    """Map {focus, energy, creativity, calm} → palette + lighting + mood.

    Returns an English visual directive string for image prompt enrichment.
    """
    if not profile:
        return ""

    focus = profile.get("focus", 0)
    energy = profile.get("energy", 0)
    creativity = profile.get("creativity", 0)
    calm = profile.get("calm", 0)

    dominant = max(profile, key=lambda k: profile.get(k, 0))

    if dominant == "focus" and focus >= 30:
        if energy >= 30:
            return (
                "warm amber and golden hour palette, sharp focused composition, "
                "rosemary and citrus botanicals, sunlit wooden surface, "
                "confident energetic mood, bright directional light"
            )
        return (
            "cool mint and eucalyptus tones, clean minimalist composition, "
            "crisp morning light, glass and ceramic surfaces, "
            "clear-minded focused atmosphere"
        )

    if dominant == "calm" and calm >= 30:
        return (
            "cool lavender mist and sage green palette, soft diffused light, "
            "linen textures and dried botanicals, gentle shadows, "
            "serene tranquil mood, muted earth tones"
        )

    if dominant == "creativity" and creativity >= 30:
        return (
            "saturated botanical palette with purple and amber accents, "
            "organic textures and flowing forms, warm artistic lighting, "
            "creative vibrant atmosphere, rich natural materials"
        )

    if dominant == "energy" and energy >= 30:
        return (
            "bright citrus and warm ginger palette, dynamic composition, "
            "morning sunlight, fresh green leaves and zest, "
            "energizing uplifting mood, vivid saturated tones"
        )

    # Balanced / fallback
    return (
        "terracotta and sage brand palette, soft natural light, "
        "botanical elements, warm wood and ceramic surfaces, "
        "balanced harmonious mood"
    )


def build_blend_of_week_topic(bc: dict) -> str:
    """Generate a topic string for 'Blend of the Week' content.

    Combines blend title, dominant trait, and key oils into a compelling topic.
    """
    title = bc.get("title", "Смесь недели")
    profile = bc.get("profile", {})
    oils = bc.get("oils", [])
    oil_names = [o.get("name_ru", "") for o in oils if o.get("name_ru")]

    dominant = max(profile, key=lambda k: profile.get(k, 0), default="") if profile else ""
    trait_labels = {
        "focus": "для концентрации и ясности",
        "energy": "для бодрости и тонуса",
        "creativity": "для вдохновения",
        "calm": "для спокойствия и расслабления",
    }
    trait = trait_labels.get(dominant, "для баланса")

    oils_str = " + ".join(oil_names[:3]) if oil_names else "ароматические масла"
    return f"Смесь недели «{title}»: {oils_str} {trait}"


async def fetch_oil_properties(oil_names: list[str]) -> list[dict]:
    """Lookup AromaCard data for blend oils from the reference database."""
    from bot.services.miniapp_references import list_reference_cards

    aromas = await list_reference_cards("aroma")
    aroma_map: dict[str, dict] = {}
    for a in aromas:
        name = (a.get("name") or "").lower()
        name_en = (a.get("name_en") or "").lower()
        if name:
            aroma_map[name] = a
        if name_en:
            aroma_map[name_en] = a

    result: list[dict] = []
    for name in oil_names:
        card = aroma_map.get(name.lower())
        if card:
            result.append(card)
    return result
