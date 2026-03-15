"""Batch-verify all symptom cards via the aromatherapy expert agent.

Runs every symptom card through verify_card_content (LLM + rule-based) and
reports suggested corrections for parent_group / category_group.

Usage:
    .venv/bin/python scripts/verify_symptom_categories.py [--dry-run] [--apply]
    --dry-run   Run LLM expert but only print suggestions, do NOT write to DB
    --apply     Write corrections to DB (parent_group / category_group only)

Default (no flags): same as --dry-run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def run(apply: bool = False) -> None:
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from bot.agents.aromatherapy_expert import verify_card_content
    from bot.services.miniapp_references import _serialize_model
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AromaCardModel).where(AromaCardModel.category == "symptom")
        )
        models = list(result.scalars().all())

    total = len(models)
    print(f"Loaded {total} symptom cards. Running expert verification...\n")

    ok_count = 0
    correction_count = 0
    error_count = 0
    all_corrections: list[dict] = []

    for i, model in enumerate(models, 1):
        card = _serialize_model(model)
        prefix = f"[{i:3d}/{total}] {model.slug}"
        try:
            result_v = await verify_card_content(card, dry_run=False)
        except Exception as exc:
            print(f"{prefix}  ERROR: {exc}")
            error_count += 1
            continue

        corrections = result_v.get("corrections") or {}
        issues = result_v.get("issues") or []
        score = result_v.get("score", 1.0)

        # Only care about parent_group / category_group corrections
        relevant = {
            k: v for k, v in corrections.items()
            if k in ("parent_group", "category_group")
        }

        if relevant:
            print(f"{prefix}  score={score:.2f}  CORRECTIONS: {json.dumps(relevant, ensure_ascii=False)}")
            if issues:
                for issue in issues[:3]:
                    print(f"           issue: {issue}")
            all_corrections.append({
                "slug": model.slug,
                "name": model.name,
                "current": {
                    "parent_group": (model.payload or {}).get("parent_group", ""),
                    "category_group": (model.payload or {}).get("category_group", ""),
                },
                "proposed": relevant,
            })
            correction_count += 1
        else:
            if issues:
                print(f"{prefix}  score={score:.2f}  issues: {'; '.join(issues[:2])}")
            else:
                print(f"{prefix}  score={score:.2f}  OK")
            ok_count += 1

    print(f"\n{'='*60}")
    print(f"Total: {total} | OK: {ok_count} | Corrections suggested: {correction_count} | Errors: {error_count}")

    if not all_corrections:
        print("No corrections needed.")
        return

    print(f"\nSuggested corrections ({correction_count}):")
    for c in all_corrections:
        print(f"  {c['slug']}")
        print(f"    current:  parent_group={c['current']['parent_group']!r}  category_group={c['current']['category_group']!r}")
        print(f"    proposed: {json.dumps(c['proposed'], ensure_ascii=False)}")

    if not apply:
        print("\n[DRY-RUN] No changes written. Re-run with --apply to write corrections.")
        return

    # Apply corrections
    print(f"\nApplying {len(all_corrections)} corrections to DB...")
    async with AsyncSessionLocal() as session:
        applied = 0
        for entry in all_corrections:
            result_q = await session.execute(
                select(AromaCardModel).where(AromaCardModel.slug == entry["slug"])
            )
            model = result_q.scalar_one_or_none()
            if model is None:
                print(f"  SKIP (not found): {entry['slug']}")
                continue
            new_payload = dict(model.payload or {})
            for field, value in entry["proposed"].items():
                new_payload[field] = value
            model.payload = new_payload
            print(f"  Applied: {entry['slug']}  {entry['proposed']}")
            applied += 1
        await session.commit()

    print(f"\nDone. Applied {applied} corrections.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-verify symptom cards via aromatherapy expert")
    parser.add_argument("--dry-run", action="store_true", help="Preview suggestions without writing (default)")
    parser.add_argument("--apply", action="store_true", help="Write corrections to DB")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("ERROR: --dry-run and --apply are mutually exclusive")
        sys.exit(1)

    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
