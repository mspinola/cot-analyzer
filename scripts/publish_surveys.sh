#!/usr/bin/env bash
# Rebuild the static sentiment page and publish it to surveys.bluemagicai.com.
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
# Scheduled on the VPS (root's crontab, server-side/publish-surveys.cron), which holds
# every store the page reads (the Windows producer pushes both after each run) and
# cot-analyzer's own venv. Runnable by hand on the Mac too, for a test. ONE machine is
# scheduled: each publish force-pushes a single-commit branch.
# docs/surveys-publishing.md has the whole picture.
#
# The environment is resolved like run-local.sh's (worktree-safe, cotmetrics-config
# beside the checkout), because a cron job reads no profile. From .env it takes ONLY the
# four variables below, by parsing rather than sourcing: the server's .env carries mail
# and admin credentials that this job has no business loading, and sourcing executes
# whatever a value happens to contain.
#
#   scripts/publish_surveys.sh              # rebuild and publish if changed
#   scripts/publish_surveys.sh --dry-run    # rebuild, say what would be pushed
#
# Extra arguments go to publish_pages.py. SURVEYS_PAGES_DIR overrides the clone (default
# surveys-dashboard beside the workspace: ~/code/ on the Mac, /root/ on the VPS);
# DBMF_TRACKER overrides the publisher checkout (default the workspace's dbmf-tracker).
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
_ENVFILE="$REPO/.env"
[ -f "$_ENVFILE" ] || _ENVFILE="$_CHECKOUT/.env"
_env_get() {
    # The last KEY=value line for $1, surrounding quotes stripped; empty if absent.
    [ -f "$_ENVFILE" ] || return 0
    # `|| true`: a key that is absent is not an error here, and under pipefail grep's
    # no-match status would otherwise end the script at the assignment.
    { grep -E "^$1=" "$_ENVFILE" || true; } | tail -1 | cut -d= -f2- \
        | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}
for _var in COTDATA_STORE MARKETDATA_STORE COTMETRICS_PARAMS COT_VIZ_CONFIG; do
    if [ -z "${!_var:-}" ]; then
        _val="$(_env_get "$_var")"
        [ -n "$_val" ] && export "$_var=$_val"
    fi
done

_params="$_WORKSPACE/cotmetrics-config/params.yaml"
[ -n "${COTMETRICS_PARAMS:-}" ] || { [ -f "$_params" ] && export COTMETRICS_PARAMS="$_params"; }
if [ ! -f "${COTMETRICS_PARAMS:-/nonexistent}" ]; then
    # Without it cotmetrics falls back to a 6-symbol sample, silently.
    echo "publish_surveys.sh: no params.yaml (COTMETRICS_PARAMS='${COTMETRICS_PARAMS:-}')." >&2
    exit 1
fi
export COT_VIZ_CONFIG="${COT_VIZ_CONFIG:-$COTMETRICS_PARAMS}"
export COT_SKIP_BOOT_FETCH=1
for _var in COTDATA_STORE MARKETDATA_STORE; do
    if [ -z "${!_var:-}" ]; then
        echo "publish_surveys.sh: $_var is not set (add it to $_CHECKOUT/.env)." >&2
        exit 1
    fi
done

_PY="$REPO/.venv/bin/python"
[ -x "$_PY" ] || _PY="$_CHECKOUT/.venv/bin/python"
PAGES_DIR="${SURVEYS_PAGES_DIR:-$(cd "$_WORKSPACE/.." && pwd)/surveys-dashboard}"
PUBLISHER="${DBMF_TRACKER:-$_WORKSPACE/dbmf-tracker}/deploy/publish_pages.py"
[ -f "$PUBLISHER" ] || { echo "publish_surveys.sh: no publisher at $PUBLISHER" >&2; exit 1; }

_tmp="$(mktemp -d)"
trap 'rm -rf "$_tmp"' EXIT
echo "publish_surveys.sh: $(date '+%Y-%m-%d %H:%M %Z') rendering"
PYTHONPATH="$REPO/src" "$_PY" scripts/export_sentiment_page.py "$_tmp/surveys.html"
# publish_pages.py is stdlib only; any python3 runs it.
"$_PY" "$PUBLISHER" --dashboard "$_tmp/surveys.html" --key surveys \
    --pages-dir "$PAGES_DIR" "$@"
