#!/usr/bin/env python3
"""KB Quality Pipeline — runs cleanup, expert, doctor, and summarization phases.

Usage:
    .venv/bin/python scripts/kb_pipeline.py --dry-run
    .venv/bin/python scripts/kb_pipeline.py --phase doctor,summarize --category aroma
    .venv/bin/python scripts/kb_pipeline.py --fix
    .venv/bin/python scripts/kb_pipeline.py --phase all --fix --limit 50
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCRIPTS_DIR = Path(__file__).resolve().parent


# ─── Phase A helpers ─────────────────────────────────────────────────────────

_CLEANUP_SCRIPTS = [
    "cleanup_duplicates.py",
    "cleanup_blend_ingredients.py",
    "fix_broken_card_names.py",
    "fix_data_quality.py",
]


async def _run_cleanup_script(script_name: str, dry_run: bool) -> tuple[str, int, str]:
    """Run a single cleanup script as subprocess. Returns (name, returncode, output)."""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return script_name, 0, f"  [skipped — {script_name} not found]"

    cmd = [sys.executable, str(script_path)]
    if dry_run:
        cmd.append("--dry-run")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode(errors="replace").strip()
    return script_name, proc.returncode or 0, output


async def phase_cleanup(dry_run: bool) -> dict:
    """Phase A: run all cleanup scripts sequentially."""
    print("[A] Cleanup — running cleanup scripts...")
    results = []
    errors = 0
    for script in _CLEANUP_SCRIPTS:
        name, rc, output = await _run_cleanup_script(script, dry_run)
        if rc != 0:
            errors += 1
        results.append({"script": name, "returncode": rc, "output": output})
        status = "✓" if rc == 0 else "✗"
        print(f"    {status} {name} (exit {rc})")
        if output:
            for line in output.splitlines()[:5]:
                print(f"      {line}")
            if len(output.splitlines()) > 5:
                print(f"      ... ({len(output.splitlines())} lines total)")

    return {"scripts": results, "errors": errors}


# ─── Phase B helpers ─────────────────────────────────────────────────────────

async def phase_expert(
    fix: bool,
    dry_run: bool,
    categories: list[str] | None,
    limit: int | None,
) -> dict:
    """Phase B: aromatherapy expert verification."""
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from bot.agents.aromatherapy_expert import verify_card_content

    target_cats = categories if categories else ["aroma"]
    print(f"[B] Expert — verifying categories: {target_cats}...")

    passed = 0
    failed = 0
    total_issues: list[str] = []
    fixes_applied = 0

    async with AsyncSessionLocal() as session:
        stmt = select(AromaCardModel).where(AromaCardModel.category.in_(target_cats))
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        cards = result.scalars().all()

        for card in cards:
            card_dict = {
                "name": card.name,
                "slug": card.slug,
                "category": card.category,
                "source_type": card.source_type,
                **(card.payload or {}),
            }

            review = await verify_card_content(card_dict, dry_run=dry_run)

            if review["passed"]:
                passed += 1
            else:
                failed += 1
                for issue in review.get("issues", []):
                    total_issues.append(f"{card.slug}: {issue}")

            if fix and not dry_run and review.get("corrections"):
                payload = dict(card.payload or {})
                payload.update(review["corrections"])
                card.payload = payload
                card.updated_at = datetime.now(timezone.utc)
                fixes_applied += 1

        if fix and not dry_run:
            await session.commit()

    print(f"    {passed}/{passed + failed} passed  ({failed} issues)")
    return {
        "passed": passed,
        "failed": failed,
        "issues": total_issues,
        "fixes_applied": fixes_applied,
    }


# ─── Phase C helpers ─────────────────────────────────────────────────────────

async def phase_doctor(
    fix: bool,
    dry_run: bool,
    categories: list[str] | None,
    limit: int | None,
) -> dict:
    """Phase C: medical safety review."""
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel
    from bot.agents.medical_reviewer import review_card_medical

    target_cats = categories if categories else ["aroma", "blend", "symptom"]
    print(f"[C] Doctor — reviewing categories: {target_cats}...")

    passed = 0
    failed = 0
    critical_count = 0
    total_issues: list[str] = []
    fixes_applied = 0

    async with AsyncSessionLocal() as session:
        stmt = select(AromaCardModel).where(AromaCardModel.category.in_(target_cats))
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        cards = result.scalars().all()

        for card in cards:
            card_dict = {
                "name": card.name,
                "slug": card.slug,
                "category": card.category,
                "source_type": card.source_type,
                **(card.payload or {}),
            }

            review = await review_card_medical(card_dict, dry_run=dry_run)

            card_issues = review.get("issues", [])
            is_critical = any("CRITICAL" in i for i in card_issues)

            if review["passed"]:
                passed += 1
            else:
                failed += 1

            if is_critical:
                critical_count += 1

            for issue in card_issues:
                total_issues.append(f"{card.slug}: {issue}")
                if "CRITICAL" in issue:
                    print(f"    ⚠ CRITICAL: {card.slug} — {issue}")

            if fix and not dry_run and review.get("corrections"):
                payload = dict(card.payload or {})
                payload.update(review["corrections"])
                card.payload = payload
                card.updated_at = datetime.now(timezone.utc)
                fixes_applied += 1

        if fix and not dry_run:
            await session.commit()

    critical_note = f" ({critical_count} critical)" if critical_count else ""
    print(f"    {passed}/{passed + failed} passed  ({failed} issues{critical_note})")
    return {
        "passed": passed,
        "failed": failed,
        "critical": critical_count,
        "issues": total_issues,
        "fixes_applied": fixes_applied,
    }


# ─── Phase D helpers ─────────────────────────────────────────────────────────

async def phase_summarize(
    dry_run: bool,
    categories: list[str] | None,
    limit: int | None,
) -> dict:
    """Phase D: generate description_short for cards missing it."""
    import os
    from sqlalchemy import select
    from db.session import AsyncSessionLocal
    from db.models import AromaCardModel

    # Import the reusable function
    sys.path.insert(0, str(SCRIPTS_DIR))
    from generate_description_short import generate_short_for_card

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[D] Summarize — ANTHROPIC_API_KEY not set, skipping")
        return {"generated": 0, "skipped": 0, "errors": 0, "no_description": 0}

    target_cats = categories if categories else ["aroma", "blend", "symptom"]
    print(f"[D] Summarize — generating description_short for categories: {target_cats}...")

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    generated = 0
    skipped = 0
    errors = 0
    no_description = 0

    async with AsyncSessionLocal() as session:
        stmt = select(AromaCardModel).where(AromaCardModel.category.in_(target_cats))
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        cards = result.scalars().all()

        for card in cards:
            payload = dict(card.payload or {})

            if payload.get("description_short"):
                skipped += 1
                continue

            description = str(payload.get("description", "")).strip()
            if not description or len(description) < 30:
                no_description += 1
                continue

            if dry_run:
                print(f"    [dry run] {card.slug}: would generate summary")
                generated += 1
                continue

            try:
                summary = generate_short_for_card(payload, client)
                if summary:
                    payload["description_short"] = summary
                    card.payload = payload
                    card.updated_at = datetime.now(timezone.utc)
                    generated += 1
                    print(f"    ✓ {card.slug}: {summary[:70]}")
                else:
                    no_description += 1
                time.sleep(0.5)
            except Exception as e:
                errors += 1
                print(f"    ✗ {card.slug}: {e}")

        if not dry_run:
            await session.commit()

    print(f"    {generated} generated, {errors} errors, {skipped} already had summary")
    return {
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
        "no_description": no_description,
    }


# ─── Report ──────────────────────────────────────────────────────────────────

def _print_report(
    phases_run: list[str],
    cleanup_result: dict | None,
    expert_result: dict | None,
    doctor_result: dict | None,
    summarize_result: dict | None,
    fix: bool,
    dry_run: bool,
) -> bool:
    """Print final report. Returns True if there are critical issues (exit code 1)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print()
    print("═" * 55)
    print(f"KB Pipeline Report  {now}")
    if dry_run:
        print("  ⚠ DRY RUN — no changes were made")
    print("═" * 55)

    total_issues = 0
    total_fixes = 0
    has_critical = False

    if cleanup_result is not None:
        errors = cleanup_result.get("errors", 0)
        status = "OK" if errors == 0 else f"⚠ {errors} script errors"
        print(f"[A] Cleanup        {status}")
        total_issues += errors

    if expert_result is not None:
        p = expert_result.get("passed", 0)
        f = expert_result.get("failed", 0)
        total = p + f
        fixes = expert_result.get("fixes_applied", 0)
        warn = f"  ⚠ {f} issues" if f else ""
        print(f"[B] Expert         {p}/{total} passed{warn}")
        total_issues += f
        total_fixes += fixes

    if doctor_result is not None:
        p = doctor_result.get("passed", 0)
        f = doctor_result.get("failed", 0)
        total = p + f
        crit = doctor_result.get("critical", 0)
        fixes = doctor_result.get("fixes_applied", 0)
        warn = f"  ⚠ {f} issues" if f else ""
        if crit:
            warn += f" ({crit} critical)"
            has_critical = True
        print(f"[C] Doctor         {p}/{total} passed{warn}")
        total_issues += f
        total_fixes += fixes

    if summarize_result is not None:
        gen = summarize_result.get("generated", 0)
        err = summarize_result.get("errors", 0)
        warn = f", {err} errors" if err else ""
        print(f"[D] Summarize      {gen} generated{warn}")
        total_issues += err

    print("─" * 55)
    fix_note = f"  |  Applied fixes: {total_fixes} (--fix)" if fix else ""
    print(f"Total issues: {total_issues}{fix_note}")

    if has_critical:
        print("\n⛔ CRITICAL issues found — pipeline exit code 1")

    print("═" * 55)
    return has_critical


