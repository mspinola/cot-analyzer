# Contracts against dollars, market by market

**Point-in-time analysis, 2026-08-24. Not amended after this date** (see the doc lifecycle note
in the workspace CLAUDE.md: `analysis/` is a record of when a thing was learned).

Answers the question raised by a third-party positioning report that draws the same speculative
position twice, once in net contracts and once in US dollar notional, each against its own
history. The question for this app is narrower than the report's: **the Crowding Strip already
draws a 0-100 positioning index per market, so is a dollar version of that index a different
series, or the same one wearing bigger numbers?**

It is a different series, but only on one of the two dollar rungs. **Dollar RISK parts from the
contract reading by a median 30 index points at the 95th percentile and changes the model's own
answer on 11.7% of weeks. Dollar NOTIONAL does not: over a rolling window it is very nearly the
contract count again.** That split is what decided which reading the strip draws and which one it
keeps to the hover.

## Reproducer

```bash
.venv/bin/python scripts/measure_dollar_wedge.py --out docs/analysis/2026-08-24-contracts-against-dollars.json
```

Run from the `cot-analyzer` repo root with the environment `run-local.sh` sets. Nothing here is
sampled, so there is no seed and a rerun against the same store reproduces every figure. Full
output is in the JSON beside this file.

**Data reference.** `COTDATA_STORE` at `~/code/cotdata_store`, `schema_version` 2, all four
report families at `newest_data` 2026-08-18, legacy 53 entries / 81,870 rows.
`MARKETDATA_STORE` at `~/code/marketdata_store`: 98 Norgate futures entries all at `last_date`
2026-08-21, 15 equities, and a 49-row `contract_specs` table written 2026-08-22.
`COTMETRICS_PARAMS` pointed at the private `cotmetrics-config/params.yaml`, so the universe is
47 markets including `heldout`, of which **45 can be priced**. The two that cannot are MSCI EAFE
and MSCI Emerging Mkts, which have no contract multiplier in the specs table: they are ICE MSCI
futures that Norgate carries no continuous series for.

## What was measured

One statistic, four series, everything else held constant. For each market the reading is
`indicators.calculate_range_index` over **that market's own tuned lookback**, which is the window
the page draws under its default Custom setting, applied to:

| series | what it is | who draws it |
|---|---|---|
| `raw` | Commercial net contracts | the Raw PF index |
| `norm` | Commercial net over open interest | the NPF index |
| `notional` | contracts x point value x price | nothing; hover only |
| `risk` | notional x daily volatility | the strip's dollar mark |

`cotmetrics.exposure` supplies the last two, on the tiers it insists on: `unadj` for price levels
and `propadj` for the volatility factor. The leg is Commercials throughout, matching the mark the
strip already draws. The Legacy legs sum to zero, so the speculator mirror is exact and the
choice of leg is presentation rather than measurement.

## Result 1: dollar risk is a different series, dollar notional is not

Per market, over every week both readings exist (44 markets clear the 104-week minimum):

| pair | correlation | p95 \|gap\|, index points | disagree on the band |
|---|---|---|---|
| contracts vs **risk** (Raw PF, 5/95) | **0.917** | **30.4** | **11.7%** |
| contracts vs notional (Raw PF, 5/95) | 0.979 | 14.5 | 5.4% |
| share of OI vs **risk** (NPF, 20/80) | 0.896 | 33.9 | **20.7%** |

All three figures are medians across markets. "Disagree on the band" means the two readings do
not land in the same one of the model's three bands (below its low gate, between, above its high
gate), which is the only difference between two lenses that changes an answer on this page.

The middle row is the useful negative. Notional is contracts times a slowly-moving price, so over
a 26 to 52 week window it is close to a monotone transform of the contract count and a second
mark for it would sit on top of the first. Risk multiplies by volatility, which moves on its own
schedule and is the term no positioning index can carry.

