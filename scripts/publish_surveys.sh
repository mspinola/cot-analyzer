#!/usr/bin/env bash
# Rebuild the static sentiment page and publish it to surveys.bluemagicai.com, by hand.
# The SCHEDULED publish runs on the Windows box (scripts\publish_surveys.cmd, called from
# dbmf-tracker's publish_all.cmd); do not also schedule this one, since each publish
# force-pushes a single-commit branch. docs/surveys-publishing.md has the whole picture.
#
# Two steps, each owned elsewhere:
#   1. scripts/export_sentiment_page.py renders the page from the local stores
#      (components/sentiment_static.py), and writes nothing when a read is empty.
#   2. dbmf-tracker's deploy/publish_pages.py --key surveys pushes it to the public
#      surveys-dashboard repo the way DBMF, AHLT and ORR go up: noindex + robots.txt,
#      the view beacon (p=surveys, allowlisted in src/routing.py) and GoatCounter
#      (/surveys), one force-pushed commit, and NOTHING pushed when the page is
#      unchanged, so running this often costs nothing.
#
# The environment is run-local.sh's, resolved the same way (worktree-safe, .env from the
# main checkout, cotmetrics-config beside it), because a scheduled job reads no profile.
#
#   scripts/publish_surveys.sh              # rebuild and publish if changed
#   scripts/publish_surveys.sh --dry-run    # rebuild, say what would be pushed
#
# Extra arguments go to publish_pages.py. SURVEYS_PAGES_DIR overrides the clone
# (default ~/code/surveys-dashboard); DBMF_TRACKER overrides the publisher checkout.
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
_git_common="$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null || true)"
case "$_git_common" in
    "") _CHECKOUT="$REPO" ;;
    /*) _CHECKOUT="$(cd "$_git_common/.." && pwd)" ;;
    *)  _CHECKOUT="$(cd "$REPO/$_git_common/.." && pwd)" ;;
esac
_WORKSPACE="$(cd "$_CHECKOUT/.." && pwd)"
_LOCAL_STATE="$_WORKSPACE/.local-state/cot-analyzer"
mkdir -p "$_LOCAL_STATE/data_cache" "$_LOCAL_STATE/logs"
export COTMETRICS_CACHE="${COTMETRICS_CACHE:-$_LOCAL_STATE/data_cache}"
export COTMETRICS_LOG_DIR="${COTMETRICS_LOG_DIR:-$_LOCAL_STATE/logs}"
export COTMETRICS_DB="${COTMETRICS_DB:-$_LOCAL_STATE/cot_data.db}"
_params="$_WORKSPACE/cotmetrics-config/params.yaml"
if [ ! -f "$_params" ] && [ -z "${COTMETRICS_PARAMS:-}" ]; then
    # Without it cotmetrics falls back to a 6-symbol sample, silently.
    echo "publish_surveys.sh: no $_params and COTMETRICS_PARAMS unset." >&2
    exit 1
fi
export COTMETRICS_PARAMS="${COTMETRICS_PARAMS:-$_params}"
export COT_VIZ_CONFIG="${COT_VIZ_CONFIG:-$COTMETRICS_PARAMS}"

_ENVFILE="$REPO/.env"
[ -f "$_ENVFILE" ] || _ENVFILE="$_CHECKOUT/.env"
if [ -f "$_ENVFILE" ]; then
    set -a
    . "$_ENVFILE"
    set +a
fi
for _var in COTDATA_STORE MARKETDATA_STORE; do
    if [ -z "${!_var:-}" ]; then
        echo "publish_surveys.sh: $_var is not set (add it to $_CHECKOUT/.env)." >&2
        exit 1
    fi
done

_PY="$REPO/.venv/bin/python"
[ -x "$_PY" ] || _PY="$_CHECKOUT/.venv/bin/python"
PAGES_DIR="${SURVEYS_PAGES_DIR:-$HOME/code/surveys-dashboard}"
PUBLISHER="${DBMF_TRACKER:-$_WORKSPACE/dbmf-tracker}/deploy/publish_pages.py"
[ -f "$PUBLISHER" ] || { echo "publish_surveys.sh: no publisher at $PUBLISHER" >&2; exit 1; }

_tmp="$(mktemp -d)"
trap 'rm -rf "$_tmp"' EXIT
PYTHONPATH="$REPO/src" "$_PY" scripts/export_sentiment_page.py "$_tmp/surveys.html"
# publish_pages.py is stdlib only; any python3 runs it.
"$_PY" "$PUBLISHER" --dashboard "$_tmp/surveys.html" --key surveys \
    --pages-dir "$PAGES_DIR" "$@"
