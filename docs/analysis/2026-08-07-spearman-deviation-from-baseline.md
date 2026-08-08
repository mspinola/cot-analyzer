# Is a Spearman reading a regime shift, or ordinary wandering off a signed baseline?

**Point-in-time analysis, 2026-08-07.** Companion to
[`2026-08-07-spearman-level-null.md`](2026-08-07-spearman-level-null.md), which measured the band
against a **zero-centred** null and explicitly deferred this question:

> A zero-centred null is the wrong null for a *regime shift* question. NQ's real level series has a
> median of -0.424, so +0.713 is a large deviation from that market's own baseline even though it
> is only an 8% event against a null centred on zero. [...] That is a different measurement and it
> has not been done here.

It has now. **The answer depends entirely on which reference class you are entitled to**, and the
two differ by a factor of about seventy.

## Reproducer

```bash
.venv/bin/python scripts/measure_spearman_null.py --market Nasdaq --regime-null
```

Seed 20260807, 2000 bootstrap paths per block length. Same store reference as the companion doc
(`schema_version` 2, COT through 2026-08-04).

## The null, and one that was rejected

The statistic has a strongly signed baseline (NQ commercial: mean **-0.342**, sd 0.432). A null
that is going to judge deviations from that baseline has to **reproduce** it first.

**Used: paired block bootstrap.** Resample the weekly changes `(dPrice, dPosition)` jointly in
blocks, so the contemporaneous relationship and the short-run dynamics both survive, then cumulate
back to levels. The relationship is constant by construction, so anything the rolling statistic
does in this world is wandering rather than a shift. Block length swept 13 to 104 (§1 of the
cotmetrics doc says blocks want to be at least 8 weeks and preferably longer).

It reproduces both moments of the real series, and does so better as the block lengthens:

| L | null mean | null sd |
|---|---|---|
| 13 | -0.242 | 0.441 |
| 26 | -0.290 | 0.436 |
| 52 | **-0.318** | **0.432** |
| 104 | -0.321 | 0.435 |
| **real** | **-0.342** | **0.432** |

**Rejected: an AR(1) in levels driven by price changes.** Fitted on NQ (`phi` 0.9167, stable under
rescaling), it produces a rolling statistic centred on **+0.002** rather than on the observed
-0.342. The mean reversion stops positioning from accumulating the price relationship, so the level
correlation washes out. A null that cannot generate the data's central tendency cannot be used to
judge deviations from it, so it is reported here as a discarded variant and nothing is concluded
from it.

## Result

NQ, commercial column, W=28, latest reading **+0.713**:

| L | P(a single week reaches it) | P(a 22-year path EVER reaches it) | threshold for path-level p < 0.05 |
|---|---|---|---|
| 13 | 0.0159 | 0.9530 | +0.923 |
| 26 | 0.0135 | 0.9125 | +0.915 |
| 52 | **0.0114** | **0.9335** | **+0.904** |
| 104 | 0.0115 | 0.9640 | +0.892 |

Stable across block length in both directions. And model-free, on the real series itself:

| level | distinct episodes reaching it | weeks (of 1,152) |
|---|---|---|
| >= +0.30 | 11 | 120 |
| >= +0.50 | 5 | 52 |
| >= +0.713 | **4**, one of which is the current one | 12 |

## What that means, and it is not one answer

**As a single week, the deviation is genuinely unusual: p is about 0.013**, roughly a one-in-eighty
week. That is materially stronger than the 0.082 the zero-centred null gave, so the objection that
prompted this measurement was correct: the earlier framing understated the reading.

**As evidence that the hedging relationship has changed, it is not evidence at all.** A world where
the relationship never shifts produces a reading at least this extreme somewhere in a 22-year
history **91% to 96% of the time**. To clear a 5% path-level bar the reading would have to reach
about **+0.90**, and it is at +0.713. The real series corroborates directly: NQ has been here
three times before.

The gap between 0.013 and 0.93 is entirely multiplicity. There are ~1,150 weekly readings in the
history, so any *nominated* one being extreme is unusual while *some* reading being extreme is
near-certain.

**Which number applies is a question about how the reading was found, not about the data.** If NQ
at this date had been nominated in advance, 0.013 is the right figure. If it was noticed because
the reading stood out, the path-level figure is the honest one, and the true multiplicity is larger
still: the dashboard carries 47 markets times 6 columns times 3 lookbacks, and nothing about
scanning them is recorded.

That is the same shape as the multiple-testing discipline `crucible` enforces through
`SearchSpaceLog`. A dashboard has no such log, which is precisely why a displayed indicator cannot
carry a pre-registered claim.

## What would settle it

Not more measurement of this reading. Either nominate the market and the date in advance and wait,
or evaluate the rule that a positive commercial Spearman implies something, across all markets and
the full history, under a proper gate. The second is a `crucible` job with a search-space
denominator, not a dashboard observation, and per npf/AGENTS.md it is not the same session's job to
render that verdict.

## Bottom line, in plain language

Pushing back on "a lean at best" was right, and half-right. Measured against a null that reproduces
NQ's own strongly negative baseline, this week's +0.713 is about a one-in-eighty week, which is a
good deal stronger than the one-in-twelve the earlier zero-centred null suggested.

But that number only applies to a market and a date picked in advance. Looked at the way this one
actually was, as the striking reading on a dashboard of hundreds of series, a world in which
nothing changed at all throws up something this extreme somewhere in twenty-two years more than
nine times in ten. NQ itself has done it three times before. You would need roughly +0.90 before
the reading could carry a regime-change claim on its own.

So: stronger than a lean as an observation about this week, and weaker than a lean as evidence that
the relationship has shifted. Both are true, and which one matters depends on whether the market
was chosen before the number was seen.
