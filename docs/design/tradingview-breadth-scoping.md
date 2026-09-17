# TradingView breadth for the tape context: FOMO, net new highs, and what the connector changes

**Date:** 2026-09-16
**Status:** scoping, no code. Supersedes the vendor question in marketdata's
`docs/design/breadth-domain-scoping.md` (2026-09-13); the amendment is recorded in
[amendments-2026-09-16.md](amendments-2026-09-16.md). Revised the same day once it was
established that the Windows producer box runs Claude Code Desktop on this account, so the
connector is schedulable there (§2).
**Why now:** the 2026-09-13 session wanted the AGI breadth reads (the "FOMO" share of stocks
above their 5-day average, net new 52-week highs and lows) beside COT positioning, found
that Norgate does not publish the 5-day share at any tier, and settled for four ETF ratios as
proxies (cot-analyzer #123, marketdata #29, #30). A TradingView connector is now attached to
Claude sessions, and it serves the exact series the AGI Pine scripts read. This document
records what that changes, what it does not, and how the series would reach the app.

---

## 1. What the connector serves

Probed 2026-09-16 through `get_ohlcv` (daily bars, `count=5000`, the cap). Every symbol the
two Pine scripts name resolves, and so does the wider family.

| symbol | what it is | first bar | bars served | close 2026-09-16 |
|---|---|---|---|---|
| `INDEX:NCFD` | Nasdaq Composite, % above 5-day average (FOMO, the default) | 2018-12-07 | 1952 (all) | 32.23 |
| `INDEX:S5FD` | S&P 500, % above 5-day average (FOMO, alternative) | 2017-01-03 | 2440 (all) | 27.43 |
| `INDEX:HIGQ` | Nasdaq stocks at a new 52-week high | 2006-10-30 | 5000 (cap) | 46 |
| `INDEX:LOWQ` | Nasdaq stocks at a new 52-week low | 2006-10-31 | 5000 (cap) | 110 |
| `INDEX:HIGN` / `INDEX:LOWN` | the NYSE pair | 2006-10 | 5000 (cap) | 38 / 86 |
| `INDEX:MAHN` | NYSE new highs, the alternative filter | 2006-10 | 5000 (cap) | 38 |
| `INDEX:NCTW` / `INDEX:NCTH` | Nasdaq Composite, % above 20-day / 200-day | 2018-12-07 | 1952 | 22.98 / 53.83 |
| `INDEX:S5TH` | S&P 500, % above 200-day | 2003-12 | 5000 (cap) | 50.09 |
| `USI:PCC` / `USI:PCCE` | Cboe total / equity-only put-call ratio | 2006-10 / 2007-01 | 5000 / 4943 | 0.96 / 0.90 |

Validation: the `NCFD` close for 2026-07-29 is 48.05, and the EDGE report of that date printed
FOMO 48%. That is the same check `agi/import_fomo.py` runs on the manual CSV export, so the
connector and the export are the same series. `get_symbol_data` returns "no data" for the
`INDEX:` symbols, so `get_ohlcv` is the only door; the screener has no 5-day-average column
either, so a rebuild from constituents is not on offer here any more than it was from Norgate.

What this removes from the 2026-09-13 scoping:

- The Norgate US Stocks purchase question. Nothing here needs it.
- The "20-day share is the honest substitute" compromise. The 5-day share is published.
- The "compute it from constituents" fallback, with its survivorship problem. Not needed.

## 2. How the series reach the store: Claude on the producer box

**The connector is a claude.ai connector, not a library.** `session_connectors_status` reports
TradingView as a hosted connector (`kind: connector`); it is reachable from a Claude session
signed in to this account and from nothing else. The Windows producer box (`NUCBOX_M8`)
runs Claude Code Desktop on this account, and the Desktop app's **local routines** run on
the machine itself, on a schedule, with the local filesystem and the account's connectors
(docs: `code.claude.com/docs/en/desktop-scheduled-tasks`; connectors load whenever the
active login is the claude.ai subscription, `docs/en/mcp`). That makes a scheduled Claude
run on the box a legitimate producer step: it writes into `MARKETDATA_STORE` on the box,
and the existing `sync-store.cmd` / `push-to-server.cmd` pair delivers it to both replicas
like everything else. The workspace's data rule is untouched: the producer writes,
consumers read, and nothing is seeded on the Mac.

The paths, and the verdict:

| | path | verdict |
|---|---|---|
| A | A **local routine on the box**: Claude pulls the bars through the connector, writes the tool results verbatim to a raw directory, and runs one `.cmd` that builds the store and syncs. All logic in code; the agent is transport. | **recommended** |
| B | A `tradingview` provider in marketdata using an unofficial Python client (`tvdatafeed`, GitHub-only) on the box's existing Task Scheduler | fallback if A's app-must-be-running constraint (§5) proves unworkable. Same feed underneath, one more unofficial dependency to own |
| C | A cloud routine pulls through the connector and commits a CSV to a repo the producer ingests | cloud routines have no local filesystem; a git repo as a data bus. No |
| D | The manual TradingView CSV export, the agi repo's current path | a one-off backfill at most. No |

### 2.1 The shape of path A

It is marketdata's databento pattern (`--ingest-databento` raw, then `--build-databento`
deterministic and offline) with the paid API replaced by a Claude session, and it inherits
that pattern's rule: **the raw directory is producer-internal, never part of the consumer
contract, and out of every store sync.**

