# Research: notable Polymarket BTC 15m wallets

**As of:** 2026-09-17 (Europe/Zurich)
**Method:** `sortBy=TIMESTAMP` closed-positions via `polymarket-trader-intel`.
**Not financial advice / not copy-trade.**

## Buckets

| Bucket | Example | For AIPP |
|--------|---------|----------|
| Favorite scrape | high WR, avg px 0.84–0.93 | Anti-pattern → **G7 ASK_MAX** |
| Late sniper | large PnL, end-of-window | Timing bucket later |
| Mid directional | ~60% WR, avg px ~0.55–0.65 | Closest fit → G7 mid-band |
| Complete-set / MM | both sides | Not for $1 open-window |

## Live adaptation

G7 `ASK_MAX=0.70`, `GATE_SHADOW=1` on `aipp-trading` cycle_runner.
Remote G4=quality, G5=trend, G6=regime stay unchanged.
