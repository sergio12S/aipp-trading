#!/usr/bin/env python3
"""
Resolve pending EXECUTED cycles in trades.db and print stats.

Usage:
  python3 resolve_trades.py              # resolve + stats
  python3 resolve_trades.py --stats-only
  python3 resolve_trades.py --resolve-only
"""
from __future__ import annotations

import argparse
import json

from trade_db import init_db, print_stats, resolve_pending, stats_summary


def main():
    parser = argparse.ArgumentParser(description="Resolve & summarize SQLite trade ledger")
    parser.add_argument("--stats-only", action="store_true")
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-age-minutes", type=float, default=16.0)
    parser.add_argument("--json", action="store_true", help="Print stats as JSON")
    args = parser.parse_args()

    init_db()

    if not args.stats_only:
        out = resolve_pending(limit=args.limit, force_min_age_minutes=args.min_age_minutes)
        print(f"resolve: resolved={out['resolved']} skipped={out['skipped']} errors={len(out['errors'])}")
        for e in out["errors"][:10]:
            print(f"  err: {e}")

    if not args.resolve_only:
        if args.json:
            print(json.dumps(stats_summary(), indent=2, default=str))
        else:
            print_stats()


if __name__ == "__main__":
    main()
