# Адаптация реальных earners под AIPP

Подробные кейсы кошельков: [research-btc15m-earners.ru.md](research-btc15m-earners.ru.md).


Не копируем кошельки и не тащим HFT/complete-set (gabagool и реклама в X).
Берём **измеримые гейты** поверх сигнала AIPP.

## Что взяли

| Паттерн | Откуда | Как у нас |
|--------|--------|-----------|
| Mid-price / не покупать «почти решённое» | deepmoat + анти-скрейп фаворитов (avg px 0.85–0.95) | **G7** `ASK_MIN`..`ASK_MAX` |
| Edge vs ask | уже было | **G3** `p_side > ask + 0.02` |

## Что не берём сейчас

- Complete-set / two-sided MM (нужен капитал и другая экономика)
- Late-only sniper как единственный режим (ломает open+25s AIPP) — позже отдельный бакет замера
- Копирование размеров китов

## Как включить G7 (ask-band)

Сначала только замер (live $1 не режется):

```bash
export GATE_SHADOW=1
export ASK_MAX=0.70
# optional: export ASK_MIN=0.35
# перезапуск cycle_runner
```

В логе будет `G7=False/True shadow=True`. В `trades.db` поля `g7`, `ask_max`, `gate_shadow`.

Когда накопится статистика «G7 отрезал бы и это были бы плохие fills» — hard:

```bash
export GATE_SHADOW=0
export ASK_MAX=0.70
```
