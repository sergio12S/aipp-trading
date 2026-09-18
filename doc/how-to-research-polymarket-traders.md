# How to research Polymarket traders (and why fakes are common)

**Primary (Russian, full):** [how-to-research-polymarket-traders.ru.md](how-to-research-polymarket-traders.ru.md)

Public X/Telegram “BTC 15m bots with smooth equity” often mix: favorite scrapes (WR~100% at ask 0.85–0.95), late snipers with jackpots, complete-set/MM (both Up+Down), and demos without a wallet. Leaderboards ≠ BTC 15m. The Data API `closed-positions` default sort is by PnL and **inflates winrate** — always use `sortBy=TIMESTAMP`.

Use `polymarket-trader-intel`: `discover-btc15m` → `closed-pnl` → `why`. For AIPP, extract **gates** (e.g. G4 `ASK_MAX`), never copy sizes. Checklist: wallet address, TIMESTAMP PnL, avg entry price, style label, enough N/age, concentration of max win.
