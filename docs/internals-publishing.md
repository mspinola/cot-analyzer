# Publishing internals.bluemagicai.com

The Market Internals page as a site of its own, like the other monitors: one static HTML
file rendered by `src/components/market_internals_static.py` and pushed to a public
GitHub Pages repo (`mspinola/internals-dashboard`) by dbmf-tracker's
`deploy/publish_pages.py --key internals`, the publisher the DBMF, AHLT, ORR and Surveys
pages use. [surveys-publishing.md](surveys-publishing.md) is the model, and the reasons
given there (why the VPS, why one machine) hold here unchanged.

**Status, 2026-11-11: built, not live.** The renderer, the build command, the publish
script and the cron line exist. The repo, the DNS record, the first publish and the cron
install are the go-live steps below, and none has been done.

## One page, two renderers, one set of numbers

| | draws | reads |
|---|---|---|
| the app's `/internals` | `src/pages/analytics/internals.py` (Dash) | `market_internals.snapshot()` |
| the static copy | `src/components/market_internals_static.py` (HTML) | `market_internals.build_snapshot()` |

Both take every number, label and cutoff from `components/market_internals.py` (which
takes the FOMO zones and the net-highs regime from `cotmetrics.indicators`), and every
title, number format, detail line and figure from `components/market_internals_view.py`.
Neither renderer computes anything. The app's page has no controls and its charts are
static plots, so the copy needed no JavaScript beyond drawing the embedded figures.

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
  app page's own rule, and the run names them on stderr (`awaiting ...`).
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
`/internals`, the app page's own path, so the page's views stay on one row when the app
page becomes a redirect. The app must be deployed with that allowlist entry BEFORE the
first publish, or the views in between are answered and dropped.

## Go-live, in order

1. Merge and deploy this change (`systemctl restart cot-analyzer` picks up the
   allowlist).
2. Create the public repo `mspinola/internals-dashboard` and clone it beside the
   workspace (`~/code/internals-dashboard` on the Mac).
3. Namecheap: `CNAME internals mspinola.github.io.`
4. First publish, by hand from the Mac, carrying the domain:

       scripts/publish_internals.sh --cname internals.bluemagicai.com

   Then in the repo's Settings > Pages: serve from `main`, and enforce HTTPS once the
   certificate is issued.
5. On the VPS:

       cd /root && git clone git@github.com:mspinola/internals-dashboard.git
       /root/trading_workspace/cot-analyzer/scripts/publish_internals.sh --dry-run
       crontab -l 2>/dev/null | cat - /root/trading_workspace/cot-analyzer/server-side/publish-internals.cron | crontab -

## After it is live (a second change, not this one)

Until then every link still points at the app's page, so this change is safe to deploy
before the subdomain exists. Once it resolves:

- "Market" in the monitors row points at the subdomain: `sentiment_static.SITES` here,
  and dbmf-tracker's three templates with its `tests/test_site_nav.py`.
- The app's Monitors menu entry moves from `_MONITOR_PAGES` to
  `_MONITOR_EXTERNAL_PAGES`.
- `/internals` becomes a 301 to the subdomain (the `/crowd` pattern: a Flask route plus
  an entry in `routing.EXTRA_PATHS`), and `src/pages/analytics/internals.py` goes.
