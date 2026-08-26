# What a setup card already implies

**Point-in-time analysis, 2026-08-25. Not amended after this date** (see the doc lifecycle note
in the workspace CLAUDE.md: `analysis/` is a record of when a thing was learned).

Answers a question raised while rebuilding the Home page. The setups tier draws positioning and
nothing else, so everything else the app knows about a market needs the screener card below it or
a click through to OI Alignment. The obvious fix is to lift the screener's readings onto the
setups cards, and the worry about doing it was ink: those cards read well because they are spare.

Ink turned out to be the wrong objection. **On the rows those cards draw, the screener's readings
are not independent of the strip already on the card. Over 551 gate market-weeks under NPF and 541
under Raw CLS, tape bias, WillCo and the six-week move never once pointed against the positioning
that put the row there.** Drawing them would add decoration, not information. The one candidate
that positioning cannot imply is how long the market has been at its gate, and that is what the
badge now carries.

## Reproducer

```bash
.venv/bin/python scripts/measure_setup_card_redundancy.py --out docs/analysis/2026-08-25-what-a-setup-card-already-implies.json
```

Run from the `cot-analyzer` repo root with the environment `run-local.sh` sets. Nothing here is
sampled, so there is no seed and a rerun against the same store reproduces every figure. Full
output, including every conflicting market-week by name and date, is in the JSON beside this file.

**Data reference.** `COTDATA_STORE` at `~/code/cotdata_store`, all four report families at
`newest_data` **2026-08-18**. `COTMETRICS_PARAMS` pointed at the private
`cotmetrics-config/params.yaml`, giving **42 markets across 9 asset classes** after the `heldout`
exclusions. Prices come from `MARKETDATA_STORE` at `~/code/marketdata_store` by way of the tape
synthesis. The window is the trailing **52 weeks**, and the positioning window is each market's own
tuned lookback under the default `Custom` setting.

## What was measured

Direction, not value. A reading that always points the same way as the positioning beside it is a
restatement of the strip however independently it is computed, so each reading is reduced to
bull / bear / flat on the app's own thresholds and compared with the side the Commercial index is
on. Only market-weeks the model calls a setup or a near-setup count, because those are the only
rows the tier ever draws.

| reading | source | rule |
|---|---|---|
| tape bias | `synthesis.generate_exhaustive_tape_synthesis` | its own `tape_bias` verdict |
| WillCo | `WILLCO_ALIAS` | `>= 80` bull, `<= 20` bear |
| LW Lrg sentiment | `LW_LRG_SENTIMENT` | **inverted**, `<= 20` bull, `>= 80` bear |
| Move, 6wk | `COMM_MOMENTUM` | `>= 40` bull, `<= -40` bear |
| price trend | `bullish_trend_continuing` / `bearish_trend_continuing` | whichever flag is set alone |

`flat` is tallied separately from `conflict` throughout. A reading that is usually silent is not
redundant, it is absent, and those are different reasons not to draw something.

Both models are measured independently rather than pooled. They are not nested: a market can be an
NPF setup while its CLS legs are only close, so a result on one is not a result on the other.

## Result 1: four of the five readings never disagree

Counts are market-weeks. The last column is conflicts as a share of all gate market-weeks.

**NPF CS 80/20, 551 gate market-weeks**

| reading | agrees | conflicts | flat | conflict rate |
|---|---:|---:|---:|---:|
| tape bias | 449 | **0** | 102 | 0.0% |
| WillCo | 491 | **0** | 60 | 0.0% |
| LW Lrg sentiment | 392 | 11 | 148 | 2.0% |
| Move, 6wk | 127 | **0** | 424 | 0.0% |
| price trend | 1 | 1 | 549 | 0.2% |

**Raw CLS 95/5, 541 gate market-weeks**

| reading | agrees | conflicts | flat | conflict rate |
|---|---:|---:|---:|---:|
| tape bias | 502 | **0** | 39 | 0.0% |
| WillCo | 504 | 3 | 34 | 0.6% |
| LW Lrg sentiment | 466 | **0** | 75 | 0.0% |
| Move, 6wk | 139 | **0** | 402 | 0.0% |
| price trend | 1 | 1 | 539 | 0.2% |

