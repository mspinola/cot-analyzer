#!/bin/bash
# Run from this repo regardless of the caller's cwd. main.py and several config reads
# resolve relative paths, so launching from elsewhere died at startup before the Dash
# server bound its port.
cd "$(dirname "$0")" || exit 1
REPO="$(pwd)"

# Point the metrics layer's derived cache at this repo's data_cache so the app
# reuses the existing per-instrument parquet cache (cotmetrics defaults it to
# ~/.cache/cotmetrics otherwise).
export COTMETRICS_CACHE="${COTMETRICS_CACHE:-$REPO/data_cache}"

# cot-analyzer ships a generic SAMPLE config/params.yaml since going public. Real runs
# need the private universe + palettes, which live in the sibling cotmetrics-config repo.
# Point BOTH the metrics layer (COTMETRICS_PARAMS: CotIndexer instruments/lookbacks/roles)
# and the viz layer (COT_VIZ_CONFIG: viz_config palettes + Name->TV_Chart map) at that one
# file so they cannot drift. If the sibling is missing, cotmetrics falls back to the sample
# and warns. Override either by exporting it yourself before running.
_private_params="$REPO/../cotmetrics-config/params.yaml"
if [ -f "$_private_params" ]; then
    export COTMETRICS_PARAMS="${COTMETRICS_PARAMS:-$_private_params}"
    export COT_VIZ_CONFIG="${COT_VIZ_CONFIG:-$_private_params}"
fi

# Machine-specific config (COTDATA_STORE, credentials) comes from .env -- gitignored,
# and the same file systemd loads via EnvironmentFile= in server-side/cot-analyzer.service.
# Sourcing it here means the app is launchable from tooling (launchd, editors, preview
# harnesses) without depending on an interactive shell having exported anything.
if [ -f "$REPO/.env" ]; then
    set -a
    . "$REPO/.env"
    set +a
fi

# Fail loudly rather than defaulting to a guess: a wrong store path surfaces much later
# as confusing empty/stale data instead of an error here.
if [ -z "$COTDATA_STORE" ]; then
    echo "run-local.sh: COTDATA_STORE is not set." >&2
    echo "  Add it to $REPO/.env (gitignored), e.g." >&2
    echo "    COTDATA_STORE=/path/to/cotdata_store" >&2
    echo "  or export it before running." >&2
    exit 1
fi

# CIT PY research notes (dated .md/.txt the /citpy page links) are produced by a separate
# tool and only read here. They used to default to $COTDATA_STORE/citpy, which was wrong
# twice over: the store is a producer/consumer artifact that a sync mirrors, so a --delete
# pass would remove a directory no producer creates, and keeping a second copy there meant
# hand-refreshing it after every generator run. Set COTMETRICS_CITPY (see .env) to the
# generator's own output directory instead. Unset, cotmetrics falls back to its XDG data
# dir, which is what the deployed unit uses.
if [ -z "$COTMETRICS_CITPY" ] && [ -d "$COTDATA_STORE/citpy" ]; then
    echo "run-local.sh: $COTDATA_STORE/citpy still exists but is no longer read." >&2
    echo "  Point COTMETRICS_CITPY at the notes' real home in .env, then delete it:" >&2
    echo "    a store sync mirrors that path and will not preserve it." >&2
fi

.venv/bin/python src/main.py "$@"
