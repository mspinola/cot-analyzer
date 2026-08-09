# COT Analyzer

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Dash/Plotly web app for exploring [CFTC](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
Commitments of Traders positioning. It's the UI layer on top of the
[`cotmetrics`](https://github.com/mspinola/cotmetrics) metrics library, which reads
positioning from the [`cotdata`](https://github.com/mspinola/cotdata) store and daily bars
from the [`marketdata`](https://github.com/mspinola/marketdata) store; it computes no
metrics of its own. Given the CFTC legacy report, it will:

* generate CSV files with per-symbol data
* generate RealTest data as an Event List for each symbol
* calculate the COT index from configurable lookbacks for the 3 COT categories (Commercials, Large Speculators, Small Speculators)
* render positioning plots via Dash/Plotly for browser viewing
* periodically download updated COT reports (released Fridays at 3:30 US/Eastern)

![Example Graphs](./docs/cot-indexing-graphs.png)
![Example Positioning Table](./docs/cot-positioning-table.png)

> **This is a source application, not a PyPI package.** Clone it and run it. It expects
> three siblings checked out alongside it (`../cotdata`, `../marketdata`, `../cotmetrics`),
> which `requirements.txt` installs editable, and **two** populated stores,
> `COTDATA_STORE` and `MARKETDATA_STORE`. See Setup below.

## COT Data

Description of [COT Legacy Report data fields](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalViewable/deanexplanatory.html)

## Setup (uv)

Check out the sibling repos alongside this one first, so the editable installs in
`requirements.txt` resolve:

```bash
git clone https://github.com/mspinola/cotdata
git clone https://github.com/mspinola/marketdata
git clone https://github.com/mspinola/cotmetrics
git clone https://github.com/mspinola/cot-analyzer
cd cot-analyzer
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt   # editable siblings: -e ../cotdata, -e ../marketdata, -e ../cotmetrics
```

`requirements.txt` pulls in three local sibling packages, all editable:

* **cotmetrics** (`-e ../cotmetrics[options]`) is the data and metrics layer. It
  owns the indexer, the COT index and signals, and options data. This repo is the Dash
  application on top of it and computes no metrics of its own.
* **cotdata** (`-e ../cotdata`) is CFTC positioning, read through `cotdata.get_cot`.
* **marketdata** (`-e ../marketdata`) is daily bars, read through `marketdata.get_bars`.
  ADR-0007 moved prices out of cotdata, so this is a separate package **and** a separate
  store. The distribution name on PyPI is `crucible-marketdata` (plain `marketdata` there
  is an unrelated abandoned project); the import is still `marketdata`.

Skipping the `marketdata` clone does not fail at install time. It fails at import, because
`cotmetrics/__init__.py` re-exports `signals`, which imports `marketdata` at module level:

```
ModuleNotFoundError: No module named 'marketdata'
```

Point `COTDATA_STORE` and `MARKETDATA_STORE` at the two stores. Put both in `.env` at the
repo root (gitignored) so the launcher and the systemd unit pick them up:

```bash
printf 'COTDATA_STORE=~/code/cotdata_store\nMARKETDATA_STORE=~/code/marketdata_store\n' >> .env
```

They must be **different** directories. Each store's producer rewrites its own
`manifest.json` read-modify-write, so one shared manifest silently loses entries. They may
sit under a common synced parent.

## Run

```bash
./run-local.sh
# generated data lives in ./data ; view in a browser at http://127.0.0.1:5001
```

Use the launcher rather than `python src/main.py` directly. It changes to the repo root
(several config reads resolve relative paths), points `COTMETRICS_CACHE` at this repo's
`data_cache/`, points `COTMETRICS_PARAMS` and `COT_VIZ_CONFIG` at the sibling
`../cotmetrics-config/params.yaml` when that private config repo is checked out alongside
(otherwise the metrics and viz layers fall back to the packaged sample and warn), sources
`.env`, and fails loudly if `COTDATA_STORE` or `MARKETDATA_STORE` is unset (or if they are
set to the same path) rather than surfacing later as confusing empty data. You can still
run `python src/main.py` directly if you export those variables yourself.

## Configuration

Yaml config file lives in config/params.yaml

`lookbacks` defines the looback periods in which indexes are calculated

`years` defines the years in which historical CFTC COT is downloaded

`AssetClasses` defines classes of symbols for analysis

* `Name` is a string reference of the instrument
* `Symbol` is the instruments symbol ID - generally TradingView based as a default
* `Code` is the CFTC assigned ID code for each instrument. Symbol to code mapping lives in `cotmetrics.symbol_code_map` (in the cotmetrics sibling)
* `TV_Chart` TV doesn't chart futures in its `widgets` platform so this is a similar symbol for widget charting.
* `CustomLookbackWeeks` allows defining one custom lookback period per instrument

## Server Side Configuration

login

```bash
sudo apt install git pip
pip install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone git@github.com:mspinola/cotdata.git
git clone git@github.com:mspinola/marketdata.git
git clone git@github.com:mspinola/cotmetrics.git
git clone git@github.com:mspinola/cot-analyzer.git

cd cot-analyzer
uv venv
uv pip install -r requirements.txt
cp cot-analyzer.service /etc/systemd/system
systemctl enable cot-analyzer
```

### Syncing Local Cache to Server (Recommended)

To avoid subjecting your production server to massive 15-year synchronous backfills or computationally heavy historical calculations, you should **never** check the `data_cache/` directory into Git (doing so will rapidly bloat your repository size).

Prices come from Norgate, which is Windows-only, so the server cannot produce them at
all: do the heavy data work on the producer machine and sync the binaries over SSH.

```bash
# Run this from the producer's cot-analyzer root directory:
rsync -avz --no-o --no-g --progress ./data_cache/ user@your-server-ip:/path/to/server/cot-analyzer/data_cache/
```

The server also needs both stores synced, `COTDATA_STORE` and `MARKETDATA_STORE`. Most of
`./data` does **not** need to travel, since the CFTC archives in it are downloaded and the
CSV exports are generated.

**See [server-side/README.md](server-side/README.md)** for the full setup: which repos
the server needs, the complete environment variable list, exactly what to sync, and the
upgrade procedure. That file is the source of truth for deployment.

## License

MIT — see [LICENSE](LICENSE).



