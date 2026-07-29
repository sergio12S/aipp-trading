#!/usr/bin/env python3
"""
Balanced v2 continuous 15m cycle runner.

Hard gates only:
  G1 AIPP action in {BUY_YES, BUY_NO}
  G2 combined.conflict is false
  G3 fused p_side > ask + EDGE_BUFFER
Then executes via polymarket_agent_bot (live) or dry-run on SKIP.

Waits for each 15m boundary + open buffer, runs one cycle, cancels stale open orders.
Stop: touch STOP file or SIGTERM.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

import requests

from polymarket_agent_bot import PolymarketAgentBot
from polymarket_executor import get_client
from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType, MarketOrderArgs
from trade_db import init_db, record_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "cycle_runner.log")),
    ],
)
logger = logging.getLogger("CycleRunner")

EDGE_BUFFER = 0.02
MIN_BALANCE = 2.0
ALLOCATED_USD = 2.0
OPEN_BUFFER_SEC = 25  # wait after :00/:15/:30/:45 for market listing
STOP_FILE = os.path.join(os.path.dirname(__file__), "STOP_CYCLE_RUNNER")
STATE_FILE = os.path.join(os.path.dirname(__file__), "cycle_runner_state.json")
MAX_CYCLES = int(os.environ.get("MAX_CYCLES", "0"))  # 0 = unlimited
_running = True
_last_traded_slug: str | None = None


def _handle_sig(_signum, _frame):
    global _running
    logger.info("Signal received — stopping after current wait/cycle")
    _running = False


signal.signal(signal.SIGINT, _handle_sig)
signal.signal(signal.SIGTERM, _handle_sig)


def seconds_to_next_boundary(buffer_sec: int = OPEN_BUFFER_SEC) -> float:
    now = datetime.now(timezone.utc)
    m, s, us = now.minute, now.second, now.microsecond
    next_m = ((m // 15) + 1) * 15
    if next_m >= 60:
        wait = (60 - m) * 60 - s - us / 1e6 + buffer_sec
    else:
        wait = (next_m - m) * 60 - s - us / 1e6 + buffer_sec
    return max(1.0, wait)


def unpack_card(raw):
    if not raw:
        return {}
    return raw.get("data", raw) if isinstance(raw, dict) else {}


def evaluate_v2(card: dict, trend: str = "NEUTRAL") -> dict:
    market = card.get("market") or {}
    decision = card.get("decision") or {}
    combined = card.get("combined") or {}
    ensemble = (card.get("pattern") or {}).get("ensemble") or {}
    execution = card.get("execution") or {}

    action = decision.get("action")
    side = (decision.get("side") or "").upper() or None
    if action == "BUY_YES":
        side = "YES"
    elif action == "BUY_NO":
        side = "NO"

    yes_ask = float((market.get("yes") or {}).get("ask") or 1.0)
    no_ask = float((market.get("no") or {}).get("ask") or 1.0)
    p_yes = combined.get("pYes")
    p_no = combined.get("pNo")
    if p_yes is None:
        p_yes = ensemble.get("closeAboveStrikeProb")
    if p_no is None:
        p_no = ensemble.get("closeBelowStrikeProb")
    p_yes = float(p_yes) if p_yes is not None else 0.0
    p_no = float(p_no) if p_no is not None else 0.0
    conflict = bool(combined.get("conflict"))

    # G1 Gate: Long-Only strategy — ONLY allow BUY_YES (side YES). BUY_NO is disabled.
    g1 = (action == "BUY_YES") and (side == "YES")
    g2 = not conflict
    if side == "YES":
        edge = p_yes - yes_ask
        g3 = p_yes > yes_ask + EDGE_BUFFER
        ask = yes_ask
        p_side = p_yes
    else:
        edge = 0.0
        g3 = False
        ask = None
        p_side = None

    # G5 Hard Trend Filter: BUY_YES only in UP trend.
    g5 = (side == "YES" and trend == "UP")

    # G4 Evidence Quality & G6 Market Structure Regime Filter
    evidence_quality = card.get("evidenceQuality") or {}
    grade = (evidence_quality.get("grade") or "OK").upper()
    score = float(evidence_quality.get("score") or 1.0)
    g4 = (grade not in ("THIN", "WEAK")) and (score >= 0.50)

    market_structure = card.get("marketStructure") or {}
    ms_trend = (market_structure.get("trend") or "").upper()
    g6 = (ms_trend != "CHOP")

    entry_max = decision.get("entryPriceMax")
    price_ok = True
    if entry_max is not None and ask is not None:
        price_ok = ask <= float(entry_max) + 1e-9

    execute = bool(g1 and g2 and g3 and price_ok and g5 and g4 and g6)

    skip_reasons = decision.get("skipReasons") or decision.get("summary")
    extra_reasons = []
    if not g5:
        extra_reasons.append(f"G5 trend filter failed: side={side} requires trend={'UP' if side=='YES' else 'DOWN'}, but current trend is '{trend}'.")
    if not g4:
        extra_reasons.append(f"G4 quality filter failed: evidence grade={grade}, score={score:.2f}.")
    if not g6:
        extra_reasons.append(f"G6 regime filter failed: market structure trend is '{ms_trend}'.")

    if extra_reasons:
        msg_str = "; ".join(extra_reasons)
        if isinstance(skip_reasons, list):
            skip_reasons.extend(extra_reasons)
        elif skip_reasons:
            skip_reasons = f"{skip_reasons}; {msg_str}"
        else:
            skip_reasons = msg_str

    return {
        "execute": execute,
        "g1": g1,
        "g2": g2,
        "g3": g3,
        "g4": g4,
        "g5": g5,
        "g6": g6,
        "price_ok": price_ok,
        "action": action,
        "side": side,
        "ask": ask,
        "p_side": p_side,
        "edge": edge,
        "conflict": conflict,
        "confidence": combined.get("confidence"),
        "title": market.get("title"),
        "slug": market.get("slug"),
        "strike": market.get("strikePrice"),
        "btc": market.get("currentPrice"),
        "entry_max": entry_max,
        "ttc": market.get("timeToCloseMinutes"),
        "execution_edge_yes": execution.get("edgeYes"),
        "execution_edge_no": execution.get("edgeNo"),
        "skip_reasons": skip_reasons,
    }


def cancel_open_orders(client) -> None:
    try:
        orders = client.get_open_orders()
        if not orders:
            return
        ids = []
        for o in orders:
            oid = o.get("id") or o.get("orderID") or o.get("order_id")
            if oid:
                ids.append(oid)
        if not ids:
            logger.info("Open orders present but no ids: %s", orders)
            return
        logger.warning("Cancelling %d open order(s): %s", len(ids), ids)
        try:
            client.cancel_orders(ids)
        except Exception:
            for oid in ids:
                try:
                    client.cancel_order(oid)
                except Exception as e:
                    logger.error("cancel %s failed: %s", oid, e)
    except Exception as e:
        logger.error("get/cancel open orders failed: %s", e)


def resolve_token_id(slug: str, side: str) -> str:
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    markets = requests.get(url, timeout=15).json()
    if not markets:
        raise ValueError(f"No market for slug {slug}")
    market_data = markets[0]
    clob_tokens = json.loads(market_data.get("clobTokenIds", "[]"))
    outcomes = json.loads(market_data.get("outcomes", "[]"))
    mapping = {}
    for i, token_id in enumerate(clob_tokens):
        if i < len(outcomes):
            mapping[str(outcomes[i]).upper()] = token_id
    if len(clob_tokens) >= 2:
        mapping.setdefault("YES", clob_tokens[0])
        mapping.setdefault("NO", clob_tokens[1])
        mapping.setdefault("UP", clob_tokens[0])
        mapping.setdefault("DOWN", clob_tokens[1])
    token = mapping.get(side.upper())
    if not token:
        raise ValueError(f"No token for side {side} outcomes={outcomes}")
    return token


def execute_market_buy(client, slug: str, side: str, usd_amount: float) -> dict:
    """FOK-style market buy for ~usd_amount USDC notional (fills immediately)."""
    token_id = resolve_token_id(slug, side)
    logger.info("Market BUY %s token=%s amount=$%.2f", side, token_id[:16] + "...", usd_amount)
    mo = MarketOrderArgs(token_id=token_id, amount=float(usd_amount), side="BUY")
    return client.create_and_post_market_order(mo)


def save_state(payload: dict) -> None:
    payload["ts_utc"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(payload, f, indent=2)


def persist_cycle(result: dict, card: dict | None = None) -> None:
    """Write JSON state + SQLite ledger row (never break trading on DB errors)."""
    if "ts_utc" not in result:
        result["ts_utc"] = datetime.now(timezone.utc).isoformat()
    save_state(result)
    try:
        row_id = record_cycle(result, card=card)
        logger.info("DB: recorded cycle id=%s final=%s slug=%s", row_id, result.get("final"), result.get("slug"))
    except Exception as e:
        logger.error("DB: record_cycle failed: %s", e)


def run_one_cycle(bot: PolymarketAgentBot) -> dict:
    global _last_traded_slug
    result = {"final": "ERROR"}
    card = None
    try:
        client = get_client()
    except Exception as e:
        logger.error("client init failed: %s", e)
        result["error"] = str(e)
        persist_cycle(result, card)
        return result

    usdc = bot.get_usdc_balance(client)
    # Cancel only residual unfilled GTC from prior cycles (before new decision)
    cancel_open_orders(client)

    raw = bot.get_live_decision()
    card = unpack_card(raw)
    if not card:
        logger.error("No decision card")
        result["final"] = "SKIP_NO_CARD"
        persist_cycle(result, card)
        return result

    market = card.get("market") or {}
    strike = market.get("strikePrice")
    btc = market.get("currentPrice")
    slug = market.get("slug")
    if strike and btc:
        trend = bot.update_history_and_get_trend(strike, btc)
    else:
        trend = "NEUTRAL"

    ev = evaluate_v2(card, trend=trend)
    ev["trend"] = trend
    ev["usdc"] = usdc
    result.update(ev)

    logger.info(
        "=== CYCLE %s | %s | strike=%s btc=%s trend=%s usdc=$%.2f ===",
        market.get("title"),
        ev.get("action"),
        strike,
        btc,
        trend,
        usdc,
    )
    logger.info(
        "Gates G1=%s G2=%s G3=%s G4(quality)=%s G5(trend)=%s G6(regime)=%s price_ok=%s | side=%s p=%.4f ask=%s edge=%.4f conf=%s",
        ev["g1"],
        ev["g2"],
        ev["g3"],
        ev["g4"],
        ev["g5"],
        ev["g6"],
        ev["price_ok"],
        ev.get("side"),
        ev.get("p_side") or 0.0,
        ev.get("ask"),
        ev.get("edge") or 0.0,
        ev.get("confidence"),
    )

    if slug and slug == _last_traded_slug:
        logger.info("Already traded this slug %s — skip duplicate", slug)
        result["final"] = "SKIP_DUP_SLUG"
        persist_cycle(result, card)
        return result

    if usdc < MIN_BALANCE:
        logger.warning("Balance $%.2f < $%.2f — dry-run only", usdc, MIN_BALANCE)
        result["final"] = "SKIP_LOW_BALANCE"
        persist_cycle(result, card)
        return result

    if not ev["execute"]:
        logger.info("SKIP — hard gates failed or AIPP SKIP. %s", ev.get("skip_reasons"))
        result["final"] = "SKIP"
        persist_cycle(result, card)
        return result

    side = ev["side"]
    amount = min(ALLOCATED_USD, usdc)
    logger.info("EXECUTE MARKET BUY_%s $%.2f on %s", side, amount, slug)
    try:
        resp = execute_market_buy(client, slug, side, amount)
        logger.info("ORDER RESPONSE: %s", json.dumps(resp, default=str))
        result["order"] = resp
        status = str((resp or {}).get("status") or "").lower()
        if status == "matched" or (resp or {}).get("takingAmount"):
            result["final"] = "EXECUTED"
            _last_traded_slug = slug
        else:
            # unfilled residual — cancel immediately (no toxic GTC)
            logger.warning("Order not matched (status=%s) — cancelling residuals", status)
            time.sleep(0.5)
            cancel_open_orders(client)
            result["final"] = "UNFILLED_CANCELLED"
            _last_traded_slug = slug  # don't re-spam same window
    except Exception as e:
        logger.error("Execution failed: %s", e)
        result["final"] = "EXEC_ERROR"
        result["error"] = str(e)
        cancel_open_orders(client)

    persist_cycle(result, card)
    return result


def main():
    logger.info("Starting balanced-v2 cycle runner (EDGE_BUFFER=%.2f, size=$%.0f)", EDGE_BUFFER, ALLOCATED_USD)
    try:
        init_db()
        logger.info("SQLite ledger ready: %s", os.path.join(os.path.dirname(__file__), "trades.db"))
    except Exception as e:
        logger.error("SQLite init failed (will retry on write): %s", e)
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)
        logger.info("Removed stale STOP file")

    bot = PolymarketAgentBot()
    cycles = 0

    # Start at next boundary by default (avoids double-trading mid-window restarts).
    # Set RUN_IMMEDIATE=1 to force a mid-window cycle on startup.
    if os.environ.get("RUN_IMMEDIATE", "0") == "1":
        try:
            raw = bot.get_live_decision()
            card = unpack_card(raw)
            ttc = float((card.get("market") or {}).get("timeToCloseMinutes") or 0)
            if ttc >= 3.0:
                logger.info("Immediate mid-window cycle (TTC=%.1f min)", ttc)
                run_one_cycle(bot)
                cycles += 1
            else:
                logger.info("Near expiry (TTC=%.1f) — wait for next boundary", ttc)
        except Exception as e:
            logger.warning("Immediate cycle probe failed: %s", e)
    else:
        logger.info("Startup: waiting for next 15m boundary (set RUN_IMMEDIATE=1 to trade now)")

    while _running:
        if os.path.exists(STOP_FILE):
            logger.info("STOP file present — exiting")
            break
        if MAX_CYCLES and cycles >= MAX_CYCLES:
            logger.info("MAX_CYCLES=%s reached — exiting", MAX_CYCLES)
            break

        wait = seconds_to_next_boundary()
        logger.info("Sleeping %.0fs until next 15m open+buffer", wait)
        end = time.time() + wait
        while _running and time.time() < end:
            if os.path.exists(STOP_FILE):
                break
            time.sleep(min(5.0, max(0.5, end - time.time())))

        if not _running or os.path.exists(STOP_FILE):
            break

        try:
            run_one_cycle(bot)
            cycles += 1
        except Exception as e:
            logger.exception("Cycle crashed: %s", e)
            persist_cycle({"final": "CRASH", "error": str(e)})

    logger.info("Cycle runner stopped after %s cycles", cycles)


if __name__ == "__main__":
    main()
