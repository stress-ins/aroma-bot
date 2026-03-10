from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Topic:
    name: str
    keywords_ru: list[str]
    keywords_en: list[str]
    hashtags_ru: list[str]
    hashtags_en: list[str]

    @property
    def all_keywords(self) -> list[str]:
        return self.keywords_ru + self.keywords_en

    @property
    def all_hashtags(self) -> list[str]:
        return self.hashtags_ru + self.hashtags_en


TOPICS: list[Topic] = [
    Topic(
        name="Ароматерапия",
        keywords_ru=["ароматерапия", "аромотерапия", "ароматические масла"],
        keywords_en=["aromatherapy", "aroma therapy"],
        hashtags_ru=["#ароматерапия", "#аромотерапия", "#ароматическиемасла"],
        hashtags_en=["#aromatherapy", "#aromatherapist", "#aromatherapylover"],
    ),
    Topic(
        name="Ольфактотерапия",
        keywords_ru=["ольфактотерапия", "ольфакторная терапия", "обонятельная терапия"],
        keywords_en=["olfactotherapy", "scent therapy", "olfactory therapy"],
        hashtags_ru=["#ольфактотерапия", "#ольфакторнаятерапия"],
        hashtags_en=["#olfactotherapy", "#scenttherapy", "#olfactorytherapy"],
    ),
    Topic(
        name="Эфирные масла",
        keywords_ru=["эфирные масла", "натуральные масла", "эфирное масло"],
        keywords_en=["essential oils", "pure essential oils", "therapeutic essential oils"],
        hashtags_ru=["#эфирныемасла", "#натуральныемасла", "#эфирноемасло"],
        hashtags_en=["#essentialoils", "#essentialoil", "#pureessentialoils"],
    ),
    Topic(
        name="Медитация гонг",
        keywords_ru=["медитация гонг", "гонг-баня", "гонг терапия", "гонг медитация", "гонг ванна"],
        keywords_en=["gong meditation", "gong bath", "gong healing", "gong sound"],
        hashtags_ru=["#медитациягонг", "#гонгбаня", "#гонгтерапия", "#гонгмедитация"],
        hashtags_en=["#gongbath", "#gongmeditation", "#gonghealing", "#gongsound"],
    ),
    Topic(
        name="Конкретные масла",
        keywords_ru=[
            "лаванда масло", "бергамот масло", "розмарин масло", "эвкалипт масло",
            "мята перечная масло", "иланг-иланг масло", "пачули масло",
            "ладан масло", "нероли масло", "сандал масло",
        ],
        keywords_en=[
            "lavender essential oil", "bergamot essential oil", "rosemary essential oil",
            "eucalyptus essential oil", "peppermint essential oil", "ylang ylang essential oil",
            "patchouli essential oil", "frankincense essential oil", "neroli essential oil",
            "sandalwood essential oil",
        ],
        hashtags_ru=[
            "#лаванда", "#бергамот", "#розмарин", "#эвкалипт",
            "#мятаперечная", "#иланг", "#пачули", "#ладан", "#нероли", "#сандал",
        ],
        hashtags_en=[
            "#lavender", "#bergamot", "#rosemary", "#eucalyptus",
            "#peppermint", "#ylangylang", "#patchouli", "#frankincense", "#neroli", "#sandalwood",
        ],
    ),
]

# Flat lists for quick access
ALL_KEYWORDS_EN: list[str] = [kw for t in TOPICS for kw in t.keywords_en]
ALL_KEYWORDS_RU: list[str] = [kw for t in TOPICS for kw in t.keywords_ru]
ALL_KEYWORDS: list[str] = ALL_KEYWORDS_RU + ALL_KEYWORDS_EN

ALL_HASHTAGS_EN: list[str] = [h for t in TOPICS for h in t.hashtags_en]
ALL_HASHTAGS_RU: list[str] = [h for t in TOPICS for h in t.hashtags_ru]
ALL_HASHTAGS: list[str] = ALL_HASHTAGS_RU + ALL_HASHTAGS_EN

# Google Trends — EN (max 5 за запрос, смежные темы для контекста)
GOOGLE_TRENDS_KEYWORDS_EN: list[str] = [
    "aromatherapy",
    "sound bath",
    "essential oils",
    "sound healing",
    "mindfulness",
]

# Google Trends — RU (смежные темы: медитация как широкий контекст)
GOOGLE_TRENDS_KEYWORDS_RU: list[str] = [
    "ароматерапия",
    "звуковые ванны",
    "эфирные масла",
    "медитация",
    "поющие чаши",
]

# Subreddits to monitor
REDDIT_SUBREDDITS: list[str] = [
    "aromatherapy",
    "Meditation",
    "essentialoils",
    "soundbath",
]

# Snapshot of original TOPICS data (before any custom overrides)
_ORIGINAL: list[tuple[list, list, list, list]] = [
    (t.keywords_ru[:], t.keywords_en[:], t.hashtags_ru[:], t.hashtags_en[:])
    for t in TOPICS
]


def apply_custom() -> None:
    """Load custom.json and apply additions/removals to TOPICS in-place.
    Safe to call multiple times — always resets to originals first.
    """
    from keywords.store import _load, FIELD_MAP

    # Reset TOPICS to original state
    for i, (kw_ru, kw_en, tag_ru, tag_en) in enumerate(_ORIGINAL):
        TOPICS[i].keywords_ru = list(kw_ru)
        TOPICS[i].keywords_en = list(kw_en)
        TOPICS[i].hashtags_ru = list(tag_ru)
        TOPICS[i].hashtags_en = list(tag_en)

    # Apply saved additions and removals
    data = _load()
    for key, words in data.get("added", {}).items():
        idx_str, fld = key.split(":", 1)
        attr = FIELD_MAP.get(fld)
        if attr and 0 <= int(idx_str) < len(TOPICS):
            lst = getattr(TOPICS[int(idx_str)], attr)
            for w in words:
                if w not in lst:
                    lst.append(w)
    for key, words in data.get("removed", {}).items():
        idx_str, fld = key.split(":", 1)
        attr = FIELD_MAP.get(fld)
        if attr and 0 <= int(idx_str) < len(TOPICS):
            lst = getattr(TOPICS[int(idx_str)], attr)
            for w in words:
                if w in lst:
                    lst.remove(w)

    # Recompute flat lists in-place so importers see the update
    ALL_KEYWORDS_EN[:] = [kw for t in TOPICS for kw in t.keywords_en]
    ALL_KEYWORDS_RU[:] = [kw for t in TOPICS for kw in t.keywords_ru]
    ALL_KEYWORDS[:] = ALL_KEYWORDS_RU + ALL_KEYWORDS_EN
    ALL_HASHTAGS_EN[:] = [h for t in TOPICS for h in t.hashtags_en]
    ALL_HASHTAGS_RU[:] = [h for t in TOPICS for h in t.hashtags_ru]
    ALL_HASHTAGS[:] = ALL_HASHTAGS_RU + ALL_HASHTAGS_EN


apply_custom()
