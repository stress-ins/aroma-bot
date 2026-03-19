"""Reference cards service — split into entity modules for maintainability.

All public symbols are re-exported here for backward compatibility so that
``from bot.services.miniapp_references import X`` continues to work.
"""
from __future__ import annotations

# --- common: constants, helpers, CRUD ------------------------------------------
from .common import (
    BASE_DIR,
    EDITABLE_FIELDS,
    EXTRA_SEED_FILE,
    INTERNAL_OVERRIDES_KEY,
    INTERNAL_SEED_KEY,
    REFERENCE_CATEGORIES,
    REFERENCE_CONTEXT_TITLES,
    REFERENCE_IMAGES_DIR,
    RESOURCE_FIELDS,
    SEED_FILE,
    SHARED_IMAGE_OVERRIDES,
    SLUG_SHARED_OVERRIDES,
    AsyncSessionLocal,
    _compact_reference_detail,
    _ENRICHMENT_FIELDS,
    _extract_ru_name,
    _image_label,
    _load_seed_items,
    _local_reference_image_url,
    _merge_seed_into_existing,
    _normalize,
    _payload_image_url,
    _public_payload,
    _resolve_symptom_refs,
    _seeded_payload,
    _serialize_model,
    _shared_reference_image_url,
    _source_illustration_key,
    _source_image,
    _source_motif_svg,
    _SVG_PREFIX,
    _SYMPTOM_STOP_WORDS,
    build_reference_context,
    enrich_reference_card,
    get_reference_card,
    list_reference_cards,
    list_reference_cards_missing_description,
    list_reference_cards_with_placeholder_images,
    seed_reference_cards_if_empty,
    update_reference_card,
)

# --- entity-specific enrichment ------------------------------------------------
from .aroma import _enrich_aroma_cross_refs
from .blend import _enrich_blend_cross_refs
from .symptom import _enrich_symptom_cross_refs

__all__ = [
    # constants
    "BASE_DIR",
    "EDITABLE_FIELDS",
    "EXTRA_SEED_FILE",
    "INTERNAL_OVERRIDES_KEY",
    "INTERNAL_SEED_KEY",
    "REFERENCE_CATEGORIES",
    "REFERENCE_CONTEXT_TITLES",
    "REFERENCE_IMAGES_DIR",
    "RESOURCE_FIELDS",
    "SEED_FILE",
    "SHARED_IMAGE_OVERRIDES",
    "SLUG_SHARED_OVERRIDES",
    # re-exported for monkeypatching in tests
    "AsyncSessionLocal",
    # private helpers (used by tests / scripts)
    "_compact_reference_detail",
    "_ENRICHMENT_FIELDS",
    "_extract_ru_name",
    "_image_label",
    "_load_seed_items",
    "_local_reference_image_url",
    "_merge_seed_into_existing",
    "_normalize",
    "_payload_image_url",
    "_public_payload",
    "_resolve_symptom_refs",
    "_seeded_payload",
    "_serialize_model",
    "_shared_reference_image_url",
    "_source_illustration_key",
    "_source_image",
    "_source_motif_svg",
    "_SVG_PREFIX",
    "_SYMPTOM_STOP_WORDS",
    # async API
    "build_reference_context",
    "enrich_reference_card",
    "get_reference_card",
    "list_reference_cards",
    "list_reference_cards_missing_description",
    "list_reference_cards_with_placeholder_images",
    "seed_reference_cards_if_empty",
    "update_reference_card",
    # entity-specific enrichment
    "_enrich_aroma_cross_refs",
    "_enrich_blend_cross_refs",
    "_enrich_symptom_cross_refs",
]
