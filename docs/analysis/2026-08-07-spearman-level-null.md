# The null band for the price-against-positioning Spearman columns

**Point-in-time analysis, 2026-08-07. Not amended after this date** (see the doc lifecycle note
in the workspace CLAUDE.md: `analysis/` is a record of when a thing was learned).

Closes the open check in
[`cotmetrics/docs/positioning-series-properties.md`](../../../cotmetrics/docs/positioning-series-properties.md)
§3, which states that the noise band for these columns "has never been measured on this data"
and that "until it is, there is no way to say whether a `comms_spearman` of -0.6 is informative
or ordinary".

It is ordinary. A reading of -0.6 sits at roughly the **75th percentile of the null** at the
configured 26-week lookback.

## Reproducer

```bash
.venv/bin/python scripts/measure_spearman_null.py --non-overlapping --market Nasdaq \
    --out docs/analysis/2026-08-07-spearman-level-null.json
```

Run from the `cot-analyzer` repo root with the environment `run-local.sh` sets. Seed `20260807`,
fixed; every draw comes from a seeded `Generator` and rerunning reproduces the tables below
exactly. Full output is in the JSON beside this file.

**Data reference.** `COTDATA_STORE` at `~/code/cotdata_store`, manifest `schema_version` 2.
`manifests/cot.json` at run time: 97 legacy codes, of which 49 carry `last_date` 2026-08-04 and
42 lag at 2026-07-21; disaggregated and TFF at 2026-08-04. 47 markets entered the panel
(`COTMETRICS_PARAMS` pointed at the private `cotmetrics-config/params.yaml`, `heldout` included,
because a null band is not a selection decision and excluding them would only cost power).

## What was measured

`CotIndexer` emits six `* Spearman` columns per lookback: commercial / large spec / small spec,
each raw and OI-normalised, each a rolling rank correlation between **price levels** and
**positioning levels** ([`indicators.py::calculate_spearman_correlation_vectorized`](../../../cotmetrics/src/cotmetrics/indicators.py),
wired at `CotIndexer.py:582`). The script recomputes the statistic itself so the identical code
path runs over the nulls.

Three nulls, because §3 prescribes only a synthetic series and that fixes the band to an
arbitrary choice of drift and volatility, when the question is what the statistic does on **this**
data:

| null | construction |
|---|---|
| `offset` | real price windows against real positioning windows **of the same market** from a different, non-overlapping stretch of time |
| `cross` | real price of market A against real positioning of market B, different asset classes, aligned on report date |
| `synthetic` | a driftless Gaussian random walk in place of price, positioning left real. §3's literal prescription |

`offset` is the strongest of the three: it preserves each series' autocorrelation and marginal
distribution exactly and destroys only the alignment. It rotates the **window index** rather than
the underlying series, so every pair is a genuine contiguous window of real data and no wrap-around
seam is introduced. Offsets are constrained so the two windows never share a week.

