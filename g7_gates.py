"""G7 ask-band helpers for cycle_runner (ASK_MAX/ASK_MIN, GATE_SHADOW)."""
from __future__ import annotations

import os


def env_float(name: str):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def ask_band_config():
    """Return (ask_max, ask_min, gate_shadow, configured). Shadow default GATE_SHADOW=1."""
    ask_max = env_float("ASK_MAX")
    ask_min = env_float("ASK_MIN")
    shadow_raw = os.environ.get("GATE_SHADOW", "1").strip().lower()
    gate_shadow = shadow_raw not in ("0", "false", "no", "off")
    configured = ask_max is not None or ask_min is not None
    return ask_max, ask_min, gate_shadow, configured


def evaluate_ask_band(ask) -> dict:
    ask_max, ask_min, gate_shadow, configured = ask_band_config()
    would_pass = True
    if ask is not None:
        if ask_max is not None and ask > ask_max + 1e-12:
            would_pass = False
        if ask_min is not None and ask < ask_min - 1e-12:
            would_pass = False
    hard = (not configured) or gate_shadow or would_pass
    return {
        "g7": would_pass,
        "g7_configured": configured,
        "g7_would_pass": would_pass,
        "ask_max": ask_max,
        "ask_min": ask_min,
        "gate_shadow": gate_shadow,
        "hard_g7": hard,
    }
