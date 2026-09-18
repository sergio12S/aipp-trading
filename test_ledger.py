#!/usr/bin/env python3
"""Smoke test: SKIP + EXECUTED rows land in SQLite; resolve is idempotent on empty."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import trade_db


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "trades.db")
        trade_db.init_db(db)
        skip_id = trade_db.record_cycle(
            {
                "final": "SKIP",
                "action": "SKIP",
                "side": None,
                "slug": "btc-updown-15m-test-skip",
                "g1": False,
                "g2": True,
                "g3": False,
                "price_ok": True,
                "p_yes": 0.4,
                "p_no": 0.6,
                "edge": 0.0,
                "skip_reasons": ["unit test skip"],
            },
            card={"decisionMode": "standard", "market": {"marketId": "1", "slug": "btc-updown-15m-test-skip"}},
            db_path=db,
        )
        exec_id = trade_db.record_cycle(
            {
                "final": "EXECUTED",
                "action": "BUY_NO",
                "side": "NO",
                "slug": "btc-updown-15m-test-exec",
                "g1": True,
                "g2": True,
                "g3": True,
                "price_ok": True,
                "ask": 0.46,
                "p_side": 0.64,
                "p_yes": 0.36,
                "p_no": 0.64,
                "edge": 0.18,
                "making_usd": 5.0,
                "taking_shares": 10.0,
                "order": {"orderID": "0xtest", "status": "matched", "makingAmount": "5", "takingAmount": "10"},
            },
            card={"decisionMode": "standard", "market": {"marketId": "2", "slug": "btc-updown-15m-test-exec"}},
            db_path=db,
        )
        assert skip_id >= 1 and exec_id >= 1
        with trade_db.connect(db) as conn:
            finals = dict(conn.execute("SELECT final, COUNT(*) FROM cycles GROUP BY final"))
        assert finals.get("SKIP") == 1, finals
        assert finals.get("EXECUTED") == 1, finals
        out = trade_db.resolve_pending(db_path=db, limit=10, force_min_age_minutes=9999)
        assert out["resolved"] == 0  # market too young / not found — must not crash
        print("ok", finals, "resolve", out)


if __name__ == "__main__":
    main()
