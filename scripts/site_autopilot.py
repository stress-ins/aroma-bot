"""CLI: python -m scripts.site_autopilot --dry-run|--publish [--topic ID]"""
from __future__ import annotations

import argparse
import json
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="generate and validate, write nothing")
    g.add_argument("--publish", action="store_true")
    ap.add_argument("--topic", help="topic id from data/site_topics.json")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    from bot.services.site_autopilot import post_text, body_words, run_once, stoplist_violations

    res = run_once(publish=args.publish, topic_id=args.topic)
    art = res.get("article")
    if art:
        for lang in ("ru", "en"):
            p = art[lang]
            print(f"[{lang}] slug={p['slug']}\n  title={p['title']}\n  excerpt={p['excerpt']}\n"
                  f"  words={body_words(p)} readMinutes={p['readMinutes']} sections={len(p['sections'])}\n"
                  f"  stoplist={stoplist_violations(post_text(p), lang) or 'clean'}")
        print("guardian:", res.get("guardian"))
        if args.topic and "--full" in (argv or sys.argv):
            print(json.dumps(art, ensure_ascii=False, indent=1))
    print("status:", res["status"], {k: v for k, v in res.items() if k in ("issues", "url", "reason", "notes")})
    return 0 if res["status"] in ("dry-run", "published", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
