#!/bin/bash
#
# ============================================================================
# DEPRECATED 2026-08-04. Do not use. It is kept, not deleted, because
# server-side/README.md leans on it in four places and a reader following an
# obsolete-but-present script fails more loudly than one following a dangling
# reference. It now refuses to run.
#
# WHY. This pushes from the MAC, and the Mac is a read-only replica rather than a
# producer. cotdata/docs/SYNCING.md documents the real topology: one Windows
# server produces everything and feeds two replicas, the Mac over SMB
# (robocopy /MIR, docs/examples/windows/sync-store.cmd) and this Linux dash
# server over SSH (rsync, docs/examples/windows/push-to-server.cmd). A Mac push
# is a replica pushing to a replica, and whichever side syncs second wins
# silently.
#
# It had also been unable to run since PR #12 routed runtime state out of the
# repo: the preflight still demanded ./data/cot_data.db, which moved to
# .local-state/cot-analyzer/, so it exited 1. The stale ./data_cache was the
# quieter half, a Jul 28 copy that would have been pushed over the server's
# without comment had the preflight passed. Both are symptoms of a script nobody
# had run in a while, not bugs to fix.
#
# WHAT REPLACES IT, per payload:
#   cotdata_store     cotdata/docs/examples/windows/push-to-server.cmd
#   data_cache/, db   rebuilt on the server by cotmetrics, confirmed 2026-08-04.
#                     CotIndexer writes its own per-instrument parquet under
#                     COTMETRICS_CACHE and busts it on the upstream schema
#                     version, so a store push is the only input it needs.
#
# The crowdmon damage panel briefly rode here as an optional fourth payload
# (#14). That was dead code: it was wired into a script that does not run. The
# payload is gone from here and lives in crowdmon's own Windows template.
# It is no longer a payload at all: the /damage page was removed on 2026-08-08
# and nothing on the server reads that panel now.
# ============================================================================
#
# Original header follows.
#
# Push the data the server cannot generate for itself.
#
# Exactly three payloads:
#
#   cotdata_store     Futures prices and contract specs. Norgate is Windows-only, so
#                     the server can never produce these. This lives OUTSIDE the repo,
#                     which is why the earlier version of this script never shipped it
#                     and the server failed at import after an otherwise clean sync.
#   data_cache/       Derived per-instrument parquet, plus the options snapshots.
#   data/cot_data.db  The SQLite database the app reads.
#
# Deliberately NOT shipped: the rest of data/, about 780M of CFTC archives that the ETL
# downloads from cftc.gov itself (xls_data, cot_data) and CSV exports that the app
# writes rather than reads (csv_data). The earlier version sent all of it.
#
# Dry run by default. Nothing moves until you pass --push.
#
# Usage:
#   ./scripts/push_data_cache_to_server.sh              # show what would move
#   ./scripts/push_data_cache_to_server.sh --push       # actually transfer
#
# Overrides:
#   HOST=user@example.com     ssh target (empty means a local copy, used by the tests)
#   REMOTE_ROOT=/path         workspace root on the server
#   COTDATA_STORE=/path       source store; defaults to the app's own env var
#
set -euo pipefail

# Refuse rather than warn. A deprecated sync that still runs is one that will be run.
cat >&2 <<'DEPRECATED'
push_data_cache_to_server.sh is DEPRECATED and does nothing.

The Mac is a read-only replica, not a producer. Everything the server needs is
pushed from the Windows box:

  cotdata store   cotdata/docs/examples/windows/push-to-server.cmd

See cotdata/docs/SYNCING.md for the topology and cotdata/docs/WINDOWS_SCHEDULING.md
for how those are scheduled. Set CROWDMON_ALLOW_LEGACY_PUSH=1 to run this anyway,
which you almost certainly do not want: it would push a replica over a replica.
DEPRECATED
if [ "${CROWDMON_ALLOW_LEGACY_PUSH:-0}" != "1" ]; then
    exit 2
fi

HOST="${HOST:?set HOST to the deploy target, e.g. HOST=user@your-server}"
REMOTE_ROOT="${REMOTE_ROOT:-/root/trading_workspace}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# The store is addressed by the same variable the app uses, so the two cannot disagree
# about where it lives. Falls back to the sibling-of-the-workspace convention.
STORE_SRC="${COTDATA_STORE:-$(cd "$PROJECT_ROOT/../.." && pwd)/cotdata_store}"
# On the server the store is a sibling of the workspace, not inside it.
STORE_DEST="$(dirname "$REMOTE_ROOT")/cotdata_store"
APP_DEST="$REMOTE_ROOT/cot-analyzer"

PUSH=0
for arg in "$@"; do
    case "$arg" in
        --push) PUSH=1 ;;
        -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

# ── preflight ────────────────────────────────────────────────────────────────
# Check every source before moving anything, so a missing store is a message rather
# than a partial sync that leaves the server unable to boot.
missing=0
for src in "$STORE_SRC" ./data_cache ./data/cot_data.db; do
    if [ ! -e "$src" ]; then
        echo "MISSING: $src" >&2
        missing=1
    fi
done
if [ "$missing" -ne 0 ]; then
    echo >&2
    echo "Refusing to sync a partial set. The server needs all three to start." >&2
    exit 1
fi

# .DS_Store rides along from macOS otherwise; it is noise on a Linux box.
RSYNC_OPTS=(-avz --no-o --no-g --human-readable --exclude='.DS_Store')
if [ "$PUSH" -eq 1 ]; then
    RSYNC_OPTS+=(--progress)
else
    RSYNC_OPTS+=(--dry-run --itemize-changes)
fi

# An empty HOST means a plain local path, which is how the tests exercise this without
# touching production.
remote() { if [ -n "$HOST" ]; then echo "$HOST:$1"; else echo "$1"; fi; }

echo "============================================="
if [ "$PUSH" -eq 1 ]; then
    echo "  Pushing data to ${HOST:-<local>}"
else
    echo "  DRY RUN — nothing will move. Use --push."
fi
echo "============================================="
echo "  store       $STORE_SRC"
echo "              -> $(remote "$STORE_DEST")"
echo "  data_cache  ./data_cache"
echo "              -> $(remote "$APP_DEST/data_cache")"
echo "  database    ./data/cot_data.db"
echo "              -> $(remote "$APP_DEST/data/")"
echo

if [ "$PUSH" -eq 1 ] && [ -n "$HOST" ]; then
    # rsync will not create missing parent directories on its own.
    ssh "$HOST" "mkdir -p '$STORE_DEST' '$APP_DEST/data_cache' '$APP_DEST/data'"
fi

# Trailing slash on the sources: copy the CONTENTS into the destination, so a rename
# upstream cannot produce a nested store_dir/store_dir on the server.
echo "--- store ---"
rsync "${RSYNC_OPTS[@]}" "$STORE_SRC/" "$(remote "$STORE_DEST/")"

echo "--- data_cache ---"
rsync "${RSYNC_OPTS[@]}" ./data_cache/ "$(remote "$APP_DEST/data_cache/")"

echo "--- database ---"
rsync "${RSYNC_OPTS[@]}" ./data/cot_data.db "$(remote "$APP_DEST/data/")"

echo
if [ "$PUSH" -eq 1 ]; then
    echo "[done] Sync complete."
    echo "       The app already imported its modules, so restart to pick this up:"
    echo "       ssh ${HOST:-<host>} 'systemctl restart cot-analyzer'"
else
    echo "[done] Dry run only. Re-run with --push to transfer."
fi
