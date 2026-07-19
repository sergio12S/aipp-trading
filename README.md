# Polymarket BTC Pattern Trader

An autonomous AI agent that trades 15-minute Bitcoin Up/Down binary prediction contracts on [Polymarket](https://polymarket.com), using pattern-recognition signals from the [AI Price Patterns (AIPP)](https://aipricepatterns.com) MCP server.

The agent acts as the sole **decision maker** — it collects multi-source signals, reasons through 5 hard execution gates, computes a conviction scorecard, and only then instructs the Python execution layer to place a trade.

---

## Architecture

```
┌─────────────────────────────────────┐
│         AI Agent (Decision Maker)   │
│                                     │
│  1. get_live_polymarket_trade_decision  ← binary P(close > strike), 15m
│  2. get_trading_decision + backtest     ← pattern quality filter, 75m
│  3. Local trend filter                  ← strike_history.json
│                                     │
│  → 5 Hard Gates + Conviction Score  │
│  → EXECUTE or SKIP                  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     polymarket_agent_bot.py         │  ← pure execution layer
│     polymarket_executor.py          │  ← Polymarket CLOB client
└─────────────────────────────────────┘
```

### Key Design Principles

- **Agent = decision maker, bot = executor.** The Python bot never makes autonomous trading decisions. It only executes what the agent instructs.
- **Two-source signal architecture.** `get_live_polymarket_trade_decision` provides the binary outcome probability calibrated to the 15-minute window. `get_trading_decision` provides a pattern quality backtest (75-minute horizon) used only as a credibility filter — NOT as the directional signal.
- **Zero-fee backtests.** Backtests always run with `feePct=0, slippagePct=0` to measure the raw binary directional probability without spot P&L noise.
- **Minimal bet sizing.** $5.00 USDC per trade until the strategy proves consistent profitability over 30+ live trades.

---

## Files

| File | Description |
|---|---|
| `polymarket_agent_bot.py` | Main trading bot — fetches AIPP signal, checks trend, executes trade |
| `polymarket_executor.py` | Low-level Polymarket CLOB client wrapper (order creation, cancellation) |
| `strike_history.json` | Auto-managed local history of strike/close prices for trend calculation |
| `default.env.example` | Template for required credentials |
| `skill/SKILL.md` | Full agent decision framework (for Antigravity AI skill system) |

---

## Setup

### 1. Install dependencies

```bash
pip install python-dotenv requests py-clob-client-v2
```

### 2. Configure credentials

```bash
cp default.env.example default.env
# Edit default.env with your Polymarket API keys
```

To get Polymarket API keys, visit [docs.polymarket.com](https://docs.polymarket.com) and generate L2 API credentials from your wallet.

### 3. Test connection

```bash
python3 polymarket_executor.py --test
```

---

## Usage

### Dry run (no real trades, just logs signal + updates strike history)
```bash
python3 polymarket_agent_bot.py --dry-run
```

### Live trading (agent-controlled — see Decision Framework below)
```bash
python3 polymarket_agent_bot.py
```

> ⚠️ **Important:** Do not call the live mode directly without going through the agent decision framework. The bot will execute whatever signal AIPP returns at that moment, without the backtest quality filters.

---

## Agent Decision Framework

The AI agent follows a structured 3-phase process each 15-minute cycle:

### Phase 1 — Data Collection (parallel)
1. `get_live_polymarket_trade_decision` → binary signal + `closeAboveStrikeProb`
2. `get_trading_decision` (with backtest) → pattern quality (Sharpe, WinRate, Evidence grade)
3. Read `strike_history.json` → local trend (UP / DOWN / NEUTRAL)

### Phase 2 — Deliberate Decision

**5 Hard Gates — ALL must pass:**

| Gate | Condition |
|---|---|
| G1 | AIPP verdict = BUY_YES or BUY_NO |
| G2 | `combined.conflict` = false |
| G3 | Binary edge: `closeAboveStrikeProb > ask_yes + 2%` (or equivalent for NO) |
| G4 | Pattern quality: evidence grade ≠ THIN/WEAK AND Sharpe ≥ 1.0 AND WinRate ≥ 55% |
| G5 | Trend alignment: BUY_YES only if trend ≠ DOWN; BUY_NO only if trend ≠ UP |

**Conviction Scorecard (min 4/8 to execute):**
- `combined.confidence > 0.35` → +2 pts
- `combined.confidence > 0.20` → +1 pt
- Intrabar aligns with pattern → +1 pt
- Regime is STABLE_UP/DOWNTREND → +1 pt
- Local trend aligns → +1 pt
- `combined.conflict = true` → -3 pts
- Evidence grade THIN/WEAK → -2 pts
- Sharpe < 0.5 → -2 pts; Sharpe 0.5–1.0 → -1 pt

### Phase 3 — Execution

```bash
# If all gates pass AND conviction ≥ 4/8:
python3 polymarket_agent_bot.py

# Otherwise:
python3 polymarket_agent_bot.py --dry-run
```

After live execution, always verify no stale unmatched limit orders remain:
```python
from polymarket_executor import get_client
client = get_client()
print(client.get_open_orders())
# Cancel any unmatched orders before expiry to avoid toxic fills
```

---

## Autonomous Operation (Antigravity AI)

This bot is designed to run autonomously as an [Antigravity](https://antigravity.ai) AI skill. The skill definition lives in `skill/SKILL.md`.

To run the cron loop, start the scheduler in Antigravity CLI:
```
/schedule every 15 minutes: run the polymarket-pattern-trader skill
```

The agent will wake up every 15 minutes, collect signals, reason through the decision framework, and execute or skip accordingly.

---

## Important Notes

- **Stale limit orders:** Polymarket orders are GTC (Good Till Cancelled). If a limit order is placed but BTC price moves away, the order stays open. Always cancel unfilled orders before the contract expires to avoid toxic fills at adverse prices.
- **Spread break-even:** YES tokens bought at $0.53 require `closeAboveStrikeProb > 53%` to break even — before adding a safety buffer. The strategy only trades when there is a meaningful edge above the spread.
- **15m vs 5m:** The 15-minute strategy has a historically verified edge of ~53-55% win rate. The 5-minute strategy collapses under spreads (52.3% raw — not enough). Only trade 15-minute contracts.

---

## License

MIT
