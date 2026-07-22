# Why this works — AIPP + Polymarket 15m trader

**Primary language:** English. Russian copy: [why-this-works.ru.md](why-this-works.ru.md).

---

## What this repo is

`aipp-trading` is a **thin execution and risk wrapper** around live signals from **AIPP (AI Price Patterns)** — the product at [aipricepatterns.com](https://aipricepatterns.com).

It is **not** a second research engine. It does not retrain models, re-index candles, or invent a new forecast. It:

1. Asks AIPP: *for the active BTC 15m Up/Down market, is there a tradeable YES/NO edge after the spread?*
2. Applies a few **hard gates** (balanced v2) so we do not force-trade noise.
3. Places a **small** Polymarket market order (~$5) or skips.
4. Logs every cycle to **SQLite** so edge can be measured over time.

In other words: **AIPP thinks; this repo acts and measures.**

---

## What AIPP is (and why it exists)

**AIPP is the owner’s own project** — a price-pattern / analog research platform and MCP API, not a random third-party black box rented for one bot.

### The core idea

Markets often rhyme. AIPP’s job is to:

- Maintain deep **OHLCV history** and **pattern indexes** (ANN / similarity search)
- Given the **current** shape of price (and context), find **historical analogues**
- Summarize what happened **after** those analogues (direction, return distribution, drawdowns)
- Turn that into **probabilities and decision cards** agents (or humans) can use

That is different from classic indicators (RSI, MACD) and different from a single neural “price next bar” model. The product thesis is:

> **Nearest-neighbor memory over price paths** → empirical distribution of forward outcomes → calibrated-ish P(up/down) and tradeability hints.

### What the service is good for

| Capability | Why it matters |
|---|---|
| **Historical analog search** | “When price looked like this before, what usually followed?” |
| **Multi-horizon / multi-scale views** | 5m vs 15m memory, TTC-aware weighting near expiry |
| **Decision cards** | Compact `BUY_YES` / `BUY_NO` / `SKIP` with edge vs live book |
| **MCP / API for agents** | Same research surface for coding agents, dashboards, and this trader |
| **Backtests / track record tools** | Prove or stress pattern rules (separate from this thin bot) |

AIPP is the **research and signal factory**. This repo is one **consumer** of that factory, specialized for Polymarket BTC 15m binaries.

### What AIPP is *not*

- Not a guaranteed money printer  
- Not a replacement for execution, spreads, or inventory risk  
- Not “always bet” — live tools often return **SKIP** when edge is thin or signals conflict  

A good AIPP day still needs a disciplined executor. A bad AIPP day with an aggressive always-on bot is worse.

---

## Why Polymarket 15m BTC Up/Down

Binary contracts map cleanly to the question AIPP already answers:

> Will BTC be **above or below** the window open (strike) when the 15m contract expires?

| Property | Fit |
|---|---|
| Fixed horizon | 15 minutes matches a natural short-horizon analog forecast |
| Binary outcome | Aligns with P(close > strike) vs market ask |
| Liquid, frequent markets | Many independent trials per day (for learning, not for overtrading size) |
| Explicit price (ask) | Edge = model p − what you pay; G3 encodes that |

Spot perpetual trading needs sizing, leverage, and path-dependent risk. Here risk per trade is roughly **premium paid** (e.g. ~$5), if fills complete.

---

## Why *this* architecture (thin bot + AIPP)

### 1. Separation of concerns

| Layer | Owns |
|---|---|
| **AIPP** | Data, indexes, analogs, probabilities, live Polymarket decision card |
| **cycle_runner** | Schedule, gates, order placement, ledger |
| **SQLite** | Honest post-trade evaluation |

If signal quality is wrong, fix or retrain **in AIPP**.  
If fills fail or sleep kills the Mac, fix **ops here**.  
Do not confuse the two.

### 2. Balanced v2 gates (intentionally few)

Hard gates only:

1. AIPP says BUY_YES or BUY_NO (not SKIP)  
2. No pattern vs intrabar **conflict**  
3. Model p still beats **ask + 2¢**  

Heavier filters (strict Sharpe on a different horizon, multi-q consensus, etc.) historically **killed trade frequency** without clear improvement. This bot trusts AIPP’s live card more and uses backtest proof only as soft context (when an agent reasons manually).

### 3. Small size until proof

$5 per fill is intentional. The point of live running is:

- Measure **calibration** (does p ≈ hit rate?)  
- Measure **PnL by side / edge bucket / regime**  
- Find ops bugs (FOK, Gamma timeouts, laptop sleep)

Scaling size before a resolved ledger is large enough is ego, not science.

### 4. Ledger-first honesty

Free USDC on Polymarket jumps with redeems and open shares. **PnL after resolve** in `trades.db` is the scoreboard. Without that, “the strategy works” is a vibe.

---

## End-to-end path of one cycle

```
15m clock boundary (+ buffer)
        │
        ▼
AIPP  POST /v1/polymarket/live-trade-decision
        │  market discovery, live asks, pattern + intrabar blend
        │  → action, pYes/pNo, edge, conflict
        ▼
cycle_runner  G1–G3
        │
        ├─ FAIL → SKIP, log row
        │
        └─ PASS → market buy YES or NO (~$5)
                    │
                    ▼
              Polymarket CLOB fill
                    │
                    ▼
              trades.db row (EXECUTED / error)
                    │
                    ▼
              later: resolve_trades.py (Gamma outcome → pnl)
```

---

## When you should expect it to “work”

“Works” means different things:

| Sense of “works” | Reality check |
|---|---|
| **Ops works** | Runner alive, AIPP reachable, fills or clean SKIPs, DB rows |
| **Signal has edge** | After many resolved trades, avg PnL > 0 after spreads/FOK misses |
| **Always profitable this week** | Not required; variance on $5 binaries is large |

Up-trending tapes often produce more **YES** signals; chop/mean-reversion stretches look different. A short lucky up-leg is **not** full validation of AIPP — it is one regime sample.

---

## Relationship to the broader AIPP product

This trader is a **dogfooding** harness for the owner’s AIPP stack:

- Stresses **live** Polymarket decision endpoints under real latency and books  
- Surfaces gaps (degraded search, thin liquidity, near-expiry mode)  
- Builds a private track record of **agent-executable** decisions  

Improvements that belong in **AIPP** (examples): better calibration, better near-expiry policy, clearer skip reasons, healthier indexes.  
Improvements that belong **here** (examples): retries, 24/7 host, richer SQL reports, size rules after stats.

---

## Bottom line

| Question | Answer |
|---|---|
| What is the “trick”? | AIPP’s **historical pattern memory** → probability of binary outcomes, sold as live decision cards |
| Why this repo? | Turn those cards into **disciplined, logged, small-size** Polymarket actions |
| Why might it make money? | If AIPP’s p is better than the **market ask** often enough after costs |
| Why might it not? | Thin edge, regime shift, bad fills, sleep gaps, over-filtering or over-trading |
| What to trust first? | **Resolved ledger stats**, not free USDC vibes |

AIPP is the brain (and the long-term product).  
`aipp-trading` is the hands and the notebook.
