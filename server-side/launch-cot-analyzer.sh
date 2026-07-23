#!/bin/bash
cd ..
source .venv/bin/activate

# Use Python to run the main application which also spawns the background auto-update schedulers
export PYTHONPATH=src
# Reuse this repo's data_cache for the cotmetrics derived cache (defaults to
# ~/.cache/cotmetrics otherwise). Requires `pip install -e ../cotmetrics` in .venv.
export COTMETRICS_CACHE="${COTMETRICS_CACHE:-$PWD/data_cache}"
# cot-analyzer now ships a generic SAMPLE config/params.yaml. Real runs need the
# private universe + palettes, which live in the sibling cotmetrics-config repo.
# Point BOTH the metrics layer (COTMETRICS_PARAMS: CotIndexer instruments/lookbacks/
# roles) and the viz layer (COT_VIZ_CONFIG: viz_config palettes + Name->TV_Chart map)
# at that one file so they cannot drift. If the sibling is missing, cotmetrics falls
# back to the sample and warns. Override either by exporting it yourself.
_private_params="$PWD/../cotmetrics-config/params.yaml"
if [ -f "$_private_params" ]; then
    export COTMETRICS_PARAMS="${COTMETRICS_PARAMS:-$_private_params}"
    export COT_VIZ_CONFIG="${COT_VIZ_CONFIG:-$_private_params}"
fi
exec python3 src/main.py
