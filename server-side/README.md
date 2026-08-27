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
git clone git@github.com:mspinola/marketdata.git   # bars; ADR-0007 split them from cotdata
git clone git@github.com:mspinola/npf.git          # optional, research only
```

The systemd unit expects `/root/trading_workspace/cot-analyzer`. Change `WorkingDirectory`,
`EnvironmentFile` and `ExecStart` in `cot-analyzer.service` together if you put them
elsewhere.

## 4. Virtualenv

One venv for the four serving repos, owned by `cot-analyzer`, with the siblings
installed editable so a `git pull` in any of them takes effect without reinstalling.
(`npf`, if cloned, gets its own on Python 3.11 and is not part of this.)

`marketdata` is the fourth as of ADR-0007, which moved daily bars out of `cotdata`.
It is **not on PyPI**, so unlike the others it can only be resolved from this clone —
`requirements.txt` carries `-e ../marketdata`, and a missing checkout fails the install
with `Distribution not found at: file:///root/trading_workspace/marketdata` rather than
anything that names the real cause.

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
pip install -e ../marketdata
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
COTDATA_STORE=/root/cotdata_store        # synced CFTC positioning store, see step 6
MARKETDATA_STORE=/root/marketdata_store  # synced daily-bar store, see step 6
```

Nothing works without `COTDATA_STORE`. Every entry point resolves instruments through
it, so a missing or empty store fails at import rather than degrading.

**`MARKETDATA_STORE` is required too, and it is new.** ADR-0007 makes `cotdata` CFTC
positioning only and moves every bar to `marketdata`, so the price reads behind the
indexer, the signal rejection scores and the options max-pain snapshot now resolve
against a second store.

**It does not fail the same way the first one does, and this paragraph used to say it
did.** Measured 2026-08-08: `MARKETDATA_STORE` *unset* raises by name, but a store that
is set and simply holds no `bars/futures/` serves an **empty frame with no error at
all**. That is the documented read semantics of `marketdata.get_bars` rather than a
bug, and it is exactly the shape a server lands in after syncing a store whose futures
half never arrived. Symptom: positioning renders, every price chart is blank, nothing in
the log says why.

`main.py` now checks this at boot, before the indexer is built, and refuses to start
when no configured instrument has bars (`COT_ANALYZER_ALLOW_MISSING_PRICES=1` downgrades
that to a warning for a deliberately COT-only run). A partial or stale store warns and
carries on. So the loud failure this paragraph promised is now real, but it comes from
the boot guard, not from the read.

Both are **synced**, not produced here. This box cannot produce bars at all:
`norgatedata` drives a locally installed Norgate Data Updater and NDU is Windows-only.

**Required for the emailed Signal Matrix report:**

```bash
EMAIL_USER=your-dedicated-account@gmail.com
RECEIVER_EMAIL_USER=your-destination-account@gmail.com
EMAIL_PASSWORD=your-16-character-app-password
COT_WEEKLY_EMAIL=1          # send automatically when the COT week advances
```

Those three credentials are enough for the Admin page's **Send Email** button, which
sends on demand. `COT_WEEKLY_EMAIL` is what makes it automatic, and it is **off unless
set** because this same code runs on development machines that must not mail anyone.

The trigger lives in the store poller (`src/weekly_email_trigger.py`), for the same
reason the index refresh does: this box never downloads COT, so `status.json` advancing
is the only local event that means a new week exists. It sends once per COT week and
records which week in `~/.local/share/cotmetrics/weekly_email.json`
(`COT_WEEKLY_EMAIL_STATE` overrides the path). That ledger is why a restart, a second
worker, or a browser tab winning the refresh race cannot produce a second copy.

**The first tick after enabling it seeds the ledger and sends nothing.** That is
deliberate, so switching the flag on does not itself look like a release. The next COT
week is the first one mailed. Use the Admin button if you want one immediately.

**Optional:**

```bash
COT_ADMIN_PASSWORD=...       # gates the Admin page; that page is unusable without it
PORT=5001                    # defaults to 5001
COT_SKIP_BOOT_FETCH=1        # skip the synchronous CFTC fetch at boot
COTMETRICS_LOG_DIR=...       # defaults to ~/.cache/cotmetrics/logs
COTMETRICS_DATA=...          # legacy raw_cot_data.parquet + real_test_data exports;
                             # defaults beside COTMETRICS_CACHE, rarely needs setting
GOATCOUNTER_URL=...          # origin of a GoatCounter instance (no trailing path);
                             # unset, no analytics script is served. See step 9
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

