# Amendments owed to sibling docs, 2026-09-16

Same convention as [amendments-2026-08-07.md](amendments-2026-08-07.md): corrections to
living docs in sibling checkouts, recorded here rather than by editing a shared working tree.
Porting upstream is a separate change in that repo.

---

## A1. `marketdata/docs/design/breadth-domain-scoping.md` Part B: the 5-day share is published, by a different vendor

**Status: measured. The Norgate facts stand; the conclusion drawn from them no longer does.**

What Part B says:

> The 5-day share the FOMO script plots is not in the list. The shortest published window is
> 20 days. Reproducing FOMO exactly means computing it ourselves from constituents, which
> Norgate sells only at Platinum and above. The honest substitute is the 20-day share,
> labelled as such, never called FOMO.

What changes: the first two sentences remain true of Norgate. The third and fourth are
superseded. TradingView publishes the exact series (`INDEX:NCFD`, `INDEX:S5FD`, daily from
2018-12-07 and 2017-01-03), and the net new highs pair (`INDEX:HIGQ`, `INDEX:LOWQ`, from
2006-10). Validated against a published reading (2026-07-29 close 48.05, EDGE report 48%).
Measurement and the vendor question: [tradingview-breadth-scoping.md](tradingview-breadth-scoping.md) §1.

Consequences for Part B as written:

- The "Two facts to verify on the box" (which Norgate package carries breadth; the `#`
  symbol strings) are moot for FOMO and net highs. They still apply if the Norgate
  advance/decline family is ever wanted.
- The purchase decision in "Order of work" step 2 is removed for this use.
- The `series` domain design (store shape, `raw`-only tier, second vendor entry point,
  separate task with repeating trigger, finals gate on the series' own bar) is unchanged and
  is the design the TradingView provider should follow. Only the vendor module differs.
- The consumer note "The 20-day share is not FOMO" stays true and is now also unnecessary:
  the 5-day share is the row.

Two things the Norgate design did not have. The producer step is a Claude Code Desktop
local routine on the Windows box (the box runs Claude on this account, so the connector is
schedulable there), with the deterministic build in marketdata as `--build-tradingview` on
the databento raw-then-build pattern; §2 of the scoping doc. And the feed is unofficial, so
the vendor must be designed to die quietly (stale note, awaiting row) rather than assumed
permanent; §5.
