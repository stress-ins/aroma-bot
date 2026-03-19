"""Background generation tasks shared across routers and the lifespan hook.

This package re-exports all public symbols so that existing imports like
``from miniapp.api.generation import complete_carousel_generation`` keep working.
"""
from __future__ import annotations

from ._common import set_generation_state as set_generation_state
from ._common import _run_generation_task as _run_generation_task
from .carousel import complete_carousel_generation as complete_carousel_generation
from .carousel import complete_carousel_regen_slide as complete_carousel_regen_slide
from .carousel import complete_carousel_regenerate_all as complete_carousel_regenerate_all
from .content import complete_content_generation as complete_content_generation
from .content import complete_threads_series_generation as complete_threads_series_generation
from .plan import generate_blend_construct as generate_blend_construct
from .reels import complete_reels_generation as complete_reels_generation
from .reels import complete_reels_regenerate_all as complete_reels_regenerate_all
from .reels import complete_reels_v2_generate_images as complete_reels_v2_generate_images
from .reels import complete_reels_v2_generation as complete_reels_v2_generation
from .reels import complete_reels_v2_regen_caption as complete_reels_v2_regen_caption
from .reels import complete_reels_v2_regen_concept as complete_reels_v2_regen_concept
from .reels import complete_reels_v2_regen_concept_only as complete_reels_v2_regen_concept_only
from .reels import complete_reels_v2_regen_frame as complete_reels_v2_regen_frame
from .reels import complete_reels_v2_regen_scenario_only as complete_reels_v2_regen_scenario_only

__all__ = [
    "complete_carousel_generation",
    "complete_carousel_regen_slide",
    "complete_carousel_regenerate_all",
    "complete_content_generation",
    "complete_reels_generation",
    "complete_reels_regenerate_all",
    "complete_reels_v2_generate_images",
    "complete_reels_v2_generation",
    "complete_reels_v2_regen_caption",
    "complete_reels_v2_regen_concept",
    "complete_reels_v2_regen_concept_only",
    "complete_reels_v2_regen_frame",
    "complete_reels_v2_regen_scenario_only",
    "complete_threads_series_generation",
    "generate_blend_construct",
    "set_generation_state",
]
