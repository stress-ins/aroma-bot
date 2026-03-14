#!/usr/bin/env python3
"""
Audit all AromaCards by running UX and Expert agents on each card.

Usage:
    .venv/bin/python scripts/audit_cards.py [--category blend|symptom|aroma|all] [--expert]

Examples:
    .venv/bin/python scripts/audit_cards.py --category blend
    .venv/bin/python scripts/audit_cards.py --category all --expert
    .venv/bin/python scripts/audit_cards.py --category aroma --expert

Exit code 1 if any card fails (score < 0.7).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from bot.agents.aromatherapy_expert import verify_card_content
from bot.agents.ux_reviewer import review_card_ux
from bot.services.miniapp_references import _serialize_model, seed_reference_cards_if_empty
from db.models import AromaCardModel
from db.session import AsyncSessionLocal, init_db

VALID_CATEGORIES = {"blend", "symptom", "aroma", "practice", "sound", "concept"}
PASS_THRESHOLD = 0.7


async def load_cards(category: str) -> list[AromaCardModel]:
    """Load all AromaCardModel rows for the given category (or all categories)."""
    await seed_reference_cards_if_empty()
    async with AsyncSessionLocal() as session:
        if category == "all":
            result = await session.execute(select(AromaCardModel))
        else:
            result = await session.execute(
                select(AromaCardModel).where(AromaCardModel.category == category)
            )
        models = result.scalars().all()
    return list(models)


async def audit_card(
    model: AromaCardModel,
    *,
    run_expert: bool,
) -> dict:
    """Run UX (and optionally expert) agent on a single card. Returns audit result dict."""
    card_detail = _serialize_model(model)

    ux_result = await review_card_ux(card_detail)
    result = {
        "name": str(card_detail.get("name") or model.name),
        "slug": model.slug,
        "category": model.category,
        "ux_score": ux_result["score"],
        "ux_passed": ux_result["passed"],
        "ux_issues": ux_result.get("issues") or [],
        "expert_score": None,
        "expert_passed": None,
        "expert_issues": [],
    }

    if run_expert:
        expert_result = await verify_card_content(card_detail, dry_run=True)
        result["expert_score"] = expert_result["score"]
        result["expert_passed"] = expert_result["passed"]
        result["expert_issues"] = expert_result.get("issues") or []

    return result


def _overall_passed(result: dict) -> bool:
    """A card passes if UX passes, and expert passes when it was run."""
    if not result["ux_passed"]:
        return False
    if result["expert_passed"] is not None and not result["expert_passed"]:
        return False
    return True


def _format_line(result: dict, *, run_expert: bool) -> str:
    name = result["name"]
    ux_score = result["ux_score"]
    passed = _overall_passed(result)

    parts = [f"UX={ux_score:.2f}"]
    if run_expert and result["expert_score"] is not None:
        parts.append(f"Expert={result['expert_score']:.2f}")

    score_str = ", ".join(parts)

    all_issues = list(result["ux_issues"])
    if run_expert:
        all_issues.extend(result["expert_issues"])

    if passed:
        line = f"  {name}: {score_str}"
    else:
        issue_summary = "; ".join(all_issues) if all_issues else "score below threshold"
        line = f"  {name}: {score_str} — {issue_summary}"

    return line


async def main() -> int:
    parser = argparse.ArgumentParser(description="Audit AromaCards with UX and Expert agents.")
    parser.add_argument(
        "--category",
        default="all",
        choices=["blend", "symptom", "aroma", "practice", "sound", "concept", "all"],
        help="Card category to audit (default: all)",
    )
    parser.add_argument(
        "--expert",
        action="store_true",
        default=False,
        help="Also run aromatherapy expert agent (rule-based, dry_run=True)",
    )
    args = parser.parse_args()

    await init_db()

    models = await load_cards(args.category)
    if not models:
        print(f"No cards found for category: {args.category!r}")
        return 0

    category_label = args.category if args.category != "all" else "all"
    print(f"Auditing {len(models)} {category_label} cards...")
    if args.expert:
        print("  (UX + Expert agents)")
    else:
        print("  (UX agent only; use --expert to also run aromatherapy expert)")
    print()

    results = []
    for model in sorted(models, key=lambda m: (m.category, m.name)):
        result = await audit_card(model, run_expert=args.expert)
        results.append(result)
        line = _format_line(result, run_expert=args.expert)
        marker = "✓" if _overall_passed(result) else "⚠"
        print(f"{marker}{line}")

    # Summary
    total = len(results)
    passed_count = sum(1 for r in results if _overall_passed(r))
    failed_count = total - passed_count

    print()
    print(f"Summary: {passed_count}/{total} passed (score >= {PASS_THRESHOLD})")

    if failed_count > 0:
        print(f"Failed: {failed_count} card(s)")
        print()
        print("Failed cards:")
        for r in results:
            if not _overall_passed(r):
                all_issues = list(r["ux_issues"])
                if args.expert:
                    all_issues.extend(r["expert_issues"])
                issue_text = "; ".join(all_issues) if all_issues else "score below threshold"
                expert_part = f", Expert={r['expert_score']:.2f}" if args.expert and r["expert_score"] is not None else ""
                print(f"  [{r['category']}] {r['name']} (UX={r['ux_score']:.2f}{expert_part}): {issue_text}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