Everything is reported for both **levels** (what the columns publish) and **first differences**
(what §2's rule says to use), so the two are comparable on equal footing.

## Result 1: the three nulls agree, which is why the band is believable

At every window and every column the three constructions land within about 0.02 of each other,
and all three are centred on zero (`mean_signed` never exceeds 0.07 in absolute value). Commercial
column, levels:

| W | offset median | cross median | synthetic median |
|---|---|---|---|
| 13 | 0.418 | 0.418 | 0.412 |
| 26 | 0.386 | 0.390 | 0.378 |
| 52 | 0.353 | 0.359 | 0.346 |
| 104 | 0.326 | 0.335 | 0.308 |

Three quite different ways of destroying the relationship produce the same band. That mutual
agreement is the main reason to trust it.

## Result 2: the band on LEVELS is very wide

Commercial column, `offset` null, absolute value of the statistic:

| W | median | p90 | **p95** | p99 | share > 0.5 | share > 0.7 |
|---|---|---|---|---|---|---|
| 13 | 0.418 | 0.780 | **0.846** | 0.923 | 40.0% | 17.9% |
| 26 | 0.386 | 0.745 | **0.809** | 0.893 | 36.2% | 14.1% |
| 52 | 0.353 | 0.705 | **0.773** | 0.865 | 31.3% | 10.4% |
| 104 | 0.326 | 0.675 | **0.744** | 0.840 | 27.8% | 8.0% |

**At the configured 26-week lookback, a pair with no relationship at all produces |rho| above 0.5
on 36% of weeks and above 0.7 on 14%.** To clear a 5% two-sided band a reading has to exceed
**0.81**. The other five columns are within 0.05 of the commercial figures throughout;
OI-normalising moves nothing.

### The real series against that band

Commercial column, levels, W=26:

| | median \|rho\| | p90 | mean signed |
|---|---|---|---|
| real | 0.699 | 0.915 | **-0.519** |
| null | 0.386 | 0.745 | 0.000 |

The real series is distinguishable from the null in aggregate, but **the separation lives in the
sign, not the magnitude**. The null is symmetric about zero; the real distribution is
systematically negative for commercials (-0.519) and systematically positive for large specs
(+0.480) and small specs (+0.348). Meanwhile the *typical* real reading, 0.699, does not even
clear the null's 90th percentile of 0.745.

So the well-known reading of these columns, that commercials run negative because they sell into
strength, is real and strongly supported. How negative the number is in any given week is mostly
noise.

## Result 3: §3's window-length prediction is wrong, and inverted

§3 states:

> The window length cuts the wrong way as it grows. A longer window gives a spurious-regression
> problem more room, not less, so the 52-week columns are the ones most exposed, and they are
> exactly the ones a reader is most likely to treat as the reliable version.

Measured, the band **narrows monotonically** as the window grows: p95 goes 0.846, 0.809, 0.773,
0.744 across W = 13, 26, 52, 104. The **13-week** window is the most exposed, not the 52-week one.
That matters because 13 is the window
[`signals.py::_append_spearman_regime_shift_signal`](../../../cotmetrics/src/cotmetrics/signals.py)
reads.

The reasoning in §3 came from the pure-unit-root regression case, where the spurious statistic
diverges with sample size. These series are persistent but not pure unit root (§2 measured a
median lag-1 of 0.956 for MM positioning; NQ's commercial net is 0.915), so a longer window buys
more effectively-independent observations and the band tightens.

**The correction should not be read as reassurance.** The band tightens very slowly: quadrupling
the window from 26 to 104 moves p95 only from 0.809 to 0.744. The ordering flips, the verdict
does not.

## Result 4: on FIRST DIFFERENCES the band is tight and the real signal is clean

Commercial column, W=26:

| | median \|rho\| | p95 | p99 |
|---|---|---|---|
| real | 0.485 | 0.793 | 0.862 |
| offset null | 0.138 | 0.390 | 0.499 |
| cross null | 0.156 | 0.444 | 0.575 |

And at W=52 the null p95 falls to 0.275 while the real median holds at 0.478.

**The typical real differenced reading sits at about the 99th percentile of its own null.** This is
the contemporaneous flow relationship (specs buy, commercials take the other side), it is strong,
and unlike the level version it is not an artifact of persistence. §2's rule, test on first
differences against a band from the same panel, holds here exactly as it does for the
positioning-against-positioning case it was written for.

The `cross` null is consistently a little wider than `offset` and `synthetic` on differences
(0.156 vs 0.138 at W=26). That is real and expected: unrelated markets still share risk-on and
risk-off shocks, so cross-market differences are genuinely slightly correlated. It is the right
band to use if the question involves two different markets.

## Result 5: overlap is not inflating the bands

Rolling windows overlap heavily, so the pooled null is not a set of independent draws. Thinning
to disjoint windows only (`--non-overlapping`) moves p95 by at most 0.006 at any window:

| W | pooled p95 | disjoint-only p95 |
|---|---|---|
| 13 | 0.846 | 0.841 |
| 26 | 0.809 | 0.814 |
| 52 | 0.773 | 0.774 |
| 104 | 0.744 | 0.748 |

As expected: overlap costs precision in the tails of an estimate, but these are quantiles of a
distribution, not a test statistic.

## Worked example: NQ, the reading that prompted this

`--market Nasdaq`, commercial column at NQ's configured Custom lookback of 28 weeks, against
**NQ's own** offset null rather than the pooled one:

| basis | latest rho | own null p90 | own null p95 | own null p99 | two-sided null p |
|---|---|---|---|---|---|
| levels | **+0.713** | 0.690 | 0.759 | 0.851 | **0.082** |
| differences | **+0.348** | 0.316 | 0.375 | 0.483 | **0.069** |

**Neither clears a 5% band.** Both are marginal, around 7% to 8%.

One qualification, and it cuts the other way. A zero-centred null is the wrong null for a *regime
shift* question. NQ's real level series has a median of -0.424, so +0.713 is a large deviation
**from that market's own baseline** even though it is only an 8% event against a null centred on
zero. Measuring that properly needs a surrogate preserving the average strength of the real
relationship, then asking how often a trajectory reaches a given deviation from it. That is a
different measurement and it has not been done here.

## Disposal

§3 states its own rule: "If the bands are narrow, the indicators are fine as they stand and this
section becomes a footnote. If they are wide, each column needs its band published beside it."

**The bands are wide, so the second branch applies.** Concretely, and in rough order of cost:

1. The `* Spearman` level columns should carry their band wherever they are displayed, in
   `cot-analyzer`'s graph page and the positioning table. A p95 of 0.81 at the 26-week lookback
   is the number a reader needs and does not have.
2. `signals.py::_append_spearman_regime_shift_signal` reads the **widest-null** window (13 weeks,
   p95 0.846). Its `out_of_normal_bounds` gate is `comm_spearman_raw > -0.30`, which on this
   evidence is inside the noise for a single reading. The velocity term does absorb some of the
   level effect, as §3 anticipated, and how much has not been measured. That is the next check,
   not a defect claim.
3. Anywhere a *number* rather than a *sign* is being read off these columns, first differences
   are the better statistic and now have a published band.

**Stakes, restating §3 so this is not over-read.** `npf` consumes none of these columns; its only
`spearman` is `wfc_gate.correlation_method`, which touches no positioning level. These are
displayed indicators in `cotmetrics` and `cot-analyzer`, **not traded inputs**. Nothing in the
book changes because of this measurement.

## Amendment owed upstream

§3 of `cotmetrics/docs/positioning-series-properties.md` is now measured, and one of its stated
expectations (the window-length ordering) is measured wrong. That doc is the canonical home and it
lives in a sibling checkout shared with other sessions, so per the workspace convention the
correction is recorded here and in [`../design/amendments-2026-08-07.md`](../design/amendments-2026-08-07.md)
rather than by editing that tree. Porting it into §3 wants its own `cotmetrics` change.

## Bottom line, in plain language

The commercial Spearman columns are much noisier than they look. Over the 26-week lookback the app
publishes, two series with no relationship whatsoever hit a correlation above 0.5 more than a third
of the time and above 0.7 one week in seven, so a single reading has to exceed about 0.81 before it
means anything on its own. The part of these columns that is genuinely informative is the **sign**,
not the size: commercials really are systematically on the other side of price, and that shows up
far outside the noise. The same statistic computed on weekly **changes** instead of levels is
clean, with a band roughly a third as wide and a real signal sitting at its 99th percentile.

The doc's guess that longer windows would be the risky ones turned out backwards, the short
13-week window used by the regime-shift signal is the noisiest, but the band tightens so slowly
with window length that the correction changes the ordering without changing the conclusion.

And the NQ reading that started this, +0.713, does not clear a 5% band on either levels or
differences. It comes in around 7% to 8% on both, which is a lean and not a result.