1. **The registry** gains the `series` domain from the 2026-09-13 scoping doc and entries
   for the symbols in §1, each with a `tradingview: "INDEX:NCFD"`-style key and a
   store-safe internal name. Nothing else about the domain design changes: `raw` tier
   only, stored as served, `Close` is the value, `get_bars` resolves to it, `asof=` raises.
2. **The routine's instructions live in the repo**, versioned, beside the other wrappers
   (`scheduler\series-routine.md` on the box), and the routine's prompt is one line
   pointing at that file. The steps it prescribes, in order, and nothing else:
   - for each registry series symbol, one `get_ohlcv` call, `interval=1D`, `count=10`;
   - write each tool result **verbatim** to
     `%MARKETDATA_STORE%\_raw\tradingview\<internal>\<YYYY-MM-DD>.json`;
   - run `scheduler\run-series.cmd` and report its exit code and printed summary.
3. **`run-series.cmd`** does what the other wrappers do, with per-step `ERRORLEVEL`
   capture on its own following line: `marketdata-update --domain series
   --build-tradingview`, then `sync-store.cmd`, then `push-to-server.cmd`.
4. **`--build-tradingview`** is the producer proper: it parses the raw files, validates
   (§2.2), appends only bars the store does not hold, writes the parquet atomically, and
   touches the manifest under `series/tradingview/<internal>`. Idempotent: a second run on
   a night the store is already current writes nothing and says so. Stale input (newest
   bar older than the expected session) is a refusal with a non-zero exit, the analogue of
   the futures defer, so a re-run later in the evening is the retry.
5. **Schedule**: two daily routines on the box, weekdays, about 18:30 and 21:30 Eastern
   (after the 17:30 equities task; the connector's notice says the last bar may still
   change, and a breadth count computed from closes is settled well before 18:30). The
   second is the retry; on a good night it is the no-op in step 4.
6. **The backfill** is one interactive session on the box: `count=5000` for every symbol
   into the same raw directory, then the same build. `NCFD`'s 1952 bars are its whole
   published history; the 2006 series exceed the cap and the cap exceeds every board
   window.

### 2.2 What stands between an LLM and the store

The producer has a language model in it, and the design has to assume the model can
mis-transcribe, skip a symbol, or stop half way. Every guard is in the build step, which
is code, not in the prompt:

- **No number passes through prose.** The routine writes tool results verbatim to files;
  the build parses JSON. A file that is not the connector's JSON shape is refused by name.
- **Overlap agreement.** Every bar in a raw file whose session date the store already holds
  must equal the stored value exactly (the vendor prints two decimals). Any mismatch
  refuses the whole file and names the bar. With `count=10` nightly, nine of ten bars are
  overlap, so a slip on an existing bar is caught that night, and a slip on the new bar is
  caught the next night when it becomes overlap. The build never rewrites a stored bar: a
  genuine vendor restatement surfaces as a refusal for a human to resolve, which is the
  workspace's posture on restated history everywhere else.
- **Shape and range.** Timestamps strictly increasing and each on a US session date; percent
  series within 0 to 100; counts non-negative integers; put/call within (0, 10). The
  `agi/import_fomo.py` range check, made general.
