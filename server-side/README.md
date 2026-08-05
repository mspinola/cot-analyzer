# Server Setup

Building the production host from nothing. Written to be followed top to bottom on a
fresh Debian/Ubuntu box.

## Read this first: the server is a consumer, not a producer

On the default path, futures prices and contract specs come from
[Norgate](https://norgatedata.com/), which is **Windows-only** and talks to a locally
installed Norgate Data Updater rather than to an API. The Linux server therefore cannot
produce prices as configured, however it is provisioned.

(`cotdata` also carries a Databento provider, which *is* API-based and would run on
Linux. It is dormant, not the default, and enabling it is a deliberate choice rather
than part of this setup. See step 5.)

So the pipeline has two halves:

```
  Windows box (producer)                 Linux server (consumer)
  ──────────────────────                 ───────────────────────
  Norgate Data Updater                   reads the synced store
  cotdata writes COTDATA_STORE   ─────►  computes indices, serves Dash
  crowdmon writes the damage panel        renders it, cannot build it (py3.9)
                                         downloads CFTC COT itself (free)
```

CFTC Commitments of Traders data is free and downloads fine on the server. Prices do
not. If you set this up expecting the server to be self-sufficient, that is the thing
that will not work.

## What has to exist on the server

Four repositories, all as siblings in one parent directory:

| Repo | Role | Needed to serve? |
|---|---|---|
| `cot-analyzer` | the Dash app, this repo | yes |
| `cotmetrics` | the data/metrics layer, imported by the app | yes |
| `cotdata` | the price/COT store library, imported by cotmetrics | yes |
| `npf` | research: books, validation, backtests | no |

`cot-analyzer` imports `cotmetrics`, which imports `cotdata`, and both are installed
editable from their checkouts. Cloning only this repo will get you an import error at
startup, not a helpful message.

`npf` is optional here. Clone it if you want to run research on the box, but it does
**not** share the app's virtualenv: it targets Python 3.11 while the app runs 3.9, and
it keeps its own `.venv` with its own editable install of `cotmetrics`. One venv for all
four will not work.

## 1. System packages

```bash
apt update
apt install -y python3 python3-venv git rsync nginx certbot python3-certbot-nginx
```

Python 3.9 or newer. Both `cotmetrics` and `cotdata` declare `requires-python = ">=3.9"`,
and production currently runs 3.9.

## 2. Timezone

The COT release schedule and the update schedulers are wall-clock driven, so the host
must agree with New York.

```bash
timedatectl                                   # check current
timedatectl set-timezone America/New_York     # set if needed
```

## 3. Clone the repos

```bash
mkdir -p /root/trading_workspace
cd /root/trading_workspace
git clone git@github.com:mspinola/cot-analyzer.git
git clone git@github.com:mspinola/cotmetrics.git
git clone git@github.com:mspinola/cotdata.git
git clone git@github.com:mspinola/npf.git          # optional, research only
```

The systemd unit expects `/root/trading_workspace/cot-analyzer`. Change `WorkingDirectory`,
`EnvironmentFile` and `ExecStart` in `cot-analyzer.service` together if you put them
elsewhere.

## 4. Virtualenv

One venv for the three serving repos, owned by `cot-analyzer`, with the siblings
installed editable so a `git pull` in either takes effect without reinstalling. (`npf`,
if cloned, gets its own on Python 3.11 and is not part of this.)

```bash
cd /root/trading_workspace/cot-analyzer
python3 -m venv .venv
source .venv/bin/activate

# Pin setuptools BEFORE anything else. setuptools 81 removed pkg_resources, and
# dash, databento and yfinance all still import it. A fresh venv on current Debian
# installs 81+, so this is the default failure, not an edge case. It surfaces as an
# ImportError when the app starts, long after everything looked like it installed
# fine.
pip install 'setuptools<81'

pip install -r requirements.txt
pip install -e ../cotmetrics
pip install -e ../cotdata
```

Check it survived, since a later install can pull it forward again:

```bash
pip show setuptools | grep Version     # want < 81
pip install 'setuptools<81'            # re-pin if something bumped it
```

Verify the editable links resolve to the checkouts and not to copies in `site-packages`:

```bash
python -c "import cotmetrics, cotdata; print(cotmetrics.__file__); print(cotdata.__file__)"
# both paths must be under /root/trading_workspace/cotmetrics/src and /root/trading_workspace/cotdata/src
```

Then confirm the app's own imports work before moving on. This is the first point where
a bad `setuptools` shows itself:

```bash
python -c "import dash, yfinance; print('imports ok')"
```

## 5. Environment file

Create `/root/trading_workspace/cot-analyzer/.env`, readable only by the service user. systemd loads it
via `EnvironmentFile=`.

```bash
touch /root/trading_workspace/cot-analyzer/.env
chmod 600 /root/trading_workspace/cot-analyzer/.env
```

**Required:**

```bash
COTDATA_STORE=/root/cotdata_store     # the synced price store, see step 6
```

Nothing works without `COTDATA_STORE`. Every entry point resolves instruments through
it, so a missing or empty store fails at import rather than degrading.

**Optional, for the `/damage` page only:**

```bash
CROWDMON_STORE=/root/crowdmon_store   # crowdmon's damage panel, synced by the same script
```

Unset is fine and is the default state. It defaults to a sibling of the workspace, the same
place `cotdata_store` sits, so on the layout above nothing needs setting at all. When the
panel is absent the `/damage` page renders a "not available" card naming what produces it and
every other page is unaffected; the reader never raises, because `use_pages=True` imports
every page at startup and an exception there would take down the whole page registry.

**This server cannot build that panel**, for the same reason it cannot build prices, plus one
more: crowdmon requires Python 3.9's successor (`>=3.10`) and this box runs 3.9.

Any *other* machine with a readable store can build it, though, so the rule is not "crowdmon
needs Windows". The panel simply has to be built **upstream of whatever ships it**, and today
that is the Windows/Norgate producer, because the sync originates there. Unlike prices, the
panel is not vendor data: it is derived output that any machine with the store regenerates
identically, so if the sync origin moves, the publish moves with it.

On Windows use the portable driver, since `bin/publish_damage.sh` is bash and the launchd
agent beside it is macOS:

```
set COTDATA_STORE=...\cotdata_store
set CROWDMON_STORE=...\crowdmon_store
.venv\Scripts\python bin\publish_damage.py
```

**Publish before the sync runs.** Nothing enforces that ordering, and getting it backwards
ships last week's panel beside this week's prices, which the `/damage` page reports as a
staleness banner rather than an error.

**Required for the emailed Signal Matrix report:**

```bash
EMAIL_USER=your-dedicated-account@gmail.com
RECEIVER_EMAIL_USER=your-destination-account@gmail.com
EMAIL_PASSWORD=your-16-character-app-password
```

**Optional:**

```bash
COT_ADMIN_PASSWORD=...       # gates the Admin page; that page is unusable without it
PORT=5001                    # defaults to 5001
COT_SKIP_BOOT_FETCH=1        # skip the synchronous CFTC fetch at boot
COTMETRICS_LOG_DIR=...       # defaults to ~/.cache/cotmetrics/logs
COTMETRICS_DATA=...          # legacy raw_cot_data.parquet + real_test_data exports;
                             # defaults beside COTMETRICS_CACHE, rarely needs setting
```

**Set for you by `launch-cot-analyzer.sh`, override only if you mean to:**

```bash
COTMETRICS_CACHE     # -> /root/trading_workspace/cot-analyzer/data_cache
COTMETRICS_PARAMS    # -> /root/trading_workspace/cot-analyzer/config/params.yaml
```

`COTMETRICS_PARAMS` matters more than it looks. Without it, cotmetrics falls back to the
copy packaged inside the installed package, so the data layer and the viz layer read two
different `params.yaml` files that drift apart silently.

**Supported but off by default:**

```bash
DATABENTO_API_KEY=db-xxxxx   # only if you enable the databento provider
```

[Databento](https://databento.com/) is a fully supported provider in `cotdata`, currently
**dormant** rather than removed. Norgate replaced it on the live EOD price path, but it
is retained deliberately for two things Norgate cannot do: intraday data, and
cross-checking Norgate's settlement close. It ships behind the `[databento]` extra.

The server does not need the key unless you turn the provider on. It is not part of the
default price path.

## 6. Sync the data the server cannot generate

Three things are gitignored and must be copied from the machine that produced them.
Run these **from the producer**, not the server.

> **`scripts/push_data_cache_to_server.sh` is DEPRECATED and refuses to run.** It pushed
> from the **Mac**, which is a read-only replica rather than a producer, so it was a replica
> pushing to a replica. `cotdata/docs/SYNCING.md` documents the real topology: one Windows
> server produces everything and feeds two replicas, the Mac over SMB and this dash server
> over SSH. The script is kept rather than deleted so a reader who finds it here gets a
> message naming its replacement instead of a dangling reference.

Everything is pushed **from the Windows producer**, by Task Scheduler running scheduler
copies of two templates. See `cotdata/docs/WINDOWS_SCHEDULING.md` for how they are wired
and chained behind `errorlevel` guards.

| payload | pushed by |
|---|---|
| the cotdata store (~234M) | `cotdata/docs/examples/windows/push-to-server.cmd` |
| the crowdmon damage panel (~35M) | `crowdmon/docs/examples/windows/push-panel.cmd` |

**`data_cache/` and `data/cot_data.db` are not pushed by either, and that is correct.**
They are cotmetrics runtime state, and PR #12 moved them out of this repo into
`.local-state/cot-analyzer/`, so the deprecated script could not have shipped them anyway.
**The server rebuilds the cache itself** — confirmed by the maintainer on 2026-08-04, not
inferred from the push having been broken. `CotIndexer` writes per-instrument parquet under
`COTMETRICS_CACHE` on first use and busts it on the upstream `cotdata.schema_version()` plus
`METRICS_CACHE_VERSION`, so a store push is the only input it needs.

The first sync after a release is therefore slower than steady state, because the cache is
cold. That is a latency cost on one request, not a missing payload.

The store push by hand, for reference, is:

```bash
rsync -avz --no-o --no-g --progress --exclude='.DS_Store' \
      /path/to/cotdata_store/ USER@HOST:/root/cotdata_store/
```

`data/` is a third gitignored directory, and most of it does **not** need to travel:

- `xls_data` (441M) and `cot_data` (94M) are CFTC archives the ETL downloads from
  `cftc.gov` and extracts on its own.
- `csv_data` (221M) is export output the app writes, not an input it reads.

None of it is pushed today. The SQLite database moved to `.local-state/cot-analyzer/`
in PR #12 and the server maintains its own; syncing the whole of `data/` would ship about
800M to save a download the server does anyway.

## 7. Install the service

```bash
cp /root/trading_workspace/cot-analyzer/server-side/cot-analyzer.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cot-analyzer
systemctl status cot-analyzer
```

The app binds `0.0.0.0:$PORT` (5001 by default).

**First start is slow.** `CotIndexer` validates the parquet cache at import, and any
schema change invalidates it and recomputes every instrument. Expect several minutes
before the port answers. That is normal on a first boot or after an upgrade that adds
columns; it is not a hang.

```bash
journalctl -u cot-analyzer -f      # watch it
```

## 8. Nginx and TLS

```bash
certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Point the site's `proxy_pass` at `http://127.0.0.1:5001`.

**The apex must resolve to exactly one address — this server.** Let's Encrypt picks one of
the published A records when it validates, so any extra one makes renewal a coin flip
rather than a failure you would notice. See the DNS entry under Troubleshooting; it has
bitten this domain once already.

```bash
dig +short A yourdomain.com        # want exactly one line, this server's IP
```

### HSTS (optional, and sticky)

Once the certificate is confirmed good **in a clean browser**, add HSTS to the `443`
server block:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

```bash
nginx -t && systemctl reload nginx
curl -sI https://yourdomain.com/ | grep -i strict-transport
```

It tells browsers to go straight to https without the plaintext request that gets
redirected, and it removes the "click Advanced to proceed" escape hatch on a bad
certificate.

That second part is the real reason to want it, and also the reason to be careful.
Clicking through an expired certificate makes Chrome remember the origin as untrusted,
and that state survives reloads: after this domain's certificate lapsed and was fixed,
the site still showed "Not secure" in the browser that had clicked through, while
working perfectly in a fresh profile. HSTS prevents that by never offering the
clickthrough.

The cost is that it is **sticky for `max-age`**, a year as written. A browser that has
seen the header will refuse plain http to the domain, so a future lapse becomes a hard
block rather than a warning. Only enable it once renewal is dependable: single apex A
record, `certbot renew --dry-run` passing, `certbot.timer` active. Shorten `max-age` to
something like `300` while testing if you want an easy way back.

## Upgrading

Code moves by git; data moves by rsync.

```bash
ssh USER@HOST '
  cd /root/trading_workspace/cotdata      && git pull &&
  cd /root/trading_workspace/cotmetrics   && git pull &&
  cd /root/trading_workspace/cot-analyzer && git pull
'
ssh USER@HOST 'systemctl restart cot-analyzer && systemctl status cot-analyzer'
```

> A release that changes derived-cache contents no longer ships a cache from here: the
> server rebuilds it. The `data_cache` push that used to sit in this block went with
> `push_data_cache_to_server.sh`, per §6.

Editable installs mean a `git pull` in `cotmetrics` or `cotdata` needs no reinstall, but
it **does** need the restart, because the running process already imported them.

Pull all three or none. `cot-analyzer` and `cotmetrics` are released together, and a
version skew shows up as an `AttributeError` at request time rather than at startup.

`restart.sh` in this directory is the restart on its own.

## Troubleshooting

**The browser says "Not secure" but the certificate checks out.** Verify from outside
the browser first (see the openssl commands below). If the certificate is valid and
`http` redirects to `https`, this is cached browser state, not a server problem: clicking
through an expired certificate makes Chrome remember the origin as untrusted, and a plain
reload will not clear it. Confirm with a private window, which shares no cached state. To
clear it in the normal profile, delete the domain under
`chrome://net-internals/#hsts` -> *Delete domain security policies*, then quit the browser
completely rather than just closing the tab. Enabling HSTS in step 8 prevents the
clickthrough that causes this.

**Certificate expired, or renewals fail with a connection timeout to an IP that is not
this server.** The domain publishes more than one A record for the apex. Let's Encrypt
picks one when it validates, so renewal succeeds or fails at random and only becomes
visible when the certificate finally lapses. `certbot.timer` looks perfectly healthy
throughout, because it is firing on schedule and failing every time.

```bash
dig +short A yourdomain.com     # more than one line is the bug
```

On Namecheap the usual cause is not a stray A record but a **URL Redirect Record** on
`@`. Namecheap implements those by pointing the host at its own redirect servers
(`162.255.119.x`), which publishes a second apex address alongside yours. It is easy to
miss because the DNS panel lists it as a redirect rather than as an address, and the
redirect is often circular and doing nothing (`@` -> `https://yourdomain.com/`).

Delete the redirect record, leave the A records, then:

```bash
dig +short A yourdomain.com                    # exactly one line now
certbot renew --dry-run                        # must pass BEFORE a real attempt
certbot renew --nginx && systemctl reload nginx
```

Use the dry run first. Let's Encrypt rate-limits failed validations, and a domain in
this state has usually burned a lot of attempts already. Verify from off the box, since
the server can reach itself regardless of what DNS publishes:

```bash
# the dates: pipe through x509 so it prints whether or not the cert is valid
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com 2>/dev/null \
  | openssl x509 -noout -subject -dates

# the trust check: silence here is the pass condition
echo | openssl s_client -connect yourdomain.com:443 -servername yourdomain.com 2>&1 \
  | grep -i 'verify error' || echo "no verify errors"
```

Check `www` as well as the apex. They are separate names on the certificate and a
redirect record usually only affects `@`.

A symptom that points here rather than at nginx: the ACME challenge URL in certbot's
error contains a path segment from the app (for example
`/positioning/.well-known/acme-challenge/...`). That is the redirect service rewriting
the request, not an nginx misconfiguration.

**`ModuleNotFoundError: No module named 'pkg_resources'`.** `setuptools` is 81 or newer,
which removed it, while `dash`, `databento` and `yfinance` still import it. Re-pin in the
venv:

```bash
pip install 'setuptools<81' && pip show setuptools | grep Version
```

setuptools warns about this itself before it breaks: *"The pkg_resources package is
slated for removal... Refrain from using this package or pin to Setuptools<81."*

**Port never answers, no error.** Almost always the parquet rebuild in step 7. Check
`journalctl` for `Cache missing or stale. Running full indexing`.

**Store errors, or every instrument empty.** `COTDATA_STORE` is unset, points somewhere
wrong, or the store was never synced. It is read at import.

**Charts render but prices are missing or stale.** Expected if the producer has not run.
The server cannot fetch prices; see the top of this file.

**The data layer and the UI disagree about instruments or lookbacks.** `COTMETRICS_PARAMS`
is not reaching the process, so the two layers are reading different `params.yaml` files.

**`data/` reappears empty somewhere unexpected.** The ETL paths (`data/xls_data`,
`data/cot_data`, `data/csv_data`) are relative and resolve against the working
directory, and they are created on demand rather than failing. `launch-cot-analyzer.sh`
does `cd ..` before starting for exactly this reason, so start the app through the
service or that script rather than invoking `src/main.py` directly.

**Max Pain empty across the board.** Options snapshots live in
`$COTMETRICS_CACHE/options`. Either they were never synced, or the snapshot for the
current COT date carries no usable underlying price, which the log names explicitly.
