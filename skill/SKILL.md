---
name: polymarket-pattern-trader
description: Skill for running the autonomous 15m Bitcoin pattern trading strategy on Polymarket (balanced v2 — higher trade frequency). The agent is the decision maker; the Python bot is pure execution.
---

# Polymarket Pattern Trader Skill (balanced v2)

This skill enables the agent to act as the **sole decision maker** for 15-minute Bitcoin Up/Down contracts on Polymarket.

**Design goal (v2):** trade **more often** by trusting the AIPP live binary signal, while keeping only the EV-critical hard filters. Pattern quality and local trend are **soft** context (logging / conviction), not hard vetoes.

The Python bot is a pure execution layer — it does **not** make trading decisions.

**Project path (this machine):** `/Users/serg/projects/my_trading/aipp-trading`

---

## Why balanced v2

Legacy v1 used 5 hard gates (including Sharpe ≥ 1.0, WR ≥ 55% on a **75m** pattern proof, plus hard trend alignment and conviction ≥ 4/8). That stack killed frequency and filtered the wrong horizon.

Historical live lesson (GBRAIN, aging): heavy aipp filters underperformed a simpler always-on AIPP path. Consensus-style over-filtering → near-zero trades.

**v2 rule of thumb:** if AIPP says BUY and there is real edge after the ask, take the $5 trade. Soft signals only document quality and size later — they do not block.

---

## Phase 1: Data Collection (run all queries first)

Every 15 minutes, collect ALL signals in parallel before deciding:

### 1. Balance / connection
```bash
python3 /Users/serg/projects/my_trading/aipp-trading/polymarket_executor.py --test
# or
python3 /Users/serg/projects/my_trading/aipp-trading/polymarket_agent_bot.py --dry-run
```
Confirm USDC balance ≥ **$5.00**. If below, SKIP and notify.

### 2. Live Binary Signal (PRIMARY)
Query `get_live_polymarket_trade_decision` for `BTCUSDT` (`interval=15m`).

Extract:
- `market.title`, `market.slug`, `market.strikePrice`, `market.currentPrice`
- `market.yes.ask`, `market.no.ask`
- `market.timeToCloseMinutes`, `decisionMode` (`standard` | `near_expiry`)
- `pattern.ensemble.closeAboveStrikeProb` / `closeBelowStrikeProb`
- `combined.direction`, `combined.confidence`, `combined.conflict`, `combined.pYes`, `combined.pNo`
- `intrabar.momentumSignal`, `intrabar.confidence`
- `decision.action` — BUY_YES / BUY_NO / SKIP
- `decision.entryPriceMax`, `decision.skipReasons`
- `execution.edgeYes`, `execution.edgeNo`

### 3. Pattern quality (SOFT context only)
Query `get_trading_decision` for `BTCUSDT`, `interval=15m`, `q=40`, `f=3`, `includeBacktest=true`, `feePct=0`, `slippagePct=0`.

> **⚠️ Two-source architecture — do NOT confuse these tools**
>
> | Tool | Purpose | Horizon | Use for |
> |---|---|---|---|
> | `get_live_polymarket_trade_decision` | Binary P(close > strike) | **15 min** ✅ | **Primary signal & direction** |
> | `get_trading_decision` proof | Pattern LONG/SHORT quality | **~75 min** | **Soft context / conviction ONLY** |
>
> `proof.stats.winRate` is **not** the binary outcome probability. Never hard-block a 15m trade solely because the 75m proof is weak.
>
> Prefer `combined.pYes` / `combined.pNo` (or ensemble probs) for G3 edge math when AIPP fuses pattern + intrabar.

Extract for logging:
- `evidenceQuality.grade`, `evidenceQuality.score`
- `proof.stats.winRate`, `proof.stats.sharpeRatio`, `proof.verdict`
- `final.direction`, `metrics.regime`

### 4. Local trend (SOFT)
Read `strike_history.json` in the project root (bot also maintains it on dry-run / live):
- `UP` if last 3 strikes are sequentially rising
- `DOWN` if last 3 strikes are sequentially falling
- else `NEUTRAL`

---

## Phase 2: Deliberate Decision

Reason through gates out loud, then print the decision summary.

### Hard Gates — ALL must pass to EXECUTE

| # | Gate | Condition | Fail |
|---|---|---|---|
| **G1** | **AIPP live verdict** | `decision.action` ∈ {BUY_YES, BUY_NO} | SKIP |
| **G2** | **No conflict** | `combined.conflict` = false | SKIP |
| **G3** | **Binary edge vs ask** | Prefer fused probs: for YES use `combined.pYes` (fallback `closeAboveStrikeProb`) > `ask_yes + 0.02`; for NO use `combined.pNo` (fallback `closeBelowStrikeProb`) > `ask_no + 0.02` | SKIP |

