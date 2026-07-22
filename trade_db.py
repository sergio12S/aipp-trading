#!/usr/bin/env python3
"""
SQLite trade ledger for aipp-trading cycle_runner.

DB path: trades.db (project root). Schema is auto-created.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import requests

DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    slug TEXT,
    title TEXT,
    market_id TEXT,
    action TEXT,
    side TEXT,
    strike REAL,
    btc REAL,
    ttc REAL,
    p_side REAL,
    p_yes REAL,
    p_no REAL,
    ask REAL,
    edge REAL,
    confidence REAL,
    conflict INTEGER,
    trend TEXT,
    g1 INTEGER,
    g2 INTEGER,
    g3 INTEGER,
    price_ok INTEGER,
    usdc_free REAL,
    final TEXT NOT NULL,
    order_id TEXT,
    making_usd REAL,
    taking_shares REAL,
    order_status TEXT,
    error TEXT,
    skip_reasons TEXT,
    decision_mode TEXT,
    entry_max REAL,
    outcome TEXT,
    close_price REAL,
    resolved_at TEXT,
    pnl_usd REAL,
    win INTEGER,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_cycles_slug ON cycles(slug);
CREATE INDEX IF NOT EXISTS idx_cycles_final ON cycles(final);
CREATE INDEX IF NOT EXISTS idx_cycles_ts ON cycles(ts_utc);
CREATE INDEX IF NOT EXISTS idx_cycles_outcome ON cycles(outcome);
CREATE INDEX IF NOT EXISTS idx_cycles_side ON cycles(side);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def _bool_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    return 1 if v else 0


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _skip_reasons_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def record_cycle(result: dict, card: Optional[dict] = None, db_path: str = DB_PATH) -> int:
    """Insert one cycle decision/execution row. Returns row id."""
    init_db(db_path)
    market = (card or {}).get("market") or {}
    combined = (card or {}).get("combined") or {}
    order = result.get("order") or {}

    making = _f(order.get("makingAmount"))
    taking = _f(order.get("takingAmount"))
    # fallback: explicit fields if set by runner
    if making is None:
        making = _f(result.get("making_usd"))
    if taking is None:
        taking = _f(result.get("taking_shares"))

    p_yes = _f(combined.get("pYes"))
    p_no = _f(combined.get("pNo"))
    if p_yes is None and result.get("side") == "YES":
        p_yes = _f(result.get("p_side"))
    if p_no is None and result.get("side") == "NO":
        p_no = _f(result.get("p_side"))

    row = {
        "ts_utc": result.get("ts_utc") or utc_now_iso(),
        "slug": result.get("slug") or market.get("slug"),
        "title": result.get("title") or market.get("title"),
        "market_id": str(market.get("marketId") or result.get("market_id") or "") or None,
        "action": result.get("action"),
        "side": result.get("side"),
        "strike": _f(result.get("strike") if result.get("strike") is not None else market.get("strikePrice")),
        "btc": _f(result.get("btc") if result.get("btc") is not None else market.get("currentPrice")),
        "ttc": _f(result.get("ttc") if result.get("ttc") is not None else market.get("timeToCloseMinutes")),
        "p_side": _f(result.get("p_side")),
        "p_yes": p_yes,
        "p_no": p_no,
        "ask": _f(result.get("ask")),
        "edge": _f(result.get("edge")),
        "confidence": _f(result.get("confidence")),
        "conflict": _bool_int(result.get("conflict")),
        "trend": result.get("trend"),
        "g1": _bool_int(result.get("g1")),
        "g2": _bool_int(result.get("g2")),
        "g3": _bool_int(result.get("g3")),
        "price_ok": _bool_int(result.get("price_ok")),
        "usdc_free": _f(result.get("usdc")),
        "final": result.get("final") or "UNKNOWN",
        "order_id": order.get("orderID") or order.get("order_id") or result.get("order_id"),
        "making_usd": making,
        "taking_shares": taking,
        "order_status": order.get("status") or result.get("order_status"),
        "error": result.get("error"),
        "skip_reasons": _skip_reasons_str(result.get("skip_reasons")),
        "decision_mode": (card or {}).get("decisionMode") or result.get("decision_mode"),
        "entry_max": _f(result.get("entry_max")),
        "raw_json": json.dumps(
            {"result": _jsonable(result), "card_summary": _card_summary(card)},
            ensure_ascii=False,
            default=str,
        ),
    }

    cols = list(row.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_sql = ", ".join(cols)
    with connect(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO cycles ({col_sql}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )
        return int(cur.lastrowid)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items() if k != "order" or True}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _card_summary(card: Optional[dict]) -> Optional[dict]:
    if not card:
        return None
    market = card.get("market") or {}
    decision = card.get("decision") or {}
    combined = card.get("combined") or {}
    return {
        "decisionMode": card.get("decisionMode"),
        "marketId": market.get("marketId"),
        "slug": market.get("slug"),
        "action": decision.get("action"),
        "combined": combined,
    }


def fetch_gamma_market(slug: str) -> Optional[dict]:
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        markets = r.json()
        if not markets:
            return None
        return markets[0]
    except Exception:
        return None


def infer_outcome_from_market(market: dict, strike: Optional[float] = None) -> tuple[Optional[str], Optional[float]]:
    """
    Returns (outcome YES/NO, close_price if known).
    Prefer explicit resolution; fall back to closed + price comparison when possible.
    """
    if not market:
        return None, None

    # closed flag
    closed = market.get("closed")
    if isinstance(closed, str):
        closed = closed.lower() in ("true", "1", "yes")

    # outcomePrices: ["1","0"] or similar when resolved
    outcome_prices = market.get("outcomePrices")
    outcomes = market.get("outcomes")
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except Exception:
            outcome_prices = None
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = None

    if outcome_prices and outcomes and len(outcome_prices) == len(outcomes):
        try:
            prices = [float(x) for x in outcome_prices]
            # winner ≈ 1.0
            best_i = max(range(len(prices)), key=lambda i: prices[i])
            if prices[best_i] >= 0.9:
                label = str(outcomes[best_i]).upper()
                if label in ("UP", "YES"):
                    return "YES", None
                if label in ("DOWN", "NO"):
                    return "NO", None
                return label, None
        except Exception:
            pass

    # umaResolutionStatus / resolved
    res = (market.get("umaResolutionStatus") or market.get("resolution") or "").upper()
    if "YES" in res or res == "UP":
        return "YES", None
    if "NO" in res or res == "DOWN":
        return "NO", None

    return None, None


def compute_pnl(side: Optional[str], making_usd: Optional[float], taking_shares: Optional[float], outcome: str) -> tuple[Optional[float], Optional[int]]:
    if not side or not outcome:
        return None, None
    side = side.upper()
    outcome = outcome.upper()
    win = 1 if side == outcome else 0
    if making_usd is None:
        return None, win
    if win:
        # binary share redeems $1 each
        shares = taking_shares if taking_shares is not None else 0.0
        # if taking missing, approximate shares ≈ making/ask not available → use making as cost only
        if taking_shares is None:
            return None, win
        pnl = float(shares) * 1.0 - float(making_usd)
    else:
        pnl = -float(making_usd)
    return pnl, win


def resolve_pending(db_path: str = DB_PATH, limit: int = 200, force_min_age_minutes: float = 16.0) -> dict:
    """
    Resolve EXECUTED rows without outcome via Gamma.
    Only attempts rows older than force_min_age_minutes (default ~one bar).
    """
    init_db(db_path)
    now = datetime.now(timezone.utc)
    resolved_n = 0
    skipped_n = 0
    errors = []

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, slug, side, strike, making_usd, taking_shares, ts_utc, final
            FROM cycles
            WHERE final = 'EXECUTED'
              AND outcome IS NULL
              AND slug IS NOT NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        for row in rows:
            ts = row["ts_utc"]
            try:
                # allow Z
                ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                age_min = (now - ts_dt).total_seconds() / 60.0
            except Exception:
                age_min = 9999

            if age_min < force_min_age_minutes:
                skipped_n += 1
                continue

            market = fetch_gamma_market(row["slug"])
            if not market:
                errors.append(f"id={row['id']} gamma miss slug={row['slug']}")
                continue

            outcome, close_px = infer_outcome_from_market(market, row["strike"])
            if not outcome:
                # market not resolved yet
                skipped_n += 1
                continue

            pnl, win = compute_pnl(row["side"], row["making_usd"], row["taking_shares"], outcome)
            conn.execute(
                """
                UPDATE cycles
                SET outcome = ?, close_price = ?, resolved_at = ?, pnl_usd = ?, win = ?
                WHERE id = ?
                """,
                (outcome, close_px, utc_now_iso(), pnl, win, row["id"]),
            )
            resolved_n += 1

    return {"resolved": resolved_n, "skipped": skipped_n, "errors": errors}


def stats_summary(db_path: str = DB_PATH) -> dict:
    init_db(db_path)
    with connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM cycles").fetchone()["n"]
        by_final = {
            r["final"]: r["n"]
            for r in conn.execute("SELECT final, COUNT(*) AS n FROM cycles GROUP BY final")
        }
        executed = conn.execute(
            "SELECT COUNT(*) AS n FROM cycles WHERE final = 'EXECUTED'"
        ).fetchone()["n"]
        resolved = conn.execute(
            "SELECT COUNT(*) AS n FROM cycles WHERE outcome IS NOT NULL"
        ).fetchone()["n"]
        wins = conn.execute(
            "SELECT COUNT(*) AS n FROM cycles WHERE win = 1"
        ).fetchone()["n"]
        losses = conn.execute(
            "SELECT COUNT(*) AS n FROM cycles WHERE win = 0"
        ).fetchone()["n"]
        pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) AS s FROM cycles WHERE pnl_usd IS NOT NULL"
        ).fetchone()["s"]
        by_side = []
        for r in conn.execute(
            """
            SELECT side,
                   COUNT(*) AS n,
                   SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN win = 0 THEN 1 ELSE 0 END) AS losses,
                   COALESCE(SUM(pnl_usd), 0) AS pnl
            FROM cycles
            WHERE final = 'EXECUTED' AND outcome IS NOT NULL
            GROUP BY side
            """
        ):
            by_side.append(dict(r))
        edge_buckets = []
        for r in conn.execute(
            """
            SELECT
              CASE
                WHEN edge IS NULL THEN 'unknown'
                WHEN edge < 0.08 THEN 'thin_<0.08'
                WHEN edge < 0.15 THEN 'mid_0.08_0.15'
                ELSE 'fat_>=0.15'
              END AS bucket,
              COUNT(*) AS n,
              SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END) AS wins,
              COALESCE(SUM(pnl_usd), 0) AS pnl
            FROM cycles
            WHERE final = 'EXECUTED' AND outcome IS NOT NULL
            GROUP BY bucket
            """
        ):
            edge_buckets.append(dict(r))

    wr = (wins / (wins + losses)) if (wins + losses) else None
    return {
        "total_cycles": total,
        "by_final": by_final,
        "executed": executed,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "pnl_usd": pnl,
        "by_side": by_side,
        "edge_buckets": edge_buckets,
    }


def print_stats(db_path: str = DB_PATH) -> None:
    s = stats_summary(db_path)
    print("=== trades.db stats ===")
    print(f"total cycles:  {s['total_cycles']}")
    print(f"by final:      {s['by_final']}")
    print(f"executed:      {s['executed']}")
    print(f"resolved:      {s['resolved']}  (W/L {s['wins']}/{s['losses']})")
    if s["win_rate"] is not None:
        print(f"win rate:      {100*s['win_rate']:.1f}%")
    print(f"sum pnl_usd:   {s['pnl_usd']:.4f}")
    print("by side:")
    for r in s["by_side"]:
        n = r["n"] or 0
        w = r["wins"] or 0
        wr = (100 * w / n) if n else 0
        print(f"  {r['side']}: n={n} wins={w} losses={r['losses']} wr={wr:.1f}% pnl={r['pnl']:.4f}")
    print("by edge bucket:")
    for r in s["edge_buckets"]:
        n = r["n"] or 0
        w = r["wins"] or 0
        wr = (100 * w / n) if n else 0
        print(f"  {r['bucket']}: n={n} wins={w} wr={wr:.1f}% pnl={r['pnl']:.4f}")
