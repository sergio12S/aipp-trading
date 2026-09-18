# Ресерч: успешные и заметные кошельки BTC 15m на Polymarket

**Дата среза:** 2026-09-17 (Europe/Zurich)  
**Инструмент:** `polymarket-trader-intel` → `closed-pnl` / `stable-earners`  
**Сортировка closed-positions:** только `sortBy=TIMESTAMP` (дефолт API по PnL даёт фейковый WR)  
**Окно:** последние ~200 закрытых позиций (не lifetime), если не сказано иное  
**Не финсовет и не copy-trade.** Цель — понять стили и что адаптировать в AIPP (гейты), а не копировать размеры.

Связанные доки: [adapt-from-earners.ru.md](adapt-from-earners.ru.md) · intel CLI: `polymarket-trader-intel`.

---

## Краткий вывод для AIPP

Большинство «красивых» кривых и высоких WR на BTC Up/Down — это не тот edge, что у нас (AIPP + вход около открытия окна):

1. **Скрейп фаворита** (ask ~0.85–0.95) → почти 100% WR, мелкий доллар на сделку.
2. **Late sniper** → крупный PnL, жирные хвосты, вход в конце окна.
3. **Complete-set / MM** (реклама в X) → оба исхода, огромный объём; на коротком срезе может быть ~50% WR.
4. Реже — **mid directional** (deepmoat): WR ~60%, цена ~0.5–0.6, есть buy и sell — ближе к нашей модели.

**Уже адаптировано:** G4 `ASK_MAX=0.70` в shadow (`GATE_SHADOW=1`).  
**Не берём:** копирование кошельков, HFT/complete-set на $1, «100% WR» ботов.

---

## Метод (обязательно читать)

| Ловушка | Суть |
|--------|------|
| `closed-positions` без `sortBy` | Сверху лучшие PnL → кажется 100% WR |
| WR без avg price | WR 90% при цене 0.90 не равен прогнозу |
| Lifetime vs окно | gabagool «$869k» не равен последним 24 closed |
| Реклама в X | Часто MM + видео equity; иногда демо без кошелька |

Воспроизведение:

```bash
cd /Users/serg/projects/my_trading/polymarket-trader-intel
PYTHONPATH=src python3 -m trader_intel closed-pnl 0xWALLET --max-rows 200
PYTHONPATH=src python3 -m trader_intel stable-earners --scan-trades 4000 --top-wallets 20
PYTHONPATH=src python3 -m trader_intel why 0xWALLET
```

---

## Сводка кейсов (TIMESTAMP, max_rows≈200, 2026-09-17 ~16:20)

| Кейс | Адрес | N | WR | PnL $ | Avg px | Стиль | Для AIPP |
|------|-------|--:|---:|------:|-------:|-------|----------|
| maxmaxi04 | `0x10d57bd3327bcdf43bf0656e717aa56f9dbd5388` | 28 | 96% | +2901 | 0.79 | Late / крупный размер, conc≈0.42 | Позже: бакет late |
| deepmoat | `0xc6accd5b5f647aacb751b8f3e9d640e723733778` | 42 | 64% | +245 | 0.59 | Mid directional, buy+sell | **Да → mid-band / G4** |
| ea59 | `0xea5929609487194dc9ce00871e2b5d1e5f48f29d` | 200 | 100% | +1705 | 0.84 | Favorite scrape | **Нет; антипаттерн G4** |
| xloong | `0x31e6cdd9dfc17cff6e106e3aaca542bdf9b4620f` | 200 | 100% | +58 | 0.93 | Tiny scrape | **Нет; антипаттерн** |
| elyash | `0xbc7bdca7a6701eb806eef565998e0545ff5ec4eb` | 99 | 60% | +214 | 0.44 | Underdog, высокий conc | Осторожно |
| magmaalpha | `0xbdaacd345fec209cd09d933e62f92e8b530afd60` | 193 | 53% | +49 | 0.64 | Мелкий чек, высокий N | Слабый сигнал |
| Flyinghippo08 | `0x78a07b91b4e2eed0835d7924f3a1846443250e82` | 30 | 80% | +205 | 0.64 | Новый аккаунт (сен 2026) | Не «stable» |
| gabagool22 | `0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d` | 24 | 50% | −98 | 0.51 | Complete-set / MM | **Не для $1 AIPP** |

