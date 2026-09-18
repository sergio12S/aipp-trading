#!/usr/bin/env python3
"""Unit tests for evaluate_v2 G7 ask-band (no network). Long-only G1–G6 assumed."""
from __future__ import annotations

import importlib
import os
import sys


def _card(*, ask: float, p: float) -> dict:
    return {
        "market": {
            "title": "test",
            "slug": "btc-updown-15m-test",
            "yes": {"ask": ask},
            "no": {"ask": 0.5},
        },
        "decision": {"action": "BUY_YES", "side": "YES"},
        "combined": {"pYes": p, "pNo": 1.0 - p, "conflict": False, "confidence": 0.7},
        "pattern": {"ensemble": {}},
        "execution": {},
        "evidenceQuality": {"grade": "OK", "score": 0.9},
        "marketStructure": {"trend": "TREND"},
    }


def _reload(**env):
    for k in ("ASK_MAX", "ASK_MIN", "GATE_SHADOW"):
        os.environ.pop(k, None)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)
    if "cycle_runner" in sys.modules:
        del sys.modules["cycle_runner"]
    return importlib.import_module("cycle_runner")


def main():
    # expensive ask, shadow on → still execute if G1–G6 pass
    cr = _reload(ASK_MAX="0.70", GATE_SHADOW="1")
    ev = cr.evaluate_v2(_card(ask=0.90, p=0.95), trend="UP")
    assert ev["g1"] and ev["g2"] and ev["g3"] and ev["g4"] and ev["g5"] and ev["g6"]
    assert ev["g7_would_pass"] is False
    assert ev["execute"] is True, ev
    assert ev["gate_shadow"] is True

    # same, hard gate → block
    cr = _reload(ASK_MAX="0.70", GATE_SHADOW="0")
    ev = cr.evaluate_v2(_card(ask=0.90, p=0.95), trend="UP")
    assert ev["g7_would_pass"] is False
    assert ev["execute"] is False, ev

    # mid ask passes band
    cr = _reload(ASK_MAX="0.70", ASK_MIN="0.35", GATE_SHADOW="0")
    ev = cr.evaluate_v2(_card(ask=0.50, p=0.64), trend="UP")
    assert ev["g7_would_pass"] is True
    assert ev["execute"] is True, ev

    # no ASK_* → G7 inactive
    cr = _reload(GATE_SHADOW="1")
    ev = cr.evaluate_v2(_card(ask=0.90, p=0.95), trend="UP")
    assert ev["g7"] is None
    assert ev["g7_configured"] is False
    assert ev["execute"] is True, ev

    print("ok test_gates")


if __name__ == "__main__":
    main()
