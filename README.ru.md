# Polymarket BTC 15m Pattern Trader

Автоторговля 15‑минутными Bitcoin **Up/Down** на [Polymarket](https://polymarket.com) по сигналам [AIPP](https://aipricepatterns.com).

> Как исследовать трейдеров / фейки: [`doc/how-to-research-polymarket-traders.ru.md`](doc/how-to-research-polymarket-traders.ru.md).  
> Ресерч кошельков: [`doc/research-btc15m-earners.ru.md`](doc/research-btc15m-earners.ru.md).  
> Адаптация (G4): [`doc/adapt-from-earners.ru.md`](doc/adapt-from-earners.ru.md).

> **Язык:** это **русская копия** ops-гайда. Основное (English): [`README.md`](README.md).  
> **Почему AIPP / смысл стека:** [`doc/why-this-works.ru.md`](doc/why-this-works.ru.md) · EN: [`doc/why-this-works.md`](doc/why-this-works.md) · индекс: [`doc/README.md`](doc/README.md).

**Основной режим:** скрипт `cycle_runner.py` сам каждые 15 минут:

1. Запрашивает AIPP live decision  
2. Проверяет 3 hard gates (balanced v2)  
3. Ставит **market buy ~$5** на **YES** (рост) или **NO** (падение), либо **SKIP**  
4. Пишет цикл в **SQLite** (`trades.db`)

---

## Быстрый старт (шпаргалка)

```bash
cd /Users/serg/projects/my_trading/aipp-trading

# 1) один раз: зависимости + ключи
pip install python-dotenv requests py-clob-client-v2
cp default.env.example default.env   # если ещё нет
# отредактируй default.env

# 2) проверка аккаунта
python3 polymarket_executor.py --test

# 3) запуск автоторговли (фон)
rm -f STOP_CYCLE_RUNNER
nohup env RUN_IMMEDIATE=0 python3 cycle_runner.py >> cycle_runner.log 2>&1 &
echo $! > cycle_runner.pid

# 4) смотреть, что происходит
tail -f cycle_runner.log
python3 resolve_trades.py --stats-only

# 5) после закрытия рынков — резолв PnL
python3 resolve_trades.py

# 6) остановка
touch STOP_CYCLE_RUNNER
# или: kill $(cat cycle_runner.pid)
```

---

## Как это работает

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

| Направление | Сторона | Смысл |
|---|---|---|
| Рост | **BUY_YES** | BTC выше strike к close окна |
| Падение | **BUY_NO** | BTC ниже strike |

Сторону выбирает **AIPP**, не «всегда long».

### Hard gates (balanced v2)

| Gate | Условие |
|---|---|
| **G1** | AIPP = `BUY_YES` или `BUY_NO` (при `SKIP` не торгуем) |
| **G2** | `combined.conflict = false` |
| **G3** | вероятность стороны > ask + **0.02** |
| **G4** | опционально ask в [`ASK_MIN`,`ASK_MAX`] (по умолчанию **shadow**) |

- Размер: **$5 USDC** market order (FOK-style)  
- Trend / backtest proof — только soft (не hard-block)  
- Подробный agent playbook: [`skill/SKILL.md`](skill/SKILL.md)

### Откуда данные

| Источник | Роль |
|---|---|
| **AIPP** | сигнал, probs, edge, SKIP/BUY |
| **Polymarket CLOB** | баланс, ордера, исполнение |
| **Gamma API** | token id рынка, resolve outcome |
| **trades.db** | наш ledger для статистики |

---

## Файлы проекта

| Файл | Зачем |
|---|---|
| **`cycle_runner.py`** | Автоторговля 15m (главный процесс) |
| **`trade_db.py`** | SQLite: запись циклов, resolve, stats |
| **`resolve_trades.py`** | CLI: закрыть outcomes + показать статистику |
| `polymarket_executor.py` | CLOB client, `python3 … --test` |
| `polymarket_agent_bot.py` | Ручной один цикл (legacy / dry-run) |
| `default.env` | Секреты Polymarket (**не в git**) |
| `default.env.example` | Шаблон env |
| **`trades.db`** | SQLite БД (локально, gitignore) |
| `cycle_runner.log` | Текстовый лог runner |
| `cycle_runner.pid` | PID фонового процесса |
| `cycle_runner_state.json` | Последний цикл (JSON) |
| `strike_history.json` | История strike/close (soft trend) |
| `STOP_CYCLE_RUNNER` | Файл-флаг «остановиться» |
| `skill/SKILL.md` | Framework для AI-агента |
| `README.md` | Основная документация (English) |

---

## Установка (один раз)

### 1. Зависимости

```bash
cd /Users/serg/projects/my_trading/aipp-trading
pip install python-dotenv requests py-clob-client-v2
```

### 2. Ключи Polymarket

```bash
cp default.env.example default.env
```

В `default.env` нужны:

```env
POLYMARKET_API_KEY=...
POLYMARKET_SECRET=...
POLYMARKET_PASSPHRASE=...
POLYMARKET_PK=...                 # private key signer
POLYMARKET_FUNDER=0x...           # proxy wallet с USDC
POLYMARKET_SIGNATURE_TYPE=2       # обычно 2
```

Опционально: `AIPP_TOKEN` — если AIPP REST требует Manus token.

USDC должен быть на **funder (proxy)**, не только на EOA signer.

### 3. Проверка

```bash
python3 polymarket_executor.py --test
```

Ожидаешь: `Status OK`, адрес signer, **USDC ≥ $5**, open orders.

Инициализация пустой БД (создаётся сама при первом цикле, можно руками):

```bash
python3 -c "from trade_db import init_db; init_db(); print('trades.db ok')"
python3 resolve_trades.py --stats-only
```

---

## Запуск торговли

### Рекомендуемый режим (фон, ждать следующее окно)

```bash
cd /Users/serg/projects/my_trading/aipp-trading
rm -f STOP_CYCLE_RUNNER

nohup env RUN_IMMEDIATE=0 python3 cycle_runner.py >> cycle_runner.log 2>&1 &
echo $! > cycle_runner.pid
echo "PID=$(cat cycle_runner.pid)"
```

`RUN_IMMEDIATE=0` — **не** торговать текущее окно сразу, ждать `:00/:15/:30/:45` + ~25s.

### Сразу текущее окно (если TTC ≳ 3 мин)

```bash
nohup env RUN_IMMEDIATE=1 python3 cycle_runner.py >> cycle_runner.log 2>&1 &
echo $! > cycle_runner.pid
```

### Тест на N циклов (foreground)

```bash
MAX_CYCLES=3 RUN_IMMEDIATE=1 python3 cycle_runner.py
```

### Переменные окружения runner

| Переменная | Default | Смысл |
|---|---|---|
| `RUN_IMMEDIATE` | `0` | `1` = цикл сразу после старта |
| `MAX_CYCLES` | `0` | `0` = бесконечно; иначе N циклов |

В коде: `ALLOCATED_USD=5`, `EDGE_BUFFER=0.02`, `OPEN_BUFFER_SEC=25`.

### Важно

- **Не запускай два runner’а** — риск double order.  
  Проверка: `ps -p $(cat cycle_runner.pid)` / `pgrep -fl cycle_runner`  
- Закрытие **крышки Mac** обычно = sleep → **пропуски окон**.  
  `nohup` не спасает от сна. Для 24/7 — VPS / всегда on / `caffeinate`.  
- Free USDC ≠ полный equity (shares / redeem).

---

## Остановка

```bash
# мягко (после текущего sleep/цикла)
touch STOP_CYCLE_RUNNER

# сразу
kill $(cat cycle_runner.pid)

# если завис
kill -9 $(cat cycle_runner.pid)
rm -f STOP_CYCLE_RUNNER cycle_runner.pid
```

Проверить, что нет висящих ордеров:

```bash
python3 polymarket_executor.py --test
# или
python3 -c "from polymarket_executor import get_client; print(get_client().get_open_orders())"
```

---

## Мониторинг (жив ли бот)

```bash
# процесс
ps -p $(cat cycle_runner.pid) -o pid,etime,command

# хвост лога в реальном времени
tail -f cycle_runner.log

# последний decision
cat cycle_runner_state.json

# баланс / open orders
python3 polymarket_executor.py --test
```

В логе нормально видеть:

```text
=== CYCLE Bitcoin Up or Down - ... | BUY_YES|BUY_NO|SKIP | ...
Gates G1=... G2=... G3=...
EXECUTE MARKET BUY_...   или   SKIP — hard gates...
ORDER RESPONSE: ..."status": "matched"...
DB: recorded cycle id=...
Sleeping 89xs until next 15m open+buffer
```

Ошибки, которые **не роняют** процесс (но цикл может не исполниться):

- `FOK orders are fully filled or killed` — нет ликвидности на $5  
- `gamma-api ... timed out` — не резолвнули token  
- `Failed to fetch live decision from AIPP` — сеть/AIPP timeout  

---

## Статистика и SQLite

### Что хранится

Каждый цикл → строка в таблице `cycles`:

- время, slug, title  
- action / side, strike, btc, ttc  
- p_side, edge, confidence, conflict, trend  
- g1/g2/g3, usdc_free  
- **final**: `SKIP`, `EXECUTED`, `EXEC_ERROR`, `UNFILLED_CANCELLED`, …  
- order_id, making_usd (стоимость), taking_shares  
- после resolve: **outcome**, **pnl_usd**, **win**

### Resolve (закрыть outcomes + PnL)

Запускай **после** того, как 15m-рынки успели зарезолвиться (не чаще, чем раз в ~15–30 мин, или раз в день):

```bash
cd /Users/serg/projects/my_trading/aipp-trading
python3 resolve_trades.py
```

Скрипт:

1. Берёт `final=EXECUTED` без `outcome`  
2. Тянет рынок с Gamma по `slug`  
3. Если resolved → пишет YES/NO, `pnl_usd`, `win`  
4. Печатает сводку  

Только статистика (без resolve):

```bash
python3 resolve_trades.py --stats-only
```

Только resolve:

```bash
python3 resolve_trades.py --resolve-only
```

JSON:

```bash
python3 resolve_trades.py --stats-only --json
```

Окна младше ~16 минут по умолчанию **не** резолвятся (ещё рано).

### Примеры SQL

```bash
# последние 20 циклов
sqlite3 trades.db "
SELECT id, ts_utc, side, printf('%.3f', edge) AS edge, final, outcome, printf('%.2f', pnl_usd) AS pnl
FROM cycles ORDER BY id DESC LIMIT 20;
"

# только исполненные
sqlite3 trades.db "
SELECT id, ts_utc, side, edge, making_usd, taking_shares, outcome, pnl_usd, win
FROM cycles WHERE final = 'EXECUTED' ORDER BY id DESC LIMIT 30;
"

# WR и PnL по стороне
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

# по «толщине» edge
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

# частота SKIP vs EXECUTE
sqlite3 trades.db "SELECT final, COUNT(*) FROM cycles GROUP BY final;"
```

### Как читать сводку `resolve_trades.py`

```text
total cycles   — все записи (включая SKIP)
executed       — были market fills
resolved       — outcome уже проставлен
win rate       — доля win среди resolved
sum pnl_usd    — сумма PnL по resolved ($1/share − cost при win; −cost при lose)
by side        — YES vs NO
by edge bucket — thin / mid / fat
```

Пока `resolved` мало — **не** делай выводы и **не** крути gates.

---

## Типичный день оператора

| Когда | Действие |
|---|---|
| Утро | `ps -p $(cat cycle_runner.pid)` — жив? иначе restart |
| | `python3 resolve_trades.py` — догнать outcomes |
| Днём | `tail -f cycle_runner.log` при желании |
| | Mac **не** должен спать, если нужна непрерывность |
| Вечер | `python3 resolve_trades.py` + глянуть free USDC |
| Раз в неделю | SQL by side / edge — есть ли edge? |

---

## Ручные команды (не авто)

Dry-run один раз (без ордера, обновит strike history):

```bash
python3 polymarket_agent_bot.py --dry-run
```

Live один раз **без** SQLite gates runner (сырой AIPP + limit) — **не для прода**:

```bash
python3 polymarket_agent_bot.py
```

Для продакшена всегда **`cycle_runner.py`**.

---

## Troubleshooting

| Симптом | Что делать |
|---|---|
| Нет новых строк в `trades.db` | Runner на **старом** коде? Restart `cycle_runner.py`. Жив ли PID? |
| `total cycles: 0` | Ещё не было цикла после включения ledger; жди 15m |
| Много `EXEC_ERROR` / FOK | Thin book; смотри log; не паника, size $5 |
| Free USDC «прыгает» | Redeem/win/loss; смотри `pnl_usd` в БД, не только free |
| Пропуски по ночам | Mac sleep (крышка); caffeinate / VPS |
| Два PID `cycle_runner` | Убей лишний: `pkill -f cycle_runner.py` и стартани один |
| Resolve ничего не закрывает | Рынок ещё open; или Gamma не отдал outcome — повтори позже |

---

## Безопасность

- `default.env`, `trades.db`, логи — **не коммитить** (см. `.gitignore`)  
- Private key в env — только локально  
- Не шарь `cycle_runner.log` с order id публично без нужды  

---

## License

MIT

## Ledger (измерение)

- Каждый цикл пишется в `trades.db` — и **SKIP**, и **EXECUTED** (`persist_cycle`).
- После каждого цикла (и на старте) runner сам вызывает `resolve_pending` (~16 мин после окна) — PnL обновляется без ручного шага.
- `python3 resolve_trades.py` по-прежнему можно гонять вручную; он идемпотентен.

