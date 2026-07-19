---
name: polymarket-pattern-trader
description: Skill for running the autonomous 15m Bitcoin pattern trading strategy on Polymarket. The agent acts as the decision maker, querying AIPP MCP tools, applying trend/backtest risk filters, and executing trades using the Python bot.
---

# Polymarket Pattern Trader Skill

This skill enables the agent to act as the **sole decision maker** for 15-minute Bitcoin prediction contracts on Polymarket. The agent gathers multi-source context, reasons explicitly about every signal, and only then issues execution commands. The Python bot is a pure execution layer — it does NOT make trading decisions.

---

## Phase 1: Data Collection (run all queries first)

Every 15 minutes when triggered by cron `task-536`, collect ALL signals in parallel before making any decision:

### 1. Balance Check
```bash
python3 /home/serg/projects/trading/polymarket_agent_bot.py --dry-run
```
Confirm balance ≥ $5.00 USDC. If below, skip and notify.

### 2. Live Binary Signal
Query `get_live_polymarket_trade_decision` for `BTCUSDT`.

Extract the following fields:
- `market.title`, `market.strikePrice`, `market.currentPrice`
- `market.yes.ask`, `market.no.ask` — actual prices to pay
- `pattern.ensemble.closeAboveStrikeProb` — P(BTC > strike at expiry)
- `pattern.ensemble.closeBelowStrikeProb` — P(BTC < strike at expiry)
- `combined.direction`, `combined.confidence`, `combined.conflict`
- `intrabar.momentumSignal`, `intrabar.confidence`
- `decision.action` — AIPP's own recommendation (BUY_YES / BUY_NO / SKIP)
- `execution.edgeYes`, `execution.edgeNo` — expected edge after spread

### 3. Pattern Quality Backtest
Query `get_trading_decision` for `BTCUSDT`, `interval=15m`, `q=40`, `f=3`, `includeBacktest=true`.

> **⚠️ CRITICAL: Two-Source Architecture — Do NOT confuse these tools**
>
> | Tool | Purpose | Horizon | Use for |
> |---|---|---|---|
> | `get_live_polymarket_trade_decision` | Binary P(close > strike) | **15 min** ✅ | **Primary signal & trade direction** |
> | `get_trading_decision` proof backtest | Historical pattern quality | **75 min** (5 bars × 15m) | **Pattern credibility filter ONLY** |
>
> `proof.stats.winRate` is NOT the probability of the binary outcome. It measures whether the pattern's LONG/SHORT direction was profitable over 75 minutes. Use it only to answer: *"Does this pattern have any historical statistical credibility?"*
>
> Always set `feePct=0`, `slippagePct=0` — we need the raw directional probability, not net P&L.

Extract:
- `evidenceQuality.grade` and `evidenceQuality.score`
- `proof.stats.winRate`, `proof.stats.sharpeRatio`, `proof.verdict`
- `final.direction` (LONG or SHORT) — must align with Polymarket signal direction
- `metrics.regime` — market regime context

---

## Phase 2: Deliberate Decision (agent must reason explicitly)

After collecting all data, the agent must **reason through each gate out loud** and produce a decision summary before executing anything.

### Hard Gates — ALL must pass to execute

| # | Gate | Condition | Fail action |
|---|---|---|---|
| G1 | **AIPP live verdict** | `decision.action` = BUY_YES or BUY_NO | SKIP |
| G2 | **No conflict** | `combined.conflict` = false | SKIP |
| G3 | **Binary probability edge** | `closeAboveStrikeProb` > ask_yes + 0.02 (for YES), or `closeBelowStrikeProb` > ask_no + 0.02 (for NO) | SKIP |
| G4 | **Pattern quality** | `evidenceQuality.grade` ≠ THIN/WEAK AND `proof.sharpeRatio` ≥ 1.0 AND `proof.winRate` ≥ 55% | SKIP |
| G5 | **Trend alignment** | BUY_YES allowed only if local trend ≠ DOWN; BUY_NO allowed only if local trend ≠ UP | SKIP |

