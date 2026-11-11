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
net-highs regime from `cotmetrics.indicators`), and every title, number format, detail
line and figure from `components/market_internals_view.py`. The page has no controls
and its charts are static plots, so its only JavaScript draws the embedded figures.

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