Also require:
- Balance ≥ $5
- `ask ≤ decision.entryPriceMax` when AIPP provides `entryPriceMax`
- Do **not** force-trade when AIPP says SKIP

> **G3 example:** YES ask $0.53 → need pYes > 0.55. NO ask $0.48 → need pNo > 0.50.

### Soft signals (do NOT hard-block)

Use these only for the conviction scorecard, logging, and optional future size tiers:

| Signal | Soft effect |
|---|---|
| Evidence THIN/WEAK | − conviction; still allow trade if G1–G3 pass |
| Proof Sharpe / WR / FAILED | − conviction; **never** hard veto |
| Local trend opposite to side | − conviction; **never** hard veto |
| Pattern direction vs live side mismatch | note in summary; **never** hard veto |
| High combined confidence / aligned intrabar | + conviction |

### Conviction Scorecard (logging only — NOT required to execute)

```
Signal strength (informational):
  + combined.confidence > 0.35           → +2
  + combined.confidence > 0.20           → +1
  + intrabar aligns with trade side      → +1
  + regime supports side (uptrend/YES or downtrend/NO) → +1
  + local trend aligns with side         → +1
  - evidenceQuality THIN/WEAK            → -1
  - proof.sharpeRatio < 0                → -1
  - local trend opposes side             → -1

Conviction is for the summary only.
If G1–G3 pass → EXECUTE even at low conviction (default size $5).
```

Optional later (only after 30+ live trades with stats):
- conviction ≤ 1 → keep $5 or skip discretionary
- conviction ≥ 4 → still $5 until proven (no size-up yet)

### Required Agent Decision Summary

```
=== DECISION SUMMARY [Iteration N] ===
Framework: balanced v2
Market: [title]
Strike: [price] | BTC Now: [price] | Trend: [UP/DOWN/NEUTRAL] (soft)
TTC: [min] | Mode: [standard|near_expiry]

Signal Analysis:
  AIPP verdict:         [BUY_YES/BUY_NO/SKIP]
  pYes (combined/ens):  [X%]  (YES ask: $X)  → Edge: [+/-X]
  pNo  (combined/ens):  [X%]  (NO ask: $X)   → Edge: [+/-X]
  Combined confidence:  [X] | Conflict: [yes/no]
  Intrabar momentum:    [BULLISH/BEARISH/NEUTRAL]

Pattern Quality (soft only):
  Evidence grade:       [THIN/OK/MEDIUM/STRONG]
  Backtest Sharpe:      [X]   (soft — not a hard gate)
  Backtest WinRate:     [X%]  (soft — not a hard gate)
  Backtest direction:   [LONG/SHORT] → aligns: [yes/no/n/a]
  Pattern regime:       [regime]

Hard Gates:
  G1 AIPP verdict:      [PASS/FAIL]
  G2 No conflict:       [PASS/FAIL]
  G3 Binary edge:       [PASS/FAIL]

Conviction (info):      [X] — does not block
FINAL DECISION:         [EXECUTE / SKIP] — reason: [...]
======================================
```

---

## Phase 3: Execution

### If EXECUTE (G1–G3 all PASS):
```bash
python3 /Users/serg/projects/my_trading/aipp-trading/polymarket_agent_bot.py
```
Then verify open orders:
```python
from polymarket_executor import get_client
client = get_client()
print(client.get_open_orders())
```

### If SKIP:
```bash
python3 /Users/serg/projects/my_trading/aipp-trading/polymarket_agent_bot.py --dry-run
```
Updates `strike_history.json` without placing an order.

> **⚠️ Stale GTC orders:** if a limit order is placed and not filled (`size_matched: 0`), cancel before expiry:
> ```python
> client.cancel_orders([order_id])
> ```
> Unfilled orders near expiry can get toxic fills.

---

## Sizing & risk

- Default size: **$5.00 USDC** per trade (~integer shares at ask)
- One market at a time; check open orders every cycle
- Never size up until **30+ live trades** with documented positive expectancy
- Only **15m** BTC Up/Down (not 5m — spreads kill small edges)

---

## Quick reference: when to trade

| Situation | Action |
|---|---|
| AIPP BUY_* + no conflict + p > ask+2% | **EXECUTE $5** |
| AIPP SKIP | **SKIP** (never force) |
| conflict = true | **SKIP** |
| Weak 75m proof / THIN evidence | **Still EXECUTE** if G1–G3 pass (log soft flags) |
| Trend opposes side | **Still EXECUTE** if G1–G3 pass (log soft flags) |
| Balance < $5 | **SKIP** |
