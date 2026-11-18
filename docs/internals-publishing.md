# Publishing internals.bluemagicai.com

The Market Internals page as a site of its own, like the other monitors: one static HTML
file rendered by `src/components/market_internals_static.py` and pushed to a public
GitHub Pages repo (`mspinola/internals-dashboard`) by dbmf-tracker's
`deploy/publish_pages.py --key internals`, the publisher the DBMF, AHLT, ORR and Surveys
pages use. [surveys-publishing.md](surveys-publishing.md) is the model, and the reasons
given there (why the VPS, why one machine) hold here unchanged.

**Status: live since 2026-11-11.** The first publish went up from the Mac that day, and
the app's own `/internals` page was removed in favour of a 301 to the subdomain.

## One renderer, no computation

`src/components/market_internals_static.py` lays the page out. Every number, label and
cutoff comes from `components/market_internals.py` (which takes the FOMO zones and the
net-highs regime from `cotmetrics.indicators`, and the credit appetite gauge and its
divergence days from the same module), and every title, text, tile and chart series from
`components/market_internals_view.py`.

## How it looks, and what draws the charts (since 2026-11-15)

- **The surveys page's stylesheet.** The page opens with `sentiment_static.base_css()`:
  the same tokens, header, readings tiles and cards. It follows that page's order too,
  a strip of tiles (each read's number, its word, one line of context), then cards that
  open on one sentence with the rest behind "How to read this". A change to the shared
  rules reaches both pages.
- **TradingView Lightweight Charts**, pinned (`LIGHTWEIGHT_CHARTS_VERSION`) and loaded
  from unpkg, drawing plain series embedded as JSON. Scroll and zoom are off; the
  crosshair shows the value and date under the cursor. The licence's attribution notice
  and link are in the footer, which is why the per-chart logo is off. To move to a
  newer release, change the constant, build locally and look at the page: nothing else
  pins it. The table's sparklines are inline SVG.
- **Credit appetite** (JNK against TLT, npf's `credit_xray.pine`) is a seventh card and
  card, drawn and described but not counted among the headwinds: a stress reading was
  not followed by a worse month when tested. The arithmetic was checked against the
  TradingView pane on 2026-11-15 (cotmetrics #58 has the comparison).

## What it counts (since 2026-11-18)

Five HEADWINDS, on the Caruso Insights member dashboard's definitions ("Market
Conditions", compared against its page for 2026-11-17): Nasdaq plus NYSE net new highs
as a 5-day average below zero, QQQ and SPY up/down volume each below 1, JNK's 20-day EMA
falling, and XLP/QQQ above its 50-day average. Each card says what would flip it, how
many sessions it has stood, and whether it is better or worse than five sessions ago.
FOMO, the advancing share and credit appetite are on the page and outside the count.

Before that the page counted six "reads" on definitions restated from agi, three of
which differed from the dashboard (JNK as price under a simple average, net highs as
the Nasdaq alone on a three-day rule, and FOMO counted, washed-out as a positive).
On the day of the comparison the two pages' numbers agreed where the data did: QQQ
0.64 and 23 sessions, SPY 0.57 and 13, JNK "turns up on a close above 92.41 (now
91.93)" and 4 sessions, XLP/QQQ +15.6% against +15.5% and 25 sessions. Net new highs
could not be compared on the same day (the store was a session behind).

Under the five cards, "When the headwinds lined up" draws each headwind's state on
every session since 2008 (where JNK starts) under QQQ, and the sessions all five were
on. It is inline SVG, about 130 KB of the page. It counts occurrences and stretches and
makes no claim about what followed; none has been tested. Each row's name is a
switch: the bottom row and the shading count only the headwind rows that are on. FOMO's
extremes are a sixth row, off as the page loads and never in the count.

Outside the count the page also carries (since 2026-11-18): the VIX against VIX3M
(inverted or normal, with the VIX's percentile since 1990), and two sections. **Sentiment**
is a block per survey (NAAIM, AAII bulls minus bears, AAII stocks allocation): the
current reading over three bars, its percentile on its full history, the last three
years and the last year, which are the surveys page's own Percentiles numbers drawn
here in HTML. **Positioning** is commercials in the four equity index futures (ES, YM,
NQ, RTY) as the crowd board draws them, the commercial index on 3M, 6M, 12M and full
history with the six-week change and the 52-week path
(`tape_context.window_index_frame`, the board's rule), then each market's net position
as a percent of open interest, weekly, three years. Positioning is read against its
recent range, so no long-history percentile appears there. Positioning needs the COT store and the indexer, which the rest of the page does
not; when either part cannot be served it is left off and named in the log
(`no surveys, left out`), and the publish goes ahead.

## Build it locally

    PYTHONPATH=src .venv/bin/python scripts/export_internals_page.py /tmp/internals.html

with run-local.sh's environment (`MARKETDATA_STORE`, `COTDATA_STORE`,
`COTMETRICS_PARAMS`, `COT_VIZ_CONFIG`), or let the publish script resolve it and stop
short of pushing:

    scripts/publish_internals.sh --dry-run

On the Mac this reads the local mirror `~/code/marketdata_store`. Do not point it at the
Windows share.

## What refuses, and what only warns

- No read at all (the store could not be read): `export-internals: not written`, exit 1,
  and the published page stays as it was.
- Some reads missing: the page goes up with those cards saying "Awaiting data", the
  page's rule for a series not delivered yet, and the run names them on stderr (`awaiting ...`).
- A read trailing the newest by more than three days is drawn and named, on the page and
  on stderr (`trailing: ...`).

## Schedule

`server-side/publish-internals.cron`: 20:15 New York time, daily, in root's crontab on
the VPS. The ETF bars land after the Windows box's 17:30 equities task and the breadth
series after its two routines (about 18:30 and 19:45); the surveys job's 19:15 would
publish between the two. An unchanged page pushes nothing. Log:
`/var/log/publish_internals.log`.

## View counting

The publisher adds the view beacon (`p=internals`) and the GoatCounter tag (path
`/internals`). `routing.EXTERNAL_PAGES` allowlists the key and records it as
`/internals`, the old app page's own path, so the page's views stay on one row across
the move. (The first publish went up before the allowlist was deployed, so the views in
between were answered and dropped.)

## How it went live (2026-11-11), for the next monitor

1. The allowlist entry merged and deployed first (cot-analyzer #191).
2. Public repo `mspinola/internals-dashboard`, cloned beside the workspace.
3. Namecheap: `CNAME internals mspinola.github.io.`
4. First publish by hand from the Mac, carrying the domain:
   `scripts/publish_internals.sh --cname internals.bluemagicai.com`. Then Pages enabled
   on `main` and HTTPS enforced once the certificate was issued (minutes).
5. On the VPS:

       cd /root && git clone git@github.com:mspinola/internals-dashboard.git
       /root/trading_workspace/cot-analyzer/scripts/publish_internals.sh --dry-run
       crontab -l 2>/dev/null | cat - /root/trading_workspace/cot-analyzer/server-side/publish-internals.cron | crontab -

6. Then the links: "Market" in the monitors row (`sentiment_static.SITES` here,
   dbmf-tracker's three templates and its `tests/test_site_nav.py`), the app's Monitors
   menu entry (`_MONITOR_EXTERNAL_PAGES`), and `/internals` as a 301
   (`app_cot.internals_redirect`, admitted by `routing.EXTRA_PATHS`).
