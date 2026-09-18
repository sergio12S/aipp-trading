# Research: notable Polymarket BTC 15m wallets

**As of:** 2026-09-17 (Europe/Zurich)  
**Method:** `sortBy=TIMESTAMP` closed-positions via `polymarket-trader-intel` (`closed-pnl`, ~200 rows). Default API PnL sort inflates winrate.  
**Not financial advice / not copy-trade.**

Primary (Russian, full case studies): [research-btc15m-earners.ru.md](research-btc15m-earners.ru.md)  
Adaptation notes: [adapt-from-earners.ru.md](adapt-from-earners.ru.md)

## Buckets

| Bucket | Example | For AIPP |
|--------|---------|----------|
| Favorite scrape | xloong, ea59 (WR~100%, avg px 0.84–0.93) | Anti-pattern → **G4 ASK_MAX** |
| Late sniper | maxmaxi04 (~+$2.9k N=28, conc~0.42) | Timing bucket later |
| Mid directional | deepmoat (~64% WR, avg px~0.59) | Closest fit → G4 mid-band |
| Underdog | elyash (avg px~0.44) | G3 edge, not longshot size |
| Complete-set / MM | gabagool22 | Not for $1 open-window |
| New / noisy | Flyinghippo08, magmaalpha | Min N / age |

## Snapshot table (TIMESTAMP ~200 rows)

| Name | Wallet | N | WR | PnL | Avg px |
|------|--------|--:|---:|----:|-------:|
| maxmaxi04 | `0x10d57bd3…5388` | 28 | 96% | +2901 | 0.79 |
| deepmoat | `0xc6accd5b…3778` | 42 | 64% | +245 | 0.59 |
| ea59 | `0xea592960…f29d` | 200 | 100% | +1705 | 0.84 |
| xloong | `0x31e6cdd9…620f` | 200 | 100% | +58 | 0.93 |
| gabagool22 | `0x6031b6ee…f96d` | 24 | 50% | −98 | 0.51 |

## Live adaptation

G4 `ASK_MAX=0.70`, `GATE_SHADOW=1` on `aipp-trading` cycle_runner.
