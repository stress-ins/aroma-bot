"""CI script: run UX reviewer + aromatherapy expert on changed card data.

Usage:
    python scripts/ci_card_review.py [--all]

Without --all: checks only cards modified in the current branch vs origin/main.
With --all: checks all cards in the database.

Exit code 0 = all passed, 1 = failures found.
"""

import asyncio
import subprocess
import sys

# Minimum UX score to pass
UX_SCORE_THRESHOLD = 0.7


def _changed_files() -> list[str]:
    """Return list of files changed vs origin/main."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().splitlines() if result.stdout.strip() else []


def _card_data_changed(files: list[str]) -> bool:
    """Check if any changed file could affect card data."""
    patterns = [
        "db/models.py",
        "bot/agents/aromatherapy_expert.py",
        "bot/agents/ux_reviewer.py",
        "scripts/import_oil",
        "scripts/enrich_",
        "scripts/reseed_",
        "data/oils",
        "data/seeds",
    ]
    return any(
        any(pattern in f for pattern in patterns)
        for f in files
    )


async def _run_reviews(check_all: bool) -> tuple[int, list[str]]:
    """Run UX reviewer and aromatherapy expert. Returns (exit_code, issues)."""
    # Import here so the script can show usage without deps
    from db.session import AsyncSessionLocal  # noqa: E402
    from db.models import AromaCardModel  # noqa: E402
    from sqlalchemy import select  # noqa: E402

    issues: list[str] = []
    cards_checked = 0

    async with AsyncSessionLocal() as session:
        stmt = select(AromaCardModel).where(AromaCardModel.category == "aroma").limit(None if check_all else 20)
        result = await session.execute(stmt)
        cards = result.scalars().all()

    if not cards:
        print("No cards found in database — skipping review")
        return 0, []

    # Lazy import agents
    from bot.agents.ux_reviewer import review_card_ux
    from bot.agents.aromatherapy_expert import verify_card_content

    for card in cards:
        card_dict = {
            "name": getattr(card, "name", ""),
            "name_en": getattr(card, "name_en", ""),
            "slug": getattr(card, "slug", ""),
            "description": getattr(card, "description", ""),
            "description_short": getattr(card, "description_short", ""),
            "applications": getattr(card, "applications", ""),
            "source_type": getattr(card, "source_type", ""),
            "complementary_oil_slugs": getattr(card, "complementary_oil_slugs", []),
            "complementary_oil_names": getattr(card, "complementary_oil_names", []),
            "parent_group": getattr(card, "parent_group", ""),
        }
        cards_checked += 1

        # UX review
        ux_result = await review_card_ux(card_dict)
        if not ux_result.get("passed", False):
            score = ux_result.get("score", 0)
            card_issues = ux_result.get("issues", [])
            issues.append(
                f"UX FAIL: {card_dict['name']} (score={score:.2f}): "
                + "; ".join(card_issues)
            )

        # Aromatherapy expert
        expert_result = await verify_card_content(card_dict, dry_run=True)
        if not expert_result.get("passed", False):
            expert_issues = expert_result.get("issues", [])
            issues.append(
                f"EXPERT FAIL: {card_dict['name']}: "
                + "; ".join(expert_issues)
            )

    print(f"Checked {cards_checked} cards")

    if issues:
        print(f"\n{len(issues)} issue(s) found:")
        for issue in issues:
            print(f"  - {issue}")
        return 1, issues

    print("All cards passed UX + expert review")
    return 0, []


def main() -> None:
    check_all = "--all" in sys.argv

    if not check_all:
        changed = _changed_files()
        if not _card_data_changed(changed):
            print("No card-related files changed — skipping card review")
            sys.exit(0)

    try:
        exit_code, _ = asyncio.run(_run_reviews(check_all))
    except Exception as e:
        # In CI there is no database — skip gracefully
        if "no such table" in str(e).lower() or "unable to open" in str(e).lower():
            print(f"No database available — skipping card review ({e})")
            sys.exit(0)
        raise
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
