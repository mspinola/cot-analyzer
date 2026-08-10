#!/bin/bash
# Run from this repo regardless of the caller's cwd. main.py and several config reads
# resolve relative paths, so launching from elsewhere died at startup before the Dash
# server bound its port.
cd "$(dirname "$0")" || exit 1
REPO="$(pwd)"

# Everything below hangs off the sibling layout, so resolve the MAIN checkout rather than
# assuming we are it. A worktree lives at <checkout>/.claude/worktrees/<name>, where
# $REPO/.. is the worktrees dir and every sibling lookup misses at once: the shared
# local-state dir, the CIT PY notes, and cotmetrics-config. That last one is the reason
# this is worth resolving properly rather than documenting -- a miss there does not fail,
# it falls back to the SAMPLE 6-symbol universe and the app comes up looking fine.
# git-common-dir names the main checkout's .git from inside a worktree and our own when
# we are the main checkout, so one expression covers both; it prints a relative path in
# the ordinary case and an absolute one from a worktree. No git at all (a tarball deploy)
# falls back to treating this directory as the checkout.
_git_common="$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null)"
case "$_git_common" in
    "") _CHECKOUT="$REPO" ;;
    /*) _CHECKOUT="$(cd "$_git_common/.." && pwd)" ;;
    *)  _CHECKOUT="$(cd "$REPO/$_git_common/.." && pwd)" ;;
esac

# Local runtime state: the derived parquet cache, rotating logs, and the visitor-log
# SQLite DB. Keep all three in one untracked dir off the workspace root, shared across
# every checkout/worktree (trading_workspace is not a git repo, so nothing tracks it).
# Unset, the library defaults scatter them across per-user XDG dirs (~/.cache for the
# cache and logs, ~/.local/share for the DB); the DB default previously landed inside
# the installed cotmetrics package tree. Override so a local run keeps them together and
# out of ~/.cache. Export your own values first to opt out of any of these.
_WORKSPACE="$(cd "$_CHECKOUT/.." && pwd)"
_LOCAL_STATE="$_WORKSPACE/.local-state/cot-analyzer"
mkdir -p "$_LOCAL_STATE/data_cache" "$_LOCAL_STATE/logs"
export COTMETRICS_CACHE="${COTMETRICS_CACHE:-$_LOCAL_STATE/data_cache}"
export COTMETRICS_LOG_DIR="${COTMETRICS_LOG_DIR:-$_LOCAL_STATE/logs}"
export COTMETRICS_DB="${COTMETRICS_DB:-$_LOCAL_STATE/cot_data.db}"

# cot-analyzer ships a generic SAMPLE config/params.yaml since going public. Real runs
# need the private universe + palettes, which live in the sibling cotmetrics-config repo.
# Point BOTH the metrics layer (COTMETRICS_PARAMS: CotIndexer instruments/lookbacks/roles)
# and the viz layer (COT_VIZ_CONFIG: viz_config palettes + Name->TV_Chart map) at that one
# file so they cannot drift. If the sibling is missing, cotmetrics falls back to the sample
# and warns. Override either by exporting it yourself before running.
_private_params="$_WORKSPACE/cotmetrics-config/params.yaml"
if [ -f "$_private_params" ]; then
    export COTMETRICS_PARAMS="${COTMETRICS_PARAMS:-$_private_params}"
    export COT_VIZ_CONFIG="${COT_VIZ_CONFIG:-$_private_params}"
fi

# Machine-specific config (COTDATA_STORE, credentials) comes from .env -- gitignored,
# and the same file systemd loads via EnvironmentFile= in server-side/cot-analyzer.service.
# Sourcing it here means the app is launchable from tooling (launchd, editors, preview
# harnesses) without depending on an interactive shell having exported anything.
# It describes the MACHINE, not the branch, so fall back to the main checkout's copy:
# gitignored files do not come along into a worktree, and without this a worktree run
# dies on the COTDATA_STORE check below having never had a chance to read one.
_ENVFILE="$REPO/.env"
[ -f "$_ENVFILE" ] || _ENVFILE="$_CHECKOUT/.env"
if [ -f "$_ENVFILE" ]; then
    set -a
    . "$_ENVFILE"
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

# Same check for the second store. ADR-0007 moved bars out of cotdata, so since
# cotmetrics repointed at marketdata.get_bars a price read needs MARKETDATA_STORE and
# raises without it. That failure is quiet in the worst way: the import succeeds, the
# app binds its port, every COT page renders, and only the first chart wanting bars
# dies. Check it here so a run that cannot serve prices says so before it starts.
# It is a SEPARATE root, never COTDATA_STORE: both producers write manifest.json with
# a read-modify-write, so pointing them at one directory loses entries.
if [ -z "$MARKETDATA_STORE" ]; then
    echo "run-local.sh: MARKETDATA_STORE is not set." >&2
    echo "  Add it to $REPO/.env (gitignored), e.g." >&2
    echo "    MARKETDATA_STORE=/path/to/marketdata_store" >&2
    echo "  or export it before running. It must NOT be COTDATA_STORE." >&2
    exit 1
elif [ "$MARKETDATA_STORE" = "$COTDATA_STORE" ]; then
    echo "run-local.sh: MARKETDATA_STORE and COTDATA_STORE are the same path." >&2
    echo "  They are two stores. Sharing one manifest.json loses entries, because" >&2
    echo "  each producer rewrites it read-modify-write. Point them at separate dirs." >&2
    exit 1
fi

# CIT PY research notes (dated .md/.txt the /citpy page links) are produced by a separate
# tool and only read here. They live in the sibling citpy repo's own untracked output dir,
# so the page reads whatever the generator last wrote rather than a copy someone has to
# refresh. Default it from the workspace, same sibling convention as cotmetrics-config
# above and for the same reason: a path pinned by hand in .env goes stale the moment the
# checkout moves, and citpy moving into trading_workspace broke exactly that way. The
# failure is the silent kind, since an unreadable directory and a generator that has not
# run yet both render /citpy as an empty table. This runs AFTER .env is sourced, so an
# explicit COTMETRICS_CITPY there still wins.
_citpy_notes="$_WORKSPACE/citpy/data/citrini_outputs"
if [ -z "$COTMETRICS_CITPY" ] && [ -d "$_citpy_notes" ]; then
    export COTMETRICS_CITPY="$_citpy_notes"
fi

# Say so rather than serving an empty page. Unset is fine (cotmetrics falls back to its
# XDG data dir, which is what the deployed unit uses); set-but-absent is a mistake.
if [ -n "$COTMETRICS_CITPY" ] && [ ! -d "$COTMETRICS_CITPY" ]; then
    echo "run-local.sh: COTMETRICS_CITPY=$COTMETRICS_CITPY does not exist." >&2
    echo "  /citpy will render an empty table. Fix or drop it in $REPO/.env; dropped," >&2
    echo "  it defaults to $_citpy_notes when that sibling is present." >&2
fi

# Tripwire, not a migration step: the notes used to be copied to $COTDATA_STORE/citpy,
# which was wrong twice over. The store is a producer/consumer artifact that a sync
# mirrors, so a --delete pass removes a directory no producer creates, and the copy had
# to be hand-refreshed after every generator run. Nothing reads it now, so if it is back
# something recreated it.
if [ -d "$COTDATA_STORE/citpy" ]; then
    echo "run-local.sh: $COTDATA_STORE/citpy exists but is no longer read." >&2
    echo "  Delete it: a store sync mirrors that path and will not preserve it." >&2
fi

# Same reasoning as .env: a worktree has no .venv of its own. Borrowing the main
# checkout's interpreter runs THIS tree's src/main.py, since cwd is $REPO. Note the
# editable siblings (cotdata, cotmetrics) still resolve to their own main checkouts, so a
# worktree run exercises this repo's changes and not a sibling's.
_PY="$REPO/.venv/bin/python"
[ -x "$_PY" ] || _PY="$_CHECKOUT/.venv/bin/python"
if [ ! -x "$_PY" ]; then
    echo "run-local.sh: no virtualenv found at $REPO/.venv or $_CHECKOUT/.venv." >&2
    exit 1
fi

exec "$_PY" src/main.py "$@"