Everything is pushed **from the Windows producer**, by Task Scheduler running a scheduler
copy of one template. See `cotdata/docs/WINDOWS_SCHEDULING.md` for how it is wired and
chained behind `errorlevel` guards.

| payload | pushed by |
|---|---|
| the cotdata store (~234M) | `cotdata/docs/examples/windows/push-to-server.cmd` |

**`data_cache/` and `data/cot_data.db` are not pushed by it, and that is correct.**
They are cotmetrics runtime state, and PR #12 moved them out of this repo into
`.local-state/cot-analyzer/`, so the deprecated script could not have shipped them anyway.
**The server rebuilds the cache itself** — confirmed by the maintainer on 2026-08-04, not
inferred from the push having been broken. `CotIndexer` writes per-instrument parquet under
`COTMETRICS_CACHE` on first use and busts it on BOTH upstream store versions
(`cotdata.schema_version()` and `marketdata.schema_version()`) plus
`METRICS_CACHE_VERSION`, so a store push is the only input it needs. Both are watched
because the case that guard was written for — reconstructed volume being promoted — was
a *price* schema bump, and prices now live in the second store.

The first sync after a release is therefore slower than steady state, because the cache is
cold. That is a latency cost on one request, not a missing payload.

The store push by hand, for reference, is:

```bash
rsync -avz --no-o --no-g --progress --exclude='.DS_Store' \
      /path/to/cotdata_store/ USER@HOST:/root/cotdata_store/

rsync -avz --no-o --no-g --progress --exclude='.DS_Store' \
      /path/to/marketdata_store/ USER@HOST:/root/marketdata_store/
```

Two stores, two pushes, and they must stay **separate roots**. Each package keeps its
own `manifest.json` at its root and does a read-modify-write on it, so merging the two
into one directory would have the producers dropping each other's entries.

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

## 9. GoatCounter analytics (optional)

