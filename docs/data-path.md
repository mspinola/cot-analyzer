# How data reaches cot-analyzer

cot-analyzer never talks to a data vendor. It never even calls the price API directly.
Every number on the dashboard arrives through two layers of indirection, and the store
is the boundary where vendor identity stops mattering.

Verified 2026-07-26 by reading the source, not the docs. **Re-verified 2026-08-08, and the
read path changed**: ADR-0007 step 4 landed in `cotmetrics` (commit `1290ec0`), so bars now
arrive through `marketdata.get_bars` and `cotdata.get_prices` is no longer called from
`cotmetrics/src` at all. See "The read path today" below before trusting the older diagram.

## Current path (superseded 2026-08-08, kept for the vendor argument)

```mermaid
flowchart TD
    subgraph producers["PRODUCERS (the only network access)"]
        direction LR
        cftc["CFTC<br/>free, any OS"]
        norgate["Norgate<br/>WINDOWS ONLY"]
        dbn["databento<br/>paid, any OS"]
        yf["yfinance<br/>free, any OS"]
    end

    cftc -->|"--cot-legacy / --cot-disagg / --cot-tff"| store
    norgate -->|"--prices"| store
    dbn -->|"--ingest-databento then --build-databento"| store
    yf -->|"--prices-yahoo"| store

    subgraph store["cotdata store ($COTDATA_STORE)"]
        direction LR
        p["prices/<br/>SYM_backadj.parquet"]
        c["cot_legacy/ cot_disagg/ cot_tff/"]
        mf["manifest.json<br/>source, last_date, n_rows"]
    end

    store --> api

    subgraph api["cotdata read API (vendor-blind, local only)"]
        gp["get_prices(symbol, adjustment, volume)"]
        gc["get_cot(...)"]
    end

    api --> cm

    subgraph cm["cotmetrics"]
        ci["CotIndexer.py:655"]
        sg["signals.py:1028"]
        od["options_data.py:366"]
    end

    cm --> ca["cot-analyzer (Dash)<br/>run-local.sh :5001<br/>NO vendor references in code"]

    style norgate fill:#b45309,color:#fff
    style store fill:#1d4ed8,color:#fff
    style api fill:#15803d,color:#fff
    style ca fill:#6d28d9,color:#fff
```

## Which vendor serves what, today

Read from the live store manifest: **47 symbols norgate, 2 yahoo**. The mix is per-symbol,
not per-deployment, so "which vendor" never had one answer even locally.

`COTDATA_PRICE_SOURCE` picks the deployment default. A symbol uses its explicit override
first, then the default when that vendor can serve it, then a Yahoo fallback where a
ticker exists. One provider owns a symbol end to end and a series is never blended
(ADR-0006).

## Where the abstraction is real

Complete, at the code level. Every mention of Norgate or databento inside `cot-analyzer/src`
and `cotmetrics/src` is a comment or a docstring. Not one is functional. `get_prices` takes
no vendor argument. Swapping the producer changes no consumer line.

## Where it leaks

The store hides the vendor. It does not hide vendor differences, and all three of these
are silent.

```mermaid
flowchart LR
    q["get_prices('ZS', 'backadj')"] --> ng["Norgate store<br/>12,260 bars"]
    q --> db["databento store<br/>floor 2010-06-06"]
    ng --> r1["deep lookbacks valid"]
    db --> r2["same call, ~1/3 the history<br/>NO error raised"]

    style db fill:#b91c1c,color:#fff
    style r2 fill:#b91c1c,color:#fff
```

**History depth.** databento's GLBX.MDP3 floor is hardcoded at 2010-06-06
(`cotdata/src/cotdata/providers/databento.py:201`). A lookback window longer than that
runs on truncated data and nothing complains.

**Reconstructed volume degrades quietly.** Only the Norgate path writes
`Volume_Reconstructed` and `Volume_Source`. `prices.py:145` handles the absence on
purpose, labelling everything `raw`. So `get_prices(volume="reconstructed")` returns true
reconstructed volume on one store and front-month volume on the other, same call, no error.
`Volume_Source` exists so a consumer can tell, but cotmetrics does not check it.

**Coverage gaps shift the vendor.** Markets off CME Globex (ICE softs, lumber, MSCI) are
not on databento at all and fall back to Yahoo, so a databento deployment is really a
databento-plus-Yahoo deployment.

## The read path today

Measured 2026-08-08 against the working tree and both live stores.

**The consumers have moved. The bytes have not.** ADR-0007 is shipping as separate steps and
these two are out of step with each other:

| | state |
|---|---|
| step 4, repoint consumers | **done**. `cotmetrics` reads `marketdata.get_bars(symbol, "backadj")` at `CotIndexer.py:752`, `signals.py:1030`, `options_data.py:366`. `grep get_prices cotmetrics/src` returns nothing |
| step 2, move the producer code and the bars | **on ice**. `providers/databento.py` has no owner |

So the read now points at `$MARKETDATA_STORE/bars/futures/`, while 99 price parquets still
sit in `$COTDATA_STORE/prices/` where the producer keeps writing them.

**This fails silently, which is the part to remember.** A futures read against a store with
no `bars/futures/` does not raise. It returns an empty frame:

```python
marketdata.get_bars("GC", "backadj")   # -> 0 rows, no error
```

The app still boots, binds :5001, and renders every COT page, because positioning comes from
the other store and is unaffected. Only price overlays and the price-dependent signals go
blank. Both failure modes below therefore look like a UI regression rather than a data one:

- `MARKETDATA_STORE` unset: raises, but late, on the first bar read rather than at startup.
  `run-local.sh` checks it upfront for this reason.
- `MARKETDATA_STORE` set and populated with `bars/equities/` only: no error anywhere.

Until the futures bars are imported into the marketdata store, a local checkout renders
positioning without prices. Confirm before trusting a chart:

```bash
python -c "import marketdata; print(len(marketdata.get_bars('GC','backadj')))"
```

## Target path after ADR-0007

`cotdata` keeps CFTC positioning only. All bars move to `marketdata`, which already holds
the `equities` domain and would gain `futures`.

```mermaid
flowchart TD
    cftc["CFTC"] --> cs["cotdata store<br/>cot/ + manifest.json"]
    norgate["Norgate (Windows)"] --> ms
    dbn["databento (Linux server only)"] --> ms
    yf["yfinance"] --> ms

    subgraph ms["marketdata store"]
        f["bars/futures/&lt;source&gt;/SYM_backadj.parquet"]
        e["bars/equities/&lt;source&gt;/SYM.parquet"]
        m2["manifest.json (separate writer)"]
    end

    cs --> cm["cotmetrics"]
    ms --> cm
    cm --> ca["cot-analyzer"]
    ms -.->|"provenance(symbol)"| ca

    style ms fill:#1d4ed8,color:#fff
    style ca fill:#6d28d9,color:#fff
```

Both stores may share one synced parent folder. They must not share a `manifest.json`,
because `_touch_manifest` is a read-modify-write and concurrent producers lose entries.

The dotted edge is the fix for the leaks above: `marketdata.provenance(symbol)` returns
source, date span, row count and `covers(start)` from the manifest without opening a
parquet, so the dashboard can show what backs a chart and a startup check can refuse a
lookback the store cannot support.
