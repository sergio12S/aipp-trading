#!/usr/bin/env python3
"""Unit tests for G1–G7 gates in cycle_runner.evaluate_v2."""
from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Stub optional trading deps so cycle_runner imports cleanly in CI/box.
for name in (
    "polymarket_agent_bot",
    "polymarket_executor",
    "py_clob_client_v2",
    "py_clob_client_v2.clob_types",
):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        if name.endswith("clob_types"):
            mod.BalanceAllowanceParams = object
            mod.AssetType = object
            mod.MarketOrderArgs = object
        if name == "polymarket_agent_bot":
            mod.PolymarketAgentBot = object
        if name == "polymarket_executor":
            mod.get_client = lambda: None
        sys.modules[name] = mod
# parent package stub
if "py_clob_client_v2" in sys.modules:
    sys.modules["py_clob_client_v2"].clob_types = sys.modules["py_clob_client_v2.clob_types"]

os.environ.pop("ASK_MAX", None)
os.environ.pop("ASK_MIN", None)
os.environ["GATE_SHADOW"] = "1"
os.environ["MIN_BALANCE"] = "1.0"
os.environ["ALLOCATED_USD"] = "1.0"

import cycle_runner as cr

importlib.reload(cr)


def _card(ask=0.55, p_yes=0.70, conflict=False, grade="OK", score=0.9, ms_trend="UP"):
    return {
        "market": {"yes": {"ask": ask}, "no": {"ask": 0.45}, "title": "t", "slug": "s"},
        "decision": {"action": "BUY_YES", "side": "YES"},
        "combined": {"pYes": p_yes, "pNo": 1 - p_yes, "conflict": conflict, "confidence": 0.8},
        "pattern": {"ensemble": {}},
        "execution": {},
        "evidenceQuality": {"grade": grade, "score": score},
        "marketStructure": {"trend": ms_trend},
    }


def test_g7_shadow_does_not_block():
    os.environ["ASK_MAX"] = "0.50"
    os.environ["GATE_SHADOW"] = "1"
    ev = cr.evaluate_v2(_card(ask=0.60, p_yes=0.80), trend="UP")
    assert ev["g7_configured"] is True
    assert ev["g7_would_pass"] is False
    assert ev["gate_shadow"] is True
    assert ev["hard_g7"] is True
    assert ev["execute"] is True


def test_g7_hard_blocks_when_shadow_off():
    os.environ["ASK_MAX"] = "0.50"
    os.environ["GATE_SHADOW"] = "0"
    ev = cr.evaluate_v2(_card(ask=0.60, p_yes=0.80), trend="UP")
    assert ev["g7_configured"] is True
    assert ev["g7_would_pass"] is False
    assert ev["hard_g7"] is False
    assert ev["execute"] is False
    assert "G7 ask-band" in str(ev.get("skip_reasons") or "")


def test_g7_passes_inside_band():
    os.environ["ASK_MAX"] = "0.70"
    os.environ["ASK_MIN"] = "0.35"
    os.environ["GATE_SHADOW"] = "0"
    ev = cr.evaluate_v2(_card(ask=0.55, p_yes=0.80), trend="UP")
    assert ev["g7"] is True
    assert ev["g7_would_pass"] is True
    assert ev["hard_g7"] is True
    assert ev["execute"] is True


def test_remote_g4_quality_still_blocks():
    os.environ.pop("ASK_MAX", None)
    os.environ.pop("ASK_MIN", None)
    os.environ["GATE_SHADOW"] = "1"
    ev = cr.evaluate_v2(_card(ask=0.55, p_yes=0.80, grade="THIN", score=0.2), trend="UP")
    assert ev["g4"] is False
    assert ev["execute"] is False