Client-side analytics beside the app's own visit log, not replacing it: the built-in
tracker (visitor_logs, the /admin charts) works with no browser JS and keeps working
if this step is skipped. [GoatCounter](https://www.goatcounter.com/) adds the polished
dashboard, and it is the tool chosen because it matches this box's ops style: one
static Go binary, SQLite storage, a systemd unit, no Docker and no Postgres.

**The release assets are gzipped, and the download must be verified.** Check
[the releases page](https://github.com/arp242/goatcounter/releases) for the current
version and pick your architecture (`uname -m`: `x86_64` is amd64, `aarch64` is arm64).

```bash
# 1. Binary. Note the .gz: there is no un-gzipped asset, and `wget -O` CREATES the
#    target file even when the server answers 404, so a wrong url leaves an empty
#    file behind that chmod +x will happily mark executable. That failure surfaces
#    much later as `Exec format error` (systemd status 203/EXEC) from the service,
#    which reads like a broken unit rather than a bad download.
wget -O /tmp/gc.gz \
  https://github.com/arp242/goatcounter/releases/download/v2.7.0/goatcounter-v2.7.0-linux-amd64.gz
gunzip -f /tmp/gc.gz
install -m755 /tmp/gc /usr/local/bin/goatcounter

# 2. Prove it runs before anything depends on it.
goatcounter version

# 3. Data dir + site. -createdb is required the first time: GoatCounter refuses to
#    create a database that does not exist unless asked, so without it every command
#    here fails and the service later starts with nothing to serve. Prompts for a
#    login password. -vhost must equal the nginx server_name below.
mkdir -p /var/lib/goatcounter
goatcounter db create site -vhost stats.yourdomain.com -user.email you@example.com \
  -createdb -db sqlite+/var/lib/goatcounter/goatcounter.sqlite3
```

Give `stats.yourdomain.com` a DNS A record pointing at this server before going
further, and exactly one: certbot validates against whatever the name resolves to, so a
second record makes issuance a coin flip, the same trap the apex has under step 8.

Unit, `/etc/systemd/system/goatcounter.service` (same shape as `cot-analyzer.service`):

```ini
[Unit]
Description=GoatCounter analytics
After=network.target

[Service]
ExecStart=/usr/local/bin/goatcounter serve -listen 127.0.0.1:8081 -tls http \
  -db sqlite+/var/lib/goatcounter/goatcounter.sqlite3
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`-tls http` means "serve no TLS", which is right here because nginx terminates it.
`RestartSec` is worth the line: without it a binary that fails instantly burns
systemd's five restarts inside one second and lands in `Start request repeated too
quickly`, which hides the real error behind a rate-limit message.

```bash
systemctl daemon-reload
systemctl enable --now goatcounter
```

```bash
systemctl status goatcounter --no-pager
```

Check that status now rather than at the end. A dead upstream here is what an nginx
`502 Bad Gateway` means three steps later, and by then it looks like a proxy problem.
If the unit has already failed a few times, `systemctl reset-failed goatcounter`
before starting it again.

GoatCounter listens on loopback only, so nginx publishes it. Unlike step 8, where the
site already existed and only needed a certificate, this vhost is new: write
`/etc/nginx/sites-available/goatcounter`,

```nginx
server {
    listen 80;
    server_name stats.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**`X-Forwarded-For` is load-bearing here, not boilerplate.** Every hit reaches
GoatCounter from 127.0.0.1 (nginx), and its visitor counting reads that header for the
real address, exactly as `visitors.client_ip` does for the app's own log. Omit it and
every visitor collapses into one.

Then enable it, and let certbot rewrite the block for TLS (it adds the 443 listener and
the http redirect itself):

```bash
ln -s /etc/nginx/sites-available/goatcounter /etc/nginx/sites-enabled/goatcounter
```

```bash
nginx -t && systemctl reload nginx
```

```bash
certbot --nginx -d stats.yourdomain.com
```

Browsing to `https://stats.yourdomain.com` should now offer the GoatCounter login, for
the email given to `db create site` above. The `-vhost` passed there must match this
`server_name`, or the site is served but no site matches the request.

Finally point the app at it in `.env`:

```bash
GOATCOUNTER_URL=https://stats.yourdomain.com
```

Restart `cot-analyzer` (`systemctl restart cot-analyzer`, or the Admin page's Restart
button) and every served page carries the tracker plus a pushState hook
(`goatcounter_index_string` in `src/app_cot.py`): GoatCounter's own script counts only
document loads, and Dash navigates by pushState, so without the hook it would record
entry pages and nothing else, the same blind spot the server-side pageview rows fix.
With the variable unset the served page is byte-identical to stock, which is why dev
machines need no opt-out.

## Upgrading

Code moves by git; data moves by rsync.

```bash
ssh USER@HOST '
  cd /root/trading_workspace/cotdata      && git pull &&
  cd /root/trading_workspace/marketdata   && git pull &&
  cd /root/trading_workspace/cotmetrics   && git pull &&
  cd /root/trading_workspace/cot-analyzer && git pull
'
ssh USER@HOST 'systemctl restart cot-analyzer && systemctl status cot-analyzer'
```

> A release that changes derived-cache contents no longer ships a cache from here: the
> server rebuilds it. The `data_cache` push that used to sit in this block went with
> `push_data_cache_to_server.sh`, per §6.

Editable installs mean a `git pull` in any sibling needs no reinstall, but it **does**
need the restart, because the running process already imported them.

Pull all four or none. `cot-analyzer` and `cotmetrics` are released together, and a
version skew shows up as an `AttributeError` at request time rather than at startup.
`marketdata` joined the set with ADR-0007 and skews the same way: `cotmetrics` calls
`marketdata.get_bars` and `marketdata.schema_version`, so a stale checkout there is a
price failure inside a healthy-looking COT deployment.

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

**`MARKETDATA_STORE is not set`, or price reads fail while COT works.** The second store
is missing. Positioning and prices come from different packages since ADR-0007, so one
can be healthy while the other is absent — and this is the shape that failure takes.
Set it and sync `marketdata_store` the same way as the first.

**The unit refuses to start, logging "MARKETDATA_STORE holds no bars for any of the N
configured instruments".** The boot guard. The store exists but its futures half is
empty, which is what a sync that carried only `bars/equities/` looks like. Sync
`bars/futures/` from the producer, or run marketdata's
`scripts/import_from_cotdata.py` if that box still has the bars under
`$COTDATA_STORE/prices/`. For a deliberately COT-only deployment, set
`COT_ANALYZER_ALLOW_MISSING_PRICES=1` and it warns instead.

**Boot logs "price store gap: SYM tier: stale/short/absent" but the unit starts.** A
partial gap, by design: positioning is unaffected and most charts still draw, so the
guard says so and carries on rather than taking the site down. The named symbols are the
ones whose charts will be blank or short.

**Charts render but prices are missing or stale.** Expected if the producer has not run.
The server cannot fetch prices; see the top of this file. Since the boot guard landed
this should announce itself in the log at startup rather than being noticed on a chart.

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
