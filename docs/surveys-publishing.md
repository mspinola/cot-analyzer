# Publishing surveys.bluemagicai.com

The app's `/sentiment` page is local-only (`src/local_pages.py`). Its public copy is one
static HTML file at https://surveys.bluemagicai.com, rendered by
`src/components/sentiment_static.py` and pushed to the public repo
[mspinola/surveys-dashboard](https://github.com/mspinola/surveys-dashboard) by
dbmf-tracker's `deploy/publish_pages.py --key surveys`, the same publisher as the DBMF,
AHLT and ORR monitors. Publishing NAAIM's and AAII's history was cleared against their
terms on 2026-11-09.

## Where it runs

On the Windows box (NUCBOX_M8), from dbmf-tracker's `deploy\publish_all.cmd`, which calls
`scripts\publish_surveys.cmd`. That puts it on the DBMF Tracker tasks' schedule (weekdays
08:30 and 18:00, as SYSTEM). The 18:00 run follows the 17:30 `marketdata equities` task,
which writes SPY and builds NAAIM and its provisional weeks, so a weekday's data is up the
same evening. Friday's COT lands at 15:30, before it. An unchanged page pushes nothing.

The box is the right machine because it writes every store the page reads. The Mac
only holds replicas, and its NAAIM provisional series exists only after a sync delivers it.

**One machine publishes.** Each publish force-pushes a one-commit branch. The Mac's
`scripts/publish_surveys.sh` stays for a hand publish or a test, and must not be scheduled.
The first publish was made from the Mac on 2026-11-09, before the box was set up.

## One-time setup on the box

In a terminal on the box (not over the share; the venv must be built on Windows):

1. Clone what the renderer imports, beside the siblings already there (`cotdata`,
   `marketdata` and the dbmf-tracker bundle are already present):

       cd C:\Users\matt\code
       git clone https://github.com/mspinola/cot-analyzer.git
       git clone https://github.com/mspinola/cotmetrics.git
       git clone https://github.com/mspinola/cotmetrics-config.git

   `cotmetrics-config` is private and holds the real `params.yaml`. Without it the
   wrapper refuses to run, because cotmetrics would silently fall back to a 6-symbol
   sample.

2. Build cot-analyzer's venv. `requirements.txt` installs `cotdata`, `marketdata` and
   `cotmetrics` editable from `..\`, which is why step 1 puts the clones side by side:

       cd C:\Users\matt\code\cot-analyzer
       py -3.11 -m venv .venv
       .venv\Scripts\python -m pip install -U pip "setuptools<81"
       .venv\Scripts\pip install -r requirements.txt

3. Clone the pages repo where the wrapper expects it, with a push credential that works
   under SYSTEM, exactly as the `ahlt-dashboard` clone has (dbmf-tracker
   `deploy\WINDOWS.md`, section 8):

       cd C:\Users\matt\code
       git clone https://github.com/mspinola/surveys-dashboard.git

4. Update the dbmf-tracker bundle so its `deploy\publish_all.cmd` carries the surveys
   step.

5. Test by hand, as the scheduled run would:

       C:\Users\matt\code\cot-analyzer\scripts\publish_surveys.cmd --dry-run
       C:\Users\matt\code\cot-analyzer\scripts\publish_surveys.cmd

   The first prints what it would push. The second either pushes or prints
   "unchanged, nothing pushed". Then run `deploy\publish_all.cmd` once and check
   `data\logs\task.out.log` for the surveys lines.

## Keeping it current

cot-analyzer on the box is a plain clone that the publish reads from, so it changes only
when you pull. After a change to `src/components/sentiment*.py` or the export script
merges, run `git -C C:\Users\matt\code\cot-analyzer pull` (and the same for
`cotmetrics` when it moves). A plotly upgrade needs nothing: the page loads the plotly.js
release the installed plotly bundles.

## When it fails

- `export failed`: a store read came back empty. Check the store's newest dates, for
  example `marketdata-update --check`. The published page is left as it was.
- `no venv` / `no clone` / `no ...params.yaml`: setup step 1, 2 or 3 is missing.
- A push failure is git's own message: the clone's credential.