> **G3 explanation:** If YES costs $0.53, we need `closeAboveStrikeProb` > 0.55 to have positive expected value. If NO costs $0.48, we need `closeBelowStrikeProb` > 0.50. Add a 2% buffer to be safe.

### Conviction Scorecard (for logging and transparency)

After checking gates, compute a conviction score to document your reasoning:

```
Signal strength:
  + combined.confidence > 0.35    → +2 pts  (strong)
  + combined.confidence > 0.20    → +1 pt   (moderate)
  + intrabar aligns with pattern  → +1 pt
  + regime is STABLE_UPTREND/DOWNTREND → +1 pt
  + local trend aligns            → +1 pt
  - combined.conflict = true      → -3 pts  (hard blocker)
  - evidenceQuality = THIN/WEAK   → -2 pts
  - proof.sharpeRatio < 0.5       → -2 pts
  - proof.sharpeRatio 0.5–1.0     → -1 pt

Minimum to execute: 4/8 points AND all hard gates passed.
```

### Required Agent Decision Summary

Before calling any execution command, always output a summary like this:

```
=== DECISION SUMMARY [Iteration N] ===
Market: [title]
Strike: [price] | BTC Now: [price] | Trend: [UP/DOWN/NEUTRAL]

Signal Analysis:
  AIPP verdict:         [BUY_YES/BUY_NO/SKIP]
  closeAboveStrikeProb: [X%]  (YES ask: $X)  → Edge: [+/-X]
  closeBelowStrikeProb: [X%]  (NO ask: $X)   → Edge: [+/-X]
  Combined confidence:  [X] | Conflict: [yes/no]
  Intrabar momentum:    [BULLISH/BEARISH/NEUTRAL]

Pattern Quality:
  Evidence grade:       [THIN/OK/MEDIUM/STRONG]
  Backtest Sharpe:      [X]   (threshold: ≥ 1.0)
  Backtest WinRate:     [X%]  (threshold: ≥ 55%)
  Backtest direction:   [LONG/SHORT] → aligns with signal: [yes/no]
  Pattern regime:       [regime]

Gate Results:
  G1 AIPP verdict:      [PASS/FAIL]
  G2 No conflict:       [PASS/FAIL]
  G3 Binary edge:       [PASS/FAIL]
  G4 Pattern quality:   [PASS/FAIL]
  G5 Trend alignment:   [PASS/FAIL]

Conviction score:       [X/8]
FINAL DECISION:         [EXECUTE / SKIP] — reason: [...]
======================================
```

---

## Phase 3: Execution

### If EXECUTE:
```bash
python3 /home/serg/projects/trading/polymarket_agent_bot.py
```
Then immediately verify no unintended open orders remain by checking:
```python
from polymarket_executor import get_client; client = get_client(); print(client.get_open_orders())
```

### If SKIP:
```bash
python3 /home/serg/projects/trading/polymarket_agent_bot.py --dry-run
```
This updates `strike_history.json` with the new strike for trend tracking, without placing any order.

> **⚠️ IMPORTANT:** If the bot returns a BUY signal but a limIt order was placed and NOT filled (`size_matched: 0`), cancel it immediately:
> ```python
> client.cancel_orders([order_id])
> ```
> A stale unfilled limit order near expiry can get a *toxic fill* when the price reverses.

---

## Reference: Local Trend Filter

The bot reads [strike_history.json](file:///home/serg/projects/trading/strike_history.json):
- Trend = `UP` if last 3 strikes are sequentially rising
- Trend = `DOWN` if last 3 strikes are sequentially falling
- Trend = `NEUTRAL` otherwise

Trade sizing: always $5.00 USDC (≈ 10 shares at $0.48–$0.53). Never size up until the strategy proves consistent profitability over 30+ trades.
