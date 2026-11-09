# Publishing surveys.bluemagicai.com

The app's `/sentiment` page is local-only (`src/local_pages.py`). Its public copy is one
static HTML file at https://surveys.bluemagicai.com, rendered by
`src/components/sentiment_static.py` and pushed to the public repo
[mspinola/surveys-dashboard](https://github.com/mspinola/surveys-dashboard) by
dbmf-tracker's `deploy/publish_pages.py --key surveys`, the same publisher as the DBMF,
AHLT and ORR monitors. Publishing NAAIM's and AAII's history was cleared against their
terms on 2026-11-09.

## Where it runs, and why there

On the VPS, from root's crontab (`server-side/publish-surveys.cron`), daily at 19:15 New
York time: `scripts/publish_surveys.sh` renders the page and calls the publisher, which
pushes only when the page changed.

The VPS already holds everything the page needs: this repo with its venv, `cotmetrics`
and `cotmetrics-config` (the real `params.yaml`), and both stores, which the Windows
producer pushes after each of its runs. The Windows box was considered first and dropped:
it has the stores but not the code that draws this page (the DBMF, AHLT and ORR pages
are drawn by dbmf-tracker itself), so it would have needed three more clones, a venv, and
a `git pull` after every change. On the VPS, code changes reach the page with the app's
ordinary deploy.

**One machine is scheduled.** Each publish force-pushes a one-commit branch. The Mac's
copy of the script stays for a hand publish or a test (`--dry-run`), and must not be
scheduled. The first publish was made from the Mac on 2026-11-09.

## What the job reads

From the server's `.env` it takes only `COTDATA_STORE`, `MARKETDATA_STORE`,
`COTMETRICS_PARAMS` and `COT_VIZ_CONFIG`, by parsing rather than sourcing (the file also
holds mail and admin credentials). It refuses to run without a real `params.yaml`,
because cotmetrics would otherwise read a 6-symbol sample in silence. It keeps its own
cotmetrics cache under `/root/trading_workspace/.local-state/cot-analyzer`, apart from
the app's `data_cache`, so the two processes never write one cache at once.

## One-time setup on the VPS

    cd /root/trading_workspace
    git -C cot-analyzer pull --ff-only          # the renderer (#169) and this script
    git -C marketdata pull --ff-only            # registry entries for AAII and NAAIM (#41-#43)
    systemctl restart cot-analyzer               # the app picks up the beacon allowlist
    git clone git@github.com:mspinola/dbmf-tracker.git     # the publisher, read only
    cd /root && git clone git@github.com:mspinola/surveys-dashboard.git
    /root/trading_workspace/cot-analyzer/scripts/publish_surveys.sh --dry-run
    crontab -l 2>/dev/null | cat - /root/trading_workspace/cot-analyzer/server-side/publish-surveys.cron | crontab -

Pushes use root's existing GitHub key (the one its other clones use). Then run
`server-side/verify-deploy.sh` for the app restart, as after any deploy.

## Keeping it current, and when it fails

- Code: pulled with the app's deploy. A plotly upgrade needs nothing, because the page
  loads the plotly.js release the installed plotly bundles.
- Log: `/var/log/publish_surveys.log`. Each run starts with a `rendering` line.
- `export-sentiment: not written`: a store read came back empty. The published page is
  left as it was. Check the store's newest dates.
- `no params.yaml` / `is not set`: the `.env` or `cotmetrics-config` is missing.
- A push failure is git's own message: root's GitHub key.