The third row is the largest of the three and is worth reading carefully: it compares two
different NORMALIZERS as well as two units, because NPF's index is already a share of open
interest. See Result 5 for why there is no dollar version of that share to compare against
instead.

## Result 2: it is not just "volatility is high"

The obvious deflation of Result 1 is that `risk = contracts x point value x price x sigma`, so the
gap could be nothing but a volatility chart wearing a positioning label. Measured against each
market's own daily volatility, as a range index over the same window:

- correlation of the gap with the volatility index: **0.25 at the median**,
- and it **flips sign across markets**: 33 of 44 positive, 11 negative.

The flip is the mechanism rather than noise. Volatility acts on a position that has a side, so the
same volatility collapse widens the gap upward on a short and downward on a long. A single
volatility overlay cannot reproduce this, because it does not know the sign of the position it is
scaling.

## Result 3: the gap is a state, not a jitter

Lag-1 autocorrelation of the gap is **0.918** at the median (p10 0.75, p90 0.95). A market whose
two lenses disagree this week disagreed last week. That is what makes it worth a mark on a weekly
board rather than a warning that fires and clears.

## Result 4: the live week, 2026-08-18

Of the 45 priceable markets, **13 disagree about the band** on the Raw PF reading and 11 on the
NPF reading. The three worth naming:

| market | window | contracts | dollars at risk | what changed |
|---|---|---|---|---|
| **Silver** | 24w | **0** | **96** | daily volatility fell from 6.7% to 2.7% across the window, so a record short (-44,792 lots) carries -$385m against the window's -$1,235m |
| **Natural Gas** | 70w | **99** | **9** | volatility fell from 7.9% to 2.5%; the largest contract position in the window is a fifth of the money the window has seen |
| **Gold** | 26w | **0** | **63** | Commercials are at their most short in contracts and in notional, and mid-range in risk, because volatility sits near the bottom of its own window |

Silver is the case the whole comparison was built from, and it is the one a boolean test misses:
it sits at the bottom of the contract range and near the top of the dollar range, which is both
ends of the axis at once. Counting "is it through a gate" scores that as agreement, which is why
`strip_traces.band_of` returns three bands rather than two.

## Result 5: a share of open interest is unit-free, exactly

Across all 45 priceable markets and every week in the store, the position's share of open interest
computed in contracts and computed in dollars at risk differ by at most **2.2e-16**.

This is algebra rather than a finding (the point value, the price and the volatility all cancel
between numerator and denominator), and it decides something concrete: **there is no dollar
version of the NPF basis to draw.** The dollar lens is inherently a LEVEL lens, so under NPF the
mark compares two different normalizations, and the caption has to say the window and the unit
rather than pretend only one thing changed.

## What this is not

Description, not a signal. Whether the gap predicts anything is a question for the ladder in
`npf`, judged by someone other than whoever proposed it, and the prior is not neutral: `crowdmon`
tested a close cousin of this (damage = crowding x illiquidity x fragility) across four
pre-registered tests and got no positive result. Nothing here licenses trading the wedge.

It is also not a claim about the printed report that prompted it. That report ranks a position
against its ENTIRE history rather than against a rolling window, which is a different statistic;
this app's expanding-percentile version of that question already lives on `/exposure`.

## Bottom line

In plain language: measuring the same positions in money instead of in contracts genuinely changes
the picture, and it changes it most where a reader would care, at the extremes. About one week in
nine, the two readings put a market in different bands, and this week thirteen of forty-five
markets are in that state, with silver the extreme case: the crowd's largest short of the year in
contracts is an ordinary-sized bet in dollars because volatility has halved. The effect is a
persistent state rather than weekly noise, and it is not simply a volatility chart, since the same
volatility move pushes the gap in opposite directions depending on which way the position leans.
The dollar-notional version of the same idea, which is what the source report plots, adds almost
nothing over a rolling window, so it is kept in the hover rather than drawn. None of this is
evidence that the gap predicts returns; it is a better description of what the position is.