---

## Кейс 1 — deepmoat (ближайший к AIPP)

- **Адрес:** `0xc6accd5b5f647aacb751b8f3e9d640e723733778`
- **Срез:** N=42, WR≈64%, PnL≈+$245, avg price≈0.59, max loss заметный (около −$138)
- **Стиль:** смешанный тайминг; есть покупки и продажи; цена около середины.
- **Интерпретация:** похоже на направленную торговлю с умеренным edge, не scrape. Окно короткое — не вечный edge.
- **Адаптация:** mid-band / **G4** `ASK_MAX=0.70` (опционально `ASK_MIN≈0.35`). Не копировать notional.

---

## Кейс 2 — maxmaxi04 (реальный размер, не стабильный)

- **Адрес:** `0x10d57bd3327bcdf43bf0656e717aa56f9dbd5388`
- **Срез:** N=28, WR≈96%, PnL≈+$2.9k, avg px≈0.79, **conc≈0.42**
- **Стиль:** near-expiry sniper (много входов в конце 15m).
- **Интерпретация:** живая крупная активность; кривая не ровная; джекпот тянет PnL.
- **Адаптация:** не ломать open+25s. Позже — shadow-бакет late. Не копировать size.

---

## Кейс 3 — ea59 и xloong (антипаттерн / маркетинг WR)

### ea59 — `0xea5929609487194dc9ce00871e2b5d1e5f48f29d`
N=200, WR=100%, PnL≈+$1.7k, avg px≈0.84, средний чек ~$8.5.

### xloong — `0x31e6cdd9dfc17cff6e106e3aaca542bdf9b4620f`
N=200, WR=100%, PnL≈+$58, avg px≈0.93, avg≈$0.29 — идеальный скрин «100% bot».

**Адаптация:** не торговать так. G4 против этого класса.

---

## Кейс 4 — elyash (underdog)

- **Адрес:** `0xbc7bdca7a6701eb806eef565998e0545ff5ec4eb`
- N=99, WR≈60%, PnL≈+$214, avg px≈0.44, conc≈0.51
- Дешёвые входы, высокая дисперсия.
- **Адаптация:** edge через G3; не longshot sizing.

---

## Кейс 5 — magmaalpha и Flyinghippo08

- **magmaalpha** (`0xbdaacd345f…`): высокий N, WR≈53%, крошечный avg — возможен шум после fees.
- **Flyinghippo08** (`0x78a07b91…`): молодой аккаунт, WR 80% на N=30 легко от удачи.
- **Адаптация:** минимум N и возраст в любом earner-фильтре.

---

## Кейс 6 — gabagool22 (X ads / complete-set)

- **Адрес:** `0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d`
- Публичный образ: ~$869k lifetime, огромный volume.
- Короткий BTC closed-срез: N=24, WR≈50%, PnL≈−$98; в трейдах — **Up и Down на одном рынке**.
- **Адаптация:** не на $1 open-window AIPP.

---

## Реклама в X

Шаблон `RetroValix` / клоны / `Dan1ro0`: equity-видео, HFT, мелкий avg trade. Часто complete-set/MM. Бывают сфабрикованные демо без кошелька. Проверять: avg price, оба ли стороны, TIMESTAMP, адрес.

---

## Маппинг на гейты AIPP

| Наблюдение | Gate |
|------------|------|
| Не брать ask ≫ 0.70–0.85 | **G4** `ASK_MAX=0.70` (shadow) |
| Edge vs рынок | **G3** |
| Сторона от AIPP | **G1/G2** |
| Late sniper | Позже: timing bucket |
| Complete-set | Не в runner |

Текущий live: `GATE_SHADOW=1`, `ASK_MAX=0.70`, size `$1`.

---

## Следующие вопросы

1. После 20–40 циклов: PnL fills с ask>0.70 vs те, что G4 отрезал бы.
2. Нужен ли `ASK_MIN`.
3. Paper mid/late бакет без ломки :00+25s.
4. gabagool-style — только отдельный проект.

## История срезов

| Когда | Что |
|-------|-----|
| 2026-09-17 ~15:40 | Первый dissect, max_rows до 400 |
| 2026-09-17 ~16:20 | Refresh max_rows=200 для таблицы |
