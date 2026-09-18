# TradingView breadth for the tape context: FOMO, net new highs, and what the connector changes

**Date:** 2026-09-16
**Status:** scoping, no code. Supersedes the vendor question in marketdata's
`docs/design/breadth-domain-scoping.md` (2026-09-13); the amendment is recorded in
[amendments-2026-09-16.md](amendments-2026-09-16.md). Revised the same day once it was
established that the Windows producer box runs Claude Code Desktop on this account, so the
connector is schedulable there (§2). Revised again 2026-09-17 with what was then verified on
the box itself: an interactive session and a local routine both reached the connector and
wrote identical bars, the sync scripts already exclude the raw directory, and both NDU and
the Desktop app relaunch on a reboot. Each such fact is marked "verified on the box".
**Built and live, 2026-09-17**: every step below landed the same day (cotmetrics 0.13.0,
marketdata 0.3.0 to 0.3.2, cotdata #114 and #115, and the panel in this repo). §7 records
the three places the build departed from this text.
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
   - load the TradingView tool schema (the connector's tools are deferred on the box too,
     verified on the box: the probe needed one schema-load call before the bars call);
   - for each registry series symbol, one `get_ohlcv` call, `interval=1D`, `count=10`;
   - write each tool result **verbatim** to
     `%MARKETDATA_STORE%\_raw\tradingview\<internal>\<YYYY-MM-DD>.json`, and do not
     print it back;
   - run `scheduler\run-series.cmd` and report its exit code and printed summary.

   The routine's folder is `C:\Users\matt\code\marketdata`, so the allow rules for
   exactly those tools (the schema load, the bars call as the box's session names it,
   writes under the raw directory, the one `.cmd`) go in that folder's
   `.claude\settings.json`, versioned with the repo, with the routine's own permission
   mode as the backstop. Verified on the box: the throwaway routine reached the connector
   and wrote the file, and it stopped twice for approval, once for the bars call and once
   for the write. Those two prompts are what the allow rules remove; unattended, either
   would stall the night.
3. **`run-series.cmd`** is `run-equities.cmd` with the fetch replaced by the build:
   `setlocal`, `MARKETDATA_STORE=C:\Users\matt\code\marketdata_store`,
   `MDEXE=C:\Users\matt\code\marketdata\.venv\Scripts\marketdata-update.exe`,
   then `"%MDEXE%" --domain series --build-tradingview` with `if errorlevel 1 exit /b
   %ERRORLEVEL%` on its own following line, then `call sync-store.cmd`, then `call
   push-to-server.cmd`, each guarded the same way, Mac sync first so that replica is
   current on a day the VPS is unreachable. No in-file retry loop: the equities wrapper
   retries because its fetch hits Yahoo, but this build reads local files, and the retry
   here is the second routine (step 5). The three wrapper rules carry over verbatim: no
   angle brackets anywhere in the file, `ERRORLEVEL` captured on the line after the
   command, and the exit code of the last command is the wrapper's.
4. **`--build-tradingview`** is the producer proper: it parses the raw files, validates
   (§2.2), appends only bars the store does not hold, writes the parquet atomically, and
   touches the manifest under `series/tradingview/<internal>`. Idempotent: a second run on
   a night the store is already current writes nothing and says so. Stale input (newest
   bar older than the expected session) is a refusal with a non-zero exit, the analogue of
   the futures defer, so a re-run later in the evening is the retry.
5. **Schedule**: two daily routines on the box, weekdays, about 18:30 and 19:45 Eastern
   (after the 17:30 equities task and its retries; before the 20:55 futures task, whose
   repeating trigger syncs the same two replicas this wrapper syncs, and two mirror passes
   at once is the race the equities wrapper's header warns about). The second is the
   retry; on a good night it is the no-op in step 4.
6. **The backfill** is a `count=5000` pull per symbol from a Claude session, and it needs
   no transcription: a result that size exceeds the harness's tool-result limit and is
   persisted VERBATIM to a file before the model sees it, so the file is copied into the
   raw directory as-is and built with `--expect-session none`. Done from a Mac session on
   2026-09-17, eleven symbols, every file validated by the build's own parser and anchors
   before it was placed. `NCFD`'s 1953 bars are its whole published history; the 2006
   series hit the cap and the cap exceeds every board window.

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

`verify-scheduling.ps1` inspects Task Scheduler tasks through its `$TASKS` table; a
Desktop routine is not one and gets no row there. Three changes, read against the script
as it stands (verified on the box, 2026-09-17):

- **A freshness check of its own.** The existing "Store freshness" section takes the
  NEWEST date across every line of `marketdata-update --check` and ages that. A stalled
  series would hide behind a fresh equities date. The new check filters the `--check`
  lines whose symbol column starts with `series/tradingview/`, takes the OLDEST last-bar
  date among them, and fails past four days, the same threshold the section already
  uses. That is the check that matters; everything else here is bookkeeping.
- **`run-series.cmd` joins the wrapper list**, so a missing wrapper fails the run like a
  missing `run-equities.cmd` does.
- **A GUARD PROOFS line** saying the routine's existence, schedule and permission mode
  cannot be checked from the script and must be eyeballed in the Desktop app's Routines
  list, beside a hand-run of `run-series.cmd` against a raw file with one altered close
  (expect a refusal naming the bar).

The replica-parity section already skips `_raw` on both sides, so the raw JSON does not
count against parity. A night the series did not update is caught by the freshness check
the next morning and by cot-analyzer's stale note, never by the routine's own logs.

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
  without anyone logging in. Verified on the box: NDU and the Desktop app both launch
  automatically in the logged-on session, so a reboot does not stop the series. What
  does is someone closing the app, which nothing relaunches until the next reboot, so
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
- **`_raw\tradingview` stays outside both syncs**, verified on the box: `sync-store.cmd`'s
  bars pass carries `/XD _raw` and `push-to-server.cmd`'s bars pass carries
  `--exclude "_raw/"`, both written for databento's paid raw store and both matching by
  name at any depth, so a `_raw\tradingview` tree is excluded the day it appears. The
  box's bar store has no `_raw` directory today; the routine's first write creates it.
  Keep the directory name exactly `_raw` or both exclusions silently stop applying.
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
2. **Done 2026-09-17.** An interactive session on the box pulled `NCFD` with `count=10`
   and wrote it verbatim; a throwaway local routine then did the same on a schedule. Both
   files are identical to each other and to the Mac-side pull on every date and close
   (`c` for 2026-09-16 is 32.23). The routine prompted twice, for the bars call and the
   write, which fixes the allow rules in §2.1. The two probe files sit at
   `C:\Users\matt\code\ncfd_probe.json` and `ncfd_routine.json`, outside any repo;
   delete them once the build's parser fixture is committed from one of them.
3. `cotmetrics.indicators`: `fomo_zone` and the net-highs regime, cited to the SWG cutoffs,
   with tests on the boundary values.
4. marketdata: the `series` domain per the 2026-09-13 scoping doc (its steps 3 and 4, store
   layout tests included), `--build-tradingview` with the §2.2 guards each under test, and
   the registry entries with anchors. No network in any of it: the build reads files.
5. On the box: `run-series.cmd`, `series-routine.md`, the allow rules in the routine
   folder's `.claude\settings.json`, the two routines, the backfill session, the
   `verify-scheduling.ps1` changes in §2.3. Run the verifier. Next morning:
   `marketdata-update --check` and the manifest entries under `series/tradingview/`.
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

## 7. Where the build departed from this document

Recorded rather than rewritten above, so the reasoning stays legible.

- **Internal names are `NASDAQ_`, not `NDX_`.** The FOMO script's universe is the Nasdaq
  COMPOSITE (settled by its Pine source), and `NDX` names the 100. The registry says which.
- **The second routine runs at 19:45, not 21:30**, for the sync-race reason now stated in
  §2.1 step 5.
- **The backfill went through persisted tool results, not a CSV export**, §2.1 step 6. The
  CSV importer (`--tradingview-csv`, marketdata 0.3.1) exists and works; it is the fallback
  for a session without the persisted-result path. The routine instructions on the box
  still describe the CSV route and are due the same edit.
- **Two vendor conventions the build learned on the first full pull** (marketdata 0.3.2): a
  count of zero is printed as 0.01, and the equity put/call ratio carries two zero-close
  holes. Neither is a transcription matter; both would have refused a nightly file on the
  wrong day.
- **The wrapper is invoked `cmd //c`**, doubled slash, because the routine's Bash tool is
  Git Bash and rewrites a lone `/c`. Found on the first supervised run.
- **No universe toggle, and the S&P 500 FOMO series is not drawn.** The panel shipped with
  a Nasdaq / S&P 500 switch, mirroring the Pine script's dropdown, and lost it the next day:
  rulebook M-07 defines FOMO on Nasdaq stocks and its zones were read off that series,
  nothing in the corpus or the agi importer uses the S&P variant, and the two universes sit
  apart (45 against 36 on 2026-09-17), so drawing S5FD against Nasdaq-calibrated bands would
  be an untested extension wearing the guide's labels. `SPX_FOMO_5D` stays in the store.
- **The panel honours the board's date selector only when the reader has gone back in
  time.** The selector defaults to the newest COT Tuesday, which for a daily panel is up to
  a week stale; the newest report means "now".