Three separate things are going on here and only the first is redundancy:

- **WillCo is a restatement by construction.** It is a Commercial-position measure, so it is
  extreme exactly when the Commercial index is. 3 conflicts in 1,092 market-weeks across both
  models is the noise floor of two differently-normalised readings of one series.
- **Tape bias is a restatement by composition.** It is a synthesis that already includes
  positioning among its inputs, so it inherits the side rather than testing it.
- **Move and price trend are not redundant, they are silent.** Move is flat on 77% of NPF gate
  weeks and price trend on 99.6%. A reading that says nothing 99.6% of the time cannot be the
  reason to add a row to a card.

LW sentiment is the only reading that disagrees at a rate worth a name, and only under NPF, at
2.0%. That is a real but thin signal to spend a permanent card element on.

The conflicts that do exist cluster on markets in the middle of the board. Under NPF on the
measurement date they are Japanese Yen, New Zealand and Palladium; under Raw CLS, New Zealand and
Heating Oil. **None of those markets was at a gate that week**, so none of them would have been
drawn in the setups tier at all.

## Result 2: age is independent, and it spreads

The strip looks identical whether a market reached its gate this week or ten weeks ago. On the
measurement date:

| model | rows at or near a gate | age spread |
|---|---:|---|
| NPF CS 80/20 | 13 | US Dollar 10w, DOW 10w, S&P 500 9w, Coffee 7w, Russell 3w, Cocoa 3w, 30-Year Note 2w, and six markets in their first week |
| Raw CLS 95/5 | 12 | Cocoa 7w, DOW 6w, Cotton 6w, US Dollar 5w, Copper 3w, then Russell, Gold and Coffee at 2w and four at 1w |

Six of thirteen NPF rows are new this week and two have been there for ten. Nothing else on the
card says so.

Ages differ between the two models for the same market on the same date (Cocoa is 3w under NPF and
7w under Raw CLS) because a run is counted in the model's own band, which is the same reason two
models disagree about the setup at all.

## Result 3: what fixes the walk cap

`PositioningModel.setup_age_from` walks backwards and needs a bound. Over the **full history** of
all 42 markets, the longest run either model has ever produced is:

| model | longest runs |
|---|---|
| NPF CS 80/20 | Palladium 51, Euro 50, Corn 44 |
| Raw CLS 95/5 | New Zealand 38, Copper 35, Palladium 33 |

The cap is set to `const.SETUP_AGE_CAP = 104`, roughly double the worst case ever observed, so in
practice it never binds. It exists so a market pinned indefinitely cannot turn a card render into a
full-history scan, and a count that reaches it is returned as it, which is why the badge renders
`104w+` rather than presenting the cap as exact.

## What this decided

- The screener's readings stay on the screener. Lifting them onto the setups cards was tested and
  rejected on evidence rather than taste.
- Setup age goes in the badge that already exists, as `SETUP · 3w`, quieter than the tier because
  the tier is still the headline.
- Max Pain Pull and OI Z-Score came off the screener card as well, for a different reason: neither
  bears on a positioning setup at all, so they were not candidates for this test.

## Limits worth stating

- **This is one 52-week window on one store.** The conflict rates are low enough that a longer
  window is unlikely to reverse the conclusion, but the specific counts are dated.
- **Direction is a coarse reduction.** Two readings can agree on side while disagreeing on
  conviction, and this test cannot see that. It is the right resolution for the decision it was
  built for, which is whether to draw a coloured mark, since a mark encodes side.
- **The measurement is a redundancy test, not a validity test.** Nothing here says WillCo or tape
  bias are wrong or useless. It says they add nothing *on rows that are already at a gate*, which
  is a statement about where to draw them, not about whether they work.
- **Price context remains an open question.** It is the obvious reading that positioning cannot
  imply, and the only price-trend flags on the frame are inert (set on 2 rows in 1,092). Answering
  it needs a price reading the board does not currently carry.
