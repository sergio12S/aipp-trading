# Почему это работает — AIPP + Polymarket 15m trader

**Язык:** русская копия. Основной текст (English): [why-this-works.md](why-this-works.md).

---

## Что это за репозиторий

`aipp-trading` — **тонкая обёртка исполнения и риска** вокруг live-сигналов **AIPP (AI Price Patterns)** — продукта на [aipricepatterns.com](https://aipricepatterns.com).

Это **не** второй research-движок. Он не переобучает модели, не переиндексирует свечи и не изобретает новый прогноз. Он:

1. Спрашивает AIPP: *на активном BTC 15m Up/Down рынке есть ли tradeable edge YES/NO после спреда?*
2. Применяет несколько **hard gates** (balanced v2), чтобы не форсить шум.
3. Ставит **маленький** market order на Polymarket (~$5) или скипает.
4. Логирует каждый цикл в **SQLite**, чтобы edge измерять во времени.

Иными словами: **AIPP думает; этот репо действует и измеряет.**

---

## Что такое AIPP (и зачем он)

**AIPP — свой проект владельца** (не чужой black box «с улицы»), платформа pattern/analog research + MCP API.

### Идея

Рынки часто «рифмуются». AIPP:

- Держит глубокую **OHLCV-историю** и **индексы паттернов** (ANN / similarity)
- По **текущей** форме цены (и контексту) находит **исторические аналоги**
- Сводит, что было **после** них (направление, distribution return, drawdown)
- Отдаёт **вероятности и decision cards** агентам и людям

Это не классические индикаторы (RSI/MACD) и не один «предскажи next bar» нейросеть. Тезис продукта:

> **Память ближайших соседей по траектории цены** → эмпирическое распределение будущих исходов → P(up/down) и подсказки tradeability.

### Зачем сервис

| Возможность | Зачем |
|---|---|
| **Поиск исторических аналогов** | «Когда цена так выглядела раньше — что обычно дальше?» |
| **Мульти-горизонт / multi-scale** | 5m vs 15m, TTC-веса near expiry |
| **Decision cards** | Компактные `BUY_YES` / `BUY_NO` / `SKIP` + edge vs live book |
| **MCP / API для агентов** | Один research surface: код, UI, этот trader |
| **Бэктесты / track record** | Проверка правил (отдельно от тонкого бота) |

AIPP — **фабрика research и сигналов**. Этот репо — один **consumer**, заточенный под Polymarket BTC 15m binary.

### Чем AIPP не является

- Не гарантия прибыли  
- Не замена execution, спредам и риску  
- Не «всегда в рынке» — live часто отвечает **SKIP**

Хороший день AIPP всё равно требует дисциплины. Плохой день AIPP + жадный always-on — хуже.

---

## Почему Polymarket 15m BTC Up/Down

Binary-контракты совпадают с вопросом, на который AIPP уже отвечает:

> Будет ли BTC **выше или ниже** open окна (strike) к экспирации 15m?

| Свойство | Fit |
|---|---|
| Фиксированный горизонт | 15 минут — естественный short-horizon analog |
| Бинарный исход | P(close > strike) vs market ask |
| Частые рынки | Много независимых trials (для обучения, не для разгона size) |
| Явная цена (ask) | Edge = model p − цена входа; G3 это кодирует |

Фьючерсы/перпы требуют плеча и path risk. Здесь риск на сделку ≈ **премия** (~$5), если fill прошёл.

---

## Почему такая архитектура (тонкий бот + AIPP)

### 1. Разделение ответственности

| Слой | Отвечает за |
|---|---|
| **AIPP** | Данные, индексы, аналоги, вероятности, live decision card |
| **cycle_runner** | Расписание, gates, ордера, ledger |
| **SQLite** | Честная оценка post-trade |

Сигнал плохой → чинить **в AIPP**.  
Fills/sleep → чинить **ops здесь**.  
Не смешивать.

### 2. Balanced v2 — мало hard gates

1. AIPP = BUY_YES или BUY_NO (не SKIP)  
2. Нет **conflict** pattern vs intrabar  
3. p бьёт **ask + 2¢**  

Жёсткие multi-filter stacks исторически **убивали частоту** без ясного плюса. Бот доверяет live card AIPP; proof backtest — soft context для агента.

### 3. Малый size до proof

$5 на fill — осознанно. Live нужен чтобы:

- Мерить **калибровку** (p ≈ hit rate?)  
- Мерить **PnL по side / edge / regime**  
- Ловить ops-баги (FOK, Gamma timeout, sleep Mac)

Раздувать size до большого resolved ledger — рано.

### 4. Ledger first

Free USDC прыгает из‑за redeem и open shares. **PnL после resolve** в `trades.db` — scoreboard. Без этого «стратегия работает» — ощущение.

---

## Путь одного цикла

```
граница 15m (+ buffer)
        │
        ▼
AIPP  live-trade-decision
        │  рынок, ask, pattern + intrabar
        │  → action, pYes/pNo, edge, conflict
        ▼
cycle_runner  G1–G3
        │
        ├─ FAIL → SKIP, запись в БД
        │
        └─ PASS → market buy YES/NO (~$5)
                    │
                    ▼
              Polymarket CLOB
                    │
                    ▼
              trades.db
                    │
                    ▼
              resolve_trades.py → pnl
```

---

## Когда «работает»

| Смысл «работает» | Проверка |
|---|---|
| **Ops** | Runner жив, AIPP доступен, fills или чистые SKIP, строки в БД |
| **Есть edge** | Много resolved, avg PnL > 0 после costs/FOK |
| **Каждая неделя в плюсе** | Не требуется; variance на $5 binary большая |

Up-tape часто даёт больше **YES**; chop выглядит иначе. Короткий удачный up-leg — **не** полная валидация AIPP, а один regime sample.

---

## Связь с продуктом AIPP

Trader — **dogfooding** стека AIPP:

- Живые Polymarket endpoints, latency, book  
- Видны gaps (degraded search, thin liquidity, near_expiry)  
- Личный track record **agent-executable** решений  

Улучшения **в AIPP**: калибровка, near-expiry policy, skip reasons, индексы.  
Улучшения **здесь**: retries, 24/7 host, SQL-отчёты, size после статистики.

---

## Короткий итог

| Вопрос | Ответ |
|---|---|
| В чём «прикол»? | **Память исторических паттернов** AIPP → P binary-исхода + live decision card |
| Зачем этот репо? | Дисциплинированные **маленькие** сделки + **лог** |
| Почему может зарабатывать? | Если p AIPP **часто лучше ask** после издержек |
| Почему может нет? | Thin edge, смена режима, fills, sleep, overtrade/overfilter |
| Чему верить сначала? | **Resolved ledger**, не free USDC |

**AIPP — мозг (и долгосрочный продукт).**  
**aipp-trading — руки и блокнот.**
