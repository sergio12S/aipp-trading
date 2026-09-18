# Polymarket BTC 15m Pattern Trader

Automated trading of 15-minute Bitcoin **Up/Down** markets on [Polymarket](https://polymarket.com), driven by [AIPP](https://aipricepatterns.com) live signals.

> **Language:** this is the **primary** ops guide (English). Russian ops copy: [`README.ru.md`](README.ru.md).  
> **Why AIPP / product context:** [`doc/why-this-works.md`](doc/why-this-works.md) (EN) · [`doc/why-this-works.ru.md`](doc/why-this-works.ru.md) (RU) · [`doc/README.md`](doc/README.md).

**Production mode:** `cycle_runner.py` runs every 15 minutes and:

1. Fetches the AIPP live trade decision  
2. Applies 3 hard gates (balanced v2)  
3. Places a **~$5 market buy** on **YES** (up) or **NO** (down), or **SKIP**  
4. Logs the cycle to **SQLite** (`trades.db`)

---

## Quick start

```bash
cd /Users/serg/projects/my_trading/aipp-trading

# 1) one-time: deps + keys
pip install python-dotenv requests py-clob-client-v2
cp default.env.example default.env   # if missing
# edit default.env

# 2) account check
python3 polymarket_executor.py --test

# 3) start auto-trading (background)
rm -f STOP_CYCLE_RUNNER
nohup env RUN_IMMEDIATE=0 python3 cycle_runner.py >> cycle_runner.log 2>&1 &
echo $! > cycle_runner.pid

# 4) watch activity
tail -f cycle_runner.log
python3 resolve_trades.py --stats-only

# 5) after markets settle — resolve PnL
python3 resolve_trades.py

# 6) stop
touch STOP_CYCLE_RUNNER
# or: kill $(cat cycle_runner.pid)
```

---

## How it works

```
:00 / :15 / :30 / :45  (+ ~25s buffer)
              │
              ▼
     ┌────────────────────┐
     │  cycle_runner.py   │
     │  AIPP live decision│
     │  Gates G1–G3       │
     │  market $5 YES/NO  │
     │  → trades.db       │
     └─────────┬──────────┘
               │
               ▼
        Polymarket CLOB
```

| Direction | Side | Meaning |
|---|---|---|
| Up | **BUY_YES** | BTC above strike at window close |
| Down | **BUY_NO** | BTC below strike |

Side is chosen by **AIPP**, not hard-coded to long-only.

### Hard gates (balanced v2)

| Gate | Condition |
|---|---|
| **G1** | AIPP = `BUY_YES` or `BUY_NO` (`SKIP` → no trade) |
| **G2** | `combined.conflict = false` |
| **G3** | side probability > ask + **0.02** |

- Size: **$5 USDC** market order (FOK-style)  
- Local trend / pattern proof backtest are **soft only** (not hard blockers)  
- Full agent playbook: [`skill/SKILL.md`](skill/SKILL.md)

### Data sources

| Source | Role |
|---|---|
| **AIPP** | signal, probs, edge, SKIP/BUY |
| **Polymarket CLOB** | balance, orders, execution |
| **Gamma API** | market token ids, outcome resolve |
| **trades.db** | local ledger for evaluation |

---

## Project files

| File | Purpose |
|---|---|
| **`cycle_runner.py`** | 15m auto-trading (main process) |
| **`trade_db.py`** | SQLite: record cycles, resolve, stats |
| **`resolve_trades.py`** | CLI: resolve outcomes + print summary |
| `polymarket_executor.py` | CLOB client, `python3 … --test` |
| `polymarket_agent_bot.py` | Manual single cycle (legacy / dry-run) |
| `default.env` | Polymarket secrets (**not in git**) |
| `default.env.example` | Env template |
| **`trades.db`** | SQLite DB (local, gitignored) |
| `cycle_runner.log` | Text log |
| `cycle_runner.pid` | Background process PID |
| `cycle_runner_state.json` | Last cycle snapshot (JSON) |
| `strike_history.json` | Strike/close history (soft trend) |
| `STOP_CYCLE_RUNNER` | Stop flag file |
| `skill/SKILL.md` | AI agent decision framework |
| `README.ru.md` | Russian documentation copy |

---

## Setup (once)

### 1. Dependencies

```bash
cd /Users/serg/projects/my_trading/aipp-trading
pip install python-dotenv requests py-clob-client-v2
```

### 2. Polymarket credentials

```bash
cp default.env.example default.env
```

Required in `default.env`:

```env
POLYMARKET_API_KEY=...
POLYMARKET_SECRET=...
POLYMARKET_PASSPHRASE=...
POLYMARKET_PK=...                 # signer private key
POLYMARKET_FUNDER=0x...           # proxy wallet holding USDC
POLYMARKET_SIGNATURE_TYPE=2       # usually 2
```

Optional: `AIPP_TOKEN` if AIPP REST requires a Manus token.

USDC must sit on the **funder (proxy)** wallet, not only the signer EOA.

### 3. Sanity check

```bash
python3 polymarket_executor.py --test
```

Expect: `Status OK`, signer address, **USDC ≥ $5**, open orders list.

Empty DB (auto-created on first cycle; optional manual init):

```bash
python3 -c "from trade_db import init_db; init_db(); print('trades.db ok')"
python3 resolve_trades.py --stats-only
```

---

## Start trading

### Recommended (background, wait for next window)

```bash
cd /Users/serg/projects/my_trading/aipp-trading
rm -f STOP_CYCLE_RUNNER

nohup env RUN_IMMEDIATE=0 python3 cycle_runner.py >> cycle_runner.log 2>&1 &
echo $! > cycle_runner.pid
echo "PID=$(cat cycle_runner.pid)"
```

`RUN_IMMEDIATE=0` — do **not** trade the current window immediately; wait for `:00/:15/:30/:45` + ~25s.

### Trade current window immediately (if TTC ≳ 3 min)

```bash
nohup env RUN_IMMEDIATE=1 python3 cycle_runner.py >> cycle_runner.log 2>&1 &
echo $! > cycle_runner.pid
```

### Foreground test for N cycles

```bash
MAX_CYCLES=3 RUN_IMMEDIATE=1 python3 cycle_runner.py
```

### Runner environment variables

| Variable | Default | Meaning |
|---|---|---|
| `RUN_IMMEDIATE` | `0` | `1` = run one cycle on startup |
| `MAX_CYCLES` | `0` | `0` = unlimited; else stop after N cycles |

In code: `ALLOCATED_USD=5`, `EDGE_BUFFER=0.02`, `OPEN_BUFFER_SEC=25`.

### Important

- **Do not run two runners** — double-order risk.  
  Check: `ps -p $(cat cycle_runner.pid)` / `pgrep -fl cycle_runner`  
- Closing a **MacBook lid** usually sleeps the machine → **missed windows**.  
  `nohup` does not prevent sleep. For 24/7 use a VPS / always-on host / `caffeinate`.  
- Free USDC ≠ full equity (open shares / redeem).

---

## Stop trading

```bash
# graceful (after current sleep/cycle)
touch STOP_CYCLE_RUNNER

# immediate
kill $(cat cycle_runner.pid)

# if stuck
kill -9 $(cat cycle_runner.pid)
rm -f STOP_CYCLE_RUNNER cycle_runner.pid
```

Check open orders:

```bash
python3 polymarket_executor.py --test
# or
python3 -c "from polymarket_executor import get_client; print(get_client().get_open_orders())"
```

---

## Monitoring

```bash
# process alive?
ps -p $(cat cycle_runner.pid) -o pid,etime,command

# live log
tail -f cycle_runner.log

# last decision snapshot
cat cycle_runner_state.json

# balance / open orders
python3 polymarket_executor.py --test
```

Healthy log patterns:

```text
=== CYCLE Bitcoin Up or Down - ... | BUY_YES|BUY_NO|SKIP | ...
Gates G1=... G2=... G3=...
EXECUTE MARKET BUY_...   or   SKIP — hard gates...
ORDER RESPONSE: ..."status": "matched"...
DB: recorded cycle id=...
Sleeping 89xs until next 15m open+buffer
```

Non-fatal errors (process keeps running; cycle may skip fill):

- `FOK orders are fully filled or killed` — not enough book liquidity for $5  
- `gamma-api ... timed out` — token resolve failed  
- `Failed to fetch live decision from AIPP` — network/AIPP timeout  

---

## Statistics & SQLite

### What is stored

Each cycle → one row in `cycles`:

- timestamp, slug, title  
- action / side, strike, btc, ttc  
- p_side, edge, confidence, conflict, trend  
- g1/g2/g3, usdc_free  
- **final**: `SKIP`, `EXECUTED`, `EXEC_ERROR`, `UNFILLED_CANCELLED`, …  
- order_id, making_usd (cost), taking_shares  
- after resolve: **outcome**, **pnl_usd**, **win**

### Resolve outcomes + PnL

Run after 15m markets have settled (every ~15–30 min, or once a day):

```bash
cd /Users/serg/projects/my_trading/aipp-trading
python3 resolve_trades.py
```

The script:

1. Loads `final=EXECUTED` rows without `outcome`  
2. Fetches the market from Gamma by `slug`  
3. If resolved → writes YES/NO, `pnl_usd`, `win`  
4. Prints a summary  

Stats only (no resolve):

```bash
python3 resolve_trades.py --stats-only
```

Resolve only:

```bash
python3 resolve_trades.py --resolve-only
```

JSON:

```bash
python3 resolve_trades.py --stats-only --json
```

Rows younger than ~16 minutes are skipped by default (too early to resolve).

### Example SQL

```bash
# last 20 cycles
sqlite3 trades.db "
SELECT id, ts_utc, side, printf('%.3f', edge) AS edge, final, outcome, printf('%.2f', pnl_usd) AS pnl
FROM cycles ORDER BY id DESC LIMIT 20;
"

# fills only
sqlite3 trades.db "
SELECT id, ts_utc, side, edge, making_usd, taking_shares, outcome, pnl_usd, win
FROM cycles WHERE final = 'EXECUTED' ORDER BY id DESC LIMIT 30;
"

# WR and PnL by side
sqlite3 trades.db "
SELECT side,
       COUNT(*) AS n,
       SUM(win) AS wins,
       ROUND(100.0 * SUM(win) / COUNT(*), 1) AS wr_pct,
       ROUND(SUM(pnl_usd), 2) AS pnl
FROM cycles
WHERE outcome IS NOT NULL
GROUP BY side;
"

# by edge thickness
sqlite3 trades.db "
SELECT
  CASE
    WHEN edge < 0.08 THEN 'thin_<0.08'
    WHEN edge < 0.15 THEN 'mid_0.08_0.15'
    ELSE 'fat_>=0.15'
  END AS bucket,
  COUNT(*) AS n,
  SUM(win) AS wins,
  ROUND(SUM(pnl_usd), 2) AS pnl
FROM cycles
WHERE outcome IS NOT NULL
GROUP BY bucket;
"

# SKIP vs EXECUTE frequency
sqlite3 trades.db "SELECT final, COUNT(*) FROM cycles GROUP BY final;"
```

### How to read `resolve_trades.py` summary

```text
total cycles   — all rows (including SKIP)
executed       — market fills attempted/succeeded
resolved       — outcome filled in
win rate       — wins / (wins+losses) among resolved
sum pnl_usd    — sum of resolved PnL ($1/share − cost on win; −cost on loss)
by side        — YES vs NO
by edge bucket — thin / mid / fat
```

If `resolved` is still small — **do not** retune gates yet.

---

## Typical operator day

| When | Action |
|---|---|
| Morning | `ps -p $(cat cycle_runner.pid)` — alive? else restart |
| | `python3 resolve_trades.py` — catch up outcomes |
| Daytime | `tail -f cycle_runner.log` if needed |
| | Keep host **awake** for continuous coverage |
| Evening | `python3 resolve_trades.py` + check free USDC |
| Weekly | SQL by side / edge — is there real edge? |

---

## Manual commands (not auto mode)

One dry-run (no order; updates strike history):

```bash
python3 polymarket_agent_bot.py --dry-run
```

One live cycle **without** runner gates/SQLite (raw AIPP + limit) — **not for production**:

```bash
python3 polymarket_agent_bot.py
```

For production always use **`cycle_runner.py`**.

---

## Troubleshooting

| Symptom | What to do |
|---|---|
| No new rows in `trades.db` | Old runner binary? Restart `cycle_runner.py`. Is PID alive? |
| `total cycles: 0` | No cycle yet after ledger enable; wait ≤15m |
| Many `EXEC_ERROR` / FOK | Thin book; check log; keep $5 size |
| Free USDC jumps around | Redeem/win/loss; trust `pnl_usd` in DB, not free only |
| Night gaps | Mac sleep (lid); use caffeinate / VPS |
| Two `cycle_runner` PIDs | Kill extras: `pkill -f cycle_runner.py`, start one |
| Resolve closes nothing | Market still open, or Gamma has no outcome yet — retry later |

---

## Security

- Do **not** commit `default.env`, `trades.db`, or logs (see `.gitignore`)  
- Keep private keys local only  
- Avoid sharing `cycle_runner.log` publicly (order ids)

---

## License

MIT

## Ledger notes (measurement)

- Every cycle is written to `trades.db` — **SKIP and EXECUTED** (via `persist_cycle`).
- After each cycle (and on startup) the runner calls `resolve_pending` automatically (~16m after window) so PnL stats update without a manual step.
- You can still run `python3 resolve_trades.py` anytime; it is idempotent.