# ─── Main ────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description="KB Quality Pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only — no DB changes",
    )
    parser.add_argument(
        "--phase",
        default="all",
        help="Phases to run: all, cleanup, expert, doctor, summarize (comma-separated)",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Filter by category (comma-separated): aroma,blend,symptom",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-apply corrections from agents",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max cards to process per phase",
    )
    args = parser.parse_args()

    phases_raw = [p.strip().lower() for p in args.phase.split(",")]
    if "all" in phases_raw:
        phases = ["cleanup", "expert", "doctor", "summarize"]
    else:
        phases = phases_raw

    categories = (
        [c.strip().lower() for c in args.category.split(",")]
        if args.category
        else None
    )

    dry_run = args.dry_run
    fix = args.fix and not dry_run

    cleanup_result = None
    expert_result = None
    doctor_result = None
    summarize_result = None

    if "cleanup" in phases:
        cleanup_result = await phase_cleanup(dry_run=dry_run)

    if "expert" in phases:
        expert_result = await phase_expert(
            fix=fix, dry_run=dry_run, categories=categories, limit=args.limit
        )

    if "doctor" in phases:
        doctor_result = await phase_doctor(
            fix=fix, dry_run=dry_run, categories=categories, limit=args.limit
        )

    if "summarize" in phases:
        summarize_result = await phase_summarize(
            dry_run=dry_run, categories=categories, limit=args.limit
        )

    has_critical = _print_report(
        phases_run=phases,
        cleanup_result=cleanup_result,
        expert_result=expert_result,
        doctor_result=doctor_result,
        summarize_result=summarize_result,
        fix=fix,
        dry_run=dry_run,
    )

    return 1 if has_critical else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
