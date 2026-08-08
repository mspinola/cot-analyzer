# Amendments owed to sibling docs, 2026-08-07

Corrections to living docs that live in **sibling checkouts**, recorded here rather than by
editing a shared working tree that other sessions have checked out. Each entry names the target
doc, what changes, and the measurement that forces it. Porting an entry upstream is a separate
change in that repo.

Convention carried forward from `crowdmon`: measure rather than assume, and when a measurement
contradicts a doc, fix the doc in the same change and say where the fix was recorded.

---

## A1. `cotmetrics/docs/positioning-series-properties.md` §3: the open check is now closed

**Status: measured. §3's core question is answered and one of its stated expectations is wrong.**

Measurement: [`../analysis/2026-08-07-spearman-level-null.md`](../analysis/2026-08-07-spearman-level-null.md).
Reproducer: `cot-analyzer/scripts/measure_spearman_null.py`, seed 20260807, 47 markets,
`COTDATA_STORE` manifest `schema_version` 2 with COT through 2026-08-04.

### What §3 asked, and the answer

> Until it is [measured], there is no way to say whether a `comms_spearman` of -0.6 is
> informative or ordinary.

**Ordinary.** At the 26-week lookback the null distribution of |rho| has median 0.386 and p95
0.809, so -0.6 sits at about the 75th percentile of the null. A reading must exceed roughly
**0.81** to clear a 5% two-sided band.

### What §3 got wrong

§3 predicts that the band **widens** with window length, and names the 52-week columns as the most
exposed. Measured, it **narrows** monotonically:

| W | p95 of \|rho\| under the null |
|---|---|
| 13 | 0.846 |
| 26 | 0.809 |
| 52 | 0.773 |
| 104 | 0.744 |

The 13-week window is the widest, and that is the window
`signals.py::_append_spearman_regime_shift_signal` reads. §3 reasoned from the pure-unit-root
regression case where the spurious statistic diverges with sample size; these series are
persistent but not pure unit root, so a longer window buys effectively-independent observations.

The correction flips the ordering, not the verdict: p95 falls only from 0.809 to 0.744 when the
window is quadrupled.

### What §3 got right

- The structure is the same as §2's and the band is wide, so the "each column needs its band
  published beside it" branch of §3's own disposal rule applies.
- The first-difference form is the one that carries information here too. At W=26 the differenced
  null has median 0.138 and p95 0.390 against a real median of 0.485.
- The stakes statement is unchanged: `npf` consumes none of these columns, so these are displayed
  indicators only and no traded input moves.

### Suggested edit to §3

Replace the "window length cuts the wrong way as it grows" paragraph with the measured ordering,
retitle the section from an open check to a closed one, and cite the analysis above for the per
window bands. Leave §1 and §2 untouched: neither is affected.

**Not yet ported.** Doing so is a `cotmetrics` change and wants its own PR.
