#!/bin/bash
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