- **Session gate.** The newest bar's session date must be the expected one for the run
  (today's, on a weekday after the close), else refuse stale, non-zero, nothing written.
- **Pinned anchors.** Registry-level `anchors` per series (`NCFD 2026-07-29 = 48.05`, the
  EDGE-report check; one per series from a published reading where one exists), verified
  on every build that touches those dates and on every backfill. This is the standing
  proof that the symbol string still names the same series.
- **Least privilege on the routine.** Its allowed tools are the one connector call, writes
  under the raw directory, and the one `.cmd`. Anything else stalls the run rather than
  proceeding, which the Desktop app's per-routine permission mode provides.
- **Bounded cost.** About eight tool calls and one command per night; cap the turns.

### 2.3 What the routine cannot do and the verifier must say

`verify-scheduling.ps1` inspects Task Scheduler tasks; a Desktop routine is not one. The
verifier gains a **store freshness** check on `series/tradingview/` (the same shape as the
futures and equities checks, which is what actually matters) and a **GUARD PROOFS** line
saying that the routine's existence, schedule and permission mode cannot be checked from
the script. A night the series did not update is caught by the freshness check the next
morning and by cot-analyzer's stale note, never by the routine's own logs.

## 3. FOMO is not a weekly quantity, so it is not a tape-context row

Measured in
[../analysis/2026-09-16-fomo-weekly-sampling.md](../analysis/2026-09-16-fomo-weekly-sampling.md):
over the last 300 sessions the board's Tuesday sample sees 1 of 5 exhaustion episodes and 1
of 8 deep-fear episodes, because the median zone visit lasts one session and the series has
a lag-5 autocorrelation of about zero. Net new highs carry a three-consecutive-day regime
rule and fail the same way for the same reason.

That sorts the candidates into two renderings, and the split is by the series' own
timescale, not by taste:

**Daily, absolute-zone (a new component, not a `ContextRatio`).** FOMO (`NCFD`, with `S5FD`
selectable), Nasdaq net new highs (`HIGQ - LOWQ`, both legs kept, per the agi notes). Drawn
as the last 60 sessions with the published zones as bands (SWG: above 80 exhaustion, 35 to
60 neutral, below 20 to 25 fear, plus the directional "positive recovery" phase, all cited to
`agi/docs/02-RULES.md` M-07 and duplicated here because cot-analyzer cannot import a private
repo) and the current reading with its zone label. Net highs carry the three-day regime
colour. The read is the vendor's level against the vendor's cutoffs; nothing is
re-normalised.

**Weekly, range-index (fits the existing `ContextRatio` frame with a small generalisation).**
Share above the 200-day (`S5TH` or `NCTH`), and a smoothed put/call ratio (`PCC`, 10-day
average, the conventional read). These move over weeks and a Tuesday close is a fair sample.
`ContextRatio` needs a single-series variant (a `ContextSeries` with one leg and a
`transform`), and the orientation rule holds: high end is the fearful or washed-out side.
Put/call is already oriented that way; share-above-200 is not, and would be drawn as
`100 - value` with the flip stated in the hint, or left off the board and drawn beside FOMO
instead. Decide when the row exists, not here.

The governance carried over from the 2026-09-13 work stands: context, not signal; nothing
here has been through the evaluation ladder or crucible; every series stays separate; no
composite "fear" number, because a composite is what crowdmon was. A zone label is a
published cutoff restated, not a verdict.

Where the zone function lives: cot-analyzer computes no metrics of its own, and a study of
FOMO trough depth already exists in the agi repo (`docs/45-PREREG-FOMO-TROUGH-DEPTH.md`), so
an npf study wanting the same cutoffs is likely. Put `fomo_zone(value)` and the net-highs
regime in `cotmetrics.indicators` beside `calculate_range_index`, cited to the SWG, and let
the app call them.

## 4. What else the connector makes possible now

Independent of the store work, each usable in a session today:

- **The agi repo's manual step is gone.** `import_fomo` and `import_net_highs` document a
  TradingView chart export as their one manual input. A session can pull `NCFD`, `HIGQ` and
  `LOWQ` through the connector and feed the same importers; the 48.05 check is the
  acceptance test either way.
- **A backfill of record** for the store, the first session the routine's raw directory
  exists: 1952 bars of `NCFD` is the whole published history, and the 5000-bar cap on the
  2006 series covers every board window, including the 104-week full-history floor,
  several times over.
- **Cross-checking a nightly bar** against the connector when a producer run looks wrong,
  the way Yahoo's VIX3M was caught in July.
- **Put/call as positioning.** `PCC` and `PCCE` are the only series here that measure
  positioning rather than breadth, which makes them the nearest cousin to COT on the board.
  Both run back to 2006 and 2007.
- **What it does not offer:** the economic-data catalogue has no retail-sentiment survey
  (searching "sentiment" returns four business-survey series, no AAII), the screener cannot
  see `INDEX:` symbols, and the `get_ohlcv` notice says bars are delayed and the last bar may
  still change, so a session read during the US day is not the close.

## 5. Things that will bite

- **The Desktop app has to be running on the box.** A local routine fires only while the
  app is open; every other producer step is a Task Scheduler task and survives a reboot
  without anyone logging in. The box already keeps an interactive desktop session because
  NDU needs one (`cotdata prices` runs only when the user is logged on), so the constraint
  is not new, but a reboot that relaunches NDU and not the app stops the series silently
  while everything else keeps running. Put the app in the same start-up path as NDU, and
  rely on the freshness check (§2.3), not on noticing. The Desktop app catches up one
  missed run within seven days on the next launch, which covers a short outage and not a
  long one.
- **The connector can need re-authorising.** A lapsed connector stalls or fails the
  routine; the freshness check and the stale note are the detection, as above. If it
  becomes chronic, path B in §2 is the fallback.
- **The feed is unofficial either way.** TradingView publishes no data API for these
  symbols; the connector rides the charting websocket and can change or refuse without
  notice. The store already tolerates a vendor that stops (Yahoo's `^VIX3M` stopped on
  2026-07-17 and the row said so for two months), and that is the model: a dead
  `tradingview` vendor produces a stale note and an "awaiting data" row, never a wrong
  number and never a blank board.
- **Symbol strings are TradingView's, not Barchart's.** `HIGQ`, `LOWQ`, `NCFD` are the
  strings the Pine scripts use and the ones the connector resolved; `MAHN` is a different
  NYSE filter, and the agi notes record a member getting a different number from a
  different filter. Registry entries carry the `INDEX:`-qualified string in a `tradingview`
  key, and internals stay store-safe (`NDX_FOMO_5D`, `NDX_NH52W`, `NDX_NL52W`,
  `SPX_PCT_ABOVE_200D`, `CBOE_PCC`); fix the scheme when the entries are written. The
  pinned anchors (§2.2) are what catches a string that quietly starts naming something else.
- **`_raw\tradingview` must be outside both syncs.** databento's raw store is already
  producer-internal; confirm on the box that `sync-store.cmd`'s bars pass excludes `_raw`
  (the share was not mounted during this scoping) before the first routine run, or the raw
  JSON rides to both replicas.
- **`NCFD` starts 2018-12-07.** About eight years, enough for every board window and the
  104-week floor, not enough for a 2008 look. `S5FD` adds two years. The 2006 series do not
  have this problem.
- **The daily panel needs the daily store read, not the weekly collapse.** `tape_context`
  collapses everything to Tuesdays on purpose. The FOMO component reads the daily frame and
  must not go through `weekly_close`.
- **Editable-install phantom, again.** The `series` domain lands in marketdata; the app's
  venv sees it only when the shared `marketdata` checkout moves. As of 2026-09-16 that
  checkout is parked on a deleted branch five commits behind `origin/main`, which is why the
  VIX3M row reads one bar today. Move it before judging any of this from the app.

## 6. Order of work

1. Fix the stranded `marketdata` checkout (a `checkout main` and a fast-forward pull), so
   the VIX3M row and everything after it can be judged from the app. No code.
2. On the box, in an interactive session: one connector pull of `NCFD` with `count=10`,
   saved verbatim to a scratch file, to prove the connector is attached to that account on
   that machine and to fix the JSON shape the build will parse. Ten minutes, and it settles
   the only fact this document takes on the user's word.
3. `cotmetrics.indicators`: `fomo_zone` and the net-highs regime, cited to the SWG cutoffs,
   with tests on the boundary values.
4. marketdata: the `series` domain per the 2026-09-13 scoping doc (its steps 3 and 4, store
   layout tests included), `--build-tradingview` with the §2.2 guards each under test, and
   the registry entries with anchors. No network in any of it: the build reads files.
5. On the box: `run-series.cmd`, `series-routine.md`, the two routines, the `_raw` sync
   exclusion confirmed, the backfill session, the `verify-scheduling.ps1` freshness row and
   GUARD PROOFS line. Run the verifier. Next morning: `marketdata-update --check` and the
   manifest entries under `series/tradingview/`.
6. In parallel with 4 and 5, and at no cost to the store: replace the agi repo's manual
   export with a connector pull for `NCFD`, `HIGQ`, `LOWQ` through the same importers, with
   the 48.05 check as acceptance.
7. cot-analyzer: the daily FOMO and net-highs component on the crowd page, reading the daily
   series; then, if wanted, the single-series weekly rows for share-above-200 and put/call.
   Awaiting-data behaviour identical to the ratios: the board never depends on the price
   store to draw positioning.

Bottom line, in words: the connector answers the data question the last session could not
(the exact FOMO and net-highs series exist, with enough history), and because the producer
box runs Claude on this account, a local routine there can be the producer, with every
number validated by code before it reaches the store. The measurement still says FOMO must
be drawn daily against its published zones rather than as a fifth weekly context row.
