# Как исследовать трейдеров на Polymarket (и почему это важно)

**Для кого:** AIPP / `aipp-trading` и ресерч BTC Up/Down 15m.  
**Инструмент:** [`polymarket-trader-intel`](https://github.com/sergio12S/polymarket-trader-intel) (CLI + MCP).  
**Не финсовет и не copy-trade.** Цель — отличать реальные стили от маркетинга и брать из них **гейты**, а не размеры чужих кошельков.

См. также: [research-btc15m-earners.ru.md](research-btc15m-earners.ru.md) · [adapt-from-earners.ru.md](adapt-from-earners.ru.md).

---

## Почему это важно

В X и Telegram постоянно показывают «ботов с ровной кривой» на Polymarket BTC 5m/15m. На вид — лёгкие деньги. На деле часто смешаны:

1. **Другой бизнес**, не «угадал свечу» (complete-set / market making: покупка Up и Down).
2. **Скрейп фаворита** (вход по 0.85–0.95) → почти 100% WR, копеечный EV.
3. **Late sniper** с джекпотами — не стабильная линия.
4. **Скриншоты и демо** без проверяемого кошелька (иногда outright fake).
5. **Кривые метрики API** — closed-positions по умолчанию сортирует по PnL → фейковый winrate.

Без разбора кошельков легко:

- скопировать стратегию, которой у тебя нет капитала/латентности;
- оптимизировать WR вместо EV;
- принять рекламу за edge и сжечь депозит (как на mid-momentum chase).

Исследование трейдеров нужно, чтобы **назвать стиль**, проверить цифры TIMESTAMP-ом и решить: антипаттерн, идея для гейта, или «не наш спорт».

---

## Что часто оказывается фейком или обманом ожидания

| Выглядит как | На самом деле |
|--------------|---------------|
| «100% winrate бот» | Ask ~0.9, профит центы; WR — артефакт цены |
| Ровная equity в видео | MM / complete-set / нарезанный период / анимация |
| «Скопируй кошелёк» | Один джекпот или неделя удачи на новом аккаунте |
| Лидерборд PnL | Fed/спорт/другие рынки, не BTC 15m |
| Lifetime +$500k | На коротком окне BTC closed может быть ~50% WR |
| «Grok/AI agents делают $X/день» | Иногда скриптовое демо без on-chain fills |

**Правило:** нет адреса кошелька + TIMESTAMP closed PnL + avg entry price → не верь цифре.

---

## Пошаговый метод (простой)

### 1) Найти, кто вообще торгует BTC 15m

Общий PnL-лидерборд ≠ BTC 15m.

```bash
cd /Users/serg/projects/my_trading/polymarket-trader-intel
PYTHONPATH=src python3 -m trader_intel discover-btc15m --scan 4000 --limit 15
```

Сканирует недавние глобальные трейды и тянет активных по `btc-updown-15m`.

### 2) Честный closed PnL (обязательно TIMESTAMP)

```bash
PYTHONPATH=src python3 -m trader_intel closed-pnl 0xWALLET --max-rows 200
```

Смотри: `n`, `wr`, `pnl`, `avg_price`, `max_win` / concentration, `sort_by` должен быть `TIMESTAMP`.

Опционально пачка + фильтр «stable»:

```bash
PYTHONPATH=src python3 -m trader_intel stable-earners --scan-trades 4000 --top-wallets 20
```

### 3) Стиль входа

```bash
PYTHONPATH=src python3 -m trader_intel pull 0xWALLET --max-trades 400
PYTHONPATH=src python3 -m trader_intel why 0xWALLET
```

Вопросы:

- early / mid / late внутри 15m?
- avg price: mid (~0.4–0.65) или фаворит (&gt;0.8)?
- только BUY или ещё SELL?
- оба исхода на одном рынке (complete-set)?
- возраст аккаунта и N сделок?

### 4) Сверить с рекламой

Если в X показали профиль — сверь адрес, окно времени и avg price. Ролик без адреса = красный флаг.

### 5) Решить для AIPP

| Находка | Действие |
|---------|----------|
| Favorite scrape | Антипаттерн → **G4 ASK_MAX** |
| Mid directional (deepmoat-like) | Идея mid-band / edge gates |
| Late sniper | Отдельный shadow-бакет, не ломать open+25s |
| Complete-set / MM | Не копировать в $1 runner |
| Новый аккаунт / один джекпот | Игнор «stable» |

---

## Ловушка API (запомни)

`GET https://data-api.polymarket.com/closed-positions` **по умолчанию** отдаёт лучшие PnL сверху. Первые N строк без `sortBy=TIMESTAMP` выглядят как «все в плюсе».  
В `polymarket-trader-intel` клиент всегда шлёт TIMESTAMP. Не собирай WR руками без этого параметра.

После закрытия BTC 15m рынок часто **пропадает** из `gamma /markets?slug=…` и остаётся в `/events?slug=…` — так чинили resolve в `aipp-trading`.

---

## Минимальный чеклист перед «вау, надо копировать»

- [ ] Есть `0x…` адрес  
- [ ] Closed PnL с `sortBy=TIMESTAMP`  
- [ ] Известен **avg price** (не только WR)  
- [ ] Понятен стиль (scrape / late / MM / directional)  
- [ ] N и возраст достаточны (не 20 сделок за неделю)  
- [ ] Один вин не = половина всего PnL (или ты это осознаёшь)  
- [ ] Для AIPP есть **гейт**, а не «скопировать size»

---

## Связь с нашим стеком

- Ресерч и кейсы → `doc/research-btc15m-earners.ru.md`  
- Адаптация → G4 shadow в `cycle_runner` (`ASK_MAX=0.70`, `GATE_SHADOW=1`)  
- Live PnL → `trades.db` + `resolve_trades.py` (Gamma events fallback)

Итог: исследование трейдеров — это фильтр от фейков и чужого бизнеса, а не источник «сигналов для копирования».
