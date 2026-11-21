#!/bin/bash
# Read-only post-deploy check: does the running site serve what the code ships?
#
# The verify-scheduling.ps1 ethos, for this box: starts nothing, writes nothing,
# and checks the OUTSIDE of the service (through nginx when given the public
# origin), because that is the path readers and crawlers take. A green
# `systemctl status` only says the process is up; every one of these checks has
# failed at least once with the service green (the "Dash" title shipped for
# years, /robots.txt 404ed until 2026-08-31, and the first /weekly render 500ed
# on an argument mismatch the tests had stubbed away).
#
#   ./verify-deploy.sh                        # checks https://bluemagicai.com
#   ./verify-deploy.sh http://127.0.0.1:5001  # or the origin directly
#
# Exits non-zero if anything fails, so it can gate a scripted deploy.
set -u

BASE="${1:-https://bluemagicai.com}"
BASE="${BASE%/}"
PASS=0
FAIL=0

check() {  # check <name> <url> <expected-status> [required-substring]
    local name="$1" url="$2" want="$3" needle="${4:-}"
    local body status
    body=$(curl -sS --max-time 30 -w '\n%{http_code}' "$url" 2>/dev/null)
    status="${body##*$'\n'}"
    body="${body%$'\n'*}"
    if [ "$status" != "$want" ]; then
        echo "FAIL  $name: expected HTTP $want, got $status ($url)"
        FAIL=$((FAIL+1)); return
    fi
    if [ -n "$needle" ] && ! printf '%s' "$body" | grep -qF -- "$needle"; then
        echo "FAIL  $name: HTTP $status but body lacks '$needle' ($url)"
        FAIL=$((FAIL+1)); return
    fi
    echo "pass  $name"
    PASS=$((PASS+1))
}

echo "Verifying $BASE"
echo

# The app itself, and the search surface shipped 2026-08-31: per-page served
# titles (the framework default was "Dash"), crawl policy, sitemap, and the
# crawlable noscript block.
check "home serves and is titled"      "$BASE/"            200 "<title>COT Analyzer"
check "heatmap serves its own title"   "$BASE/heatmap"     200 "<title>COT Signal Matrix Heatmap"
check "shell carries crawlable text"   "$BASE/"            200 "<noscript>"
check "robots.txt names the sitemap"   "$BASE/robots.txt"  200 "Sitemap:"
check "robots.txt shields admin"       "$BASE/robots.txt"  200 "Disallow: /admin"
check "sitemap lists the pages"        "$BASE/sitemap.xml" 200 "<loc>"
check "sitemap lists weekly reports"   "$BASE/sitemap.xml" 200 "/weekly/"

# The weekly report pages. The report check derives the newest week from the
# archive itself, so this needs no knowledge of the store's dates.
week=$(curl -sS --max-time 30 "$BASE/weekly" 2>/dev/null \
       | grep -oE '/weekly/[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)
check "weekly archive serves"          "$BASE/weekly"      200 "Weekly COT Reports"
if [ -n "$week" ]; then
    check "newest weekly report renders" "$BASE$week"      200 "<table"
    check "weekly report links the app"  "$BASE$week"      200 "/heatmap?date="
else
    echo "FAIL  weekly archive lists no dated reports"
    FAIL=$((FAIL+1))
fi

# The install surface (Add to Home screen on Android needs both).
check "manifest serves"                "$BASE/manifest.webmanifest" 200 '"display": "standalone"'
check "service worker serves"          "$BASE/sw.js"       200 "addEventListener('fetch'"
check "install icon serves"            "$BASE/assets/icon-512.png"  200

# Local-only pages draw licensed data (src/local_pages.py). A 200 here means
# COT_ANALYZER_LOCAL_PAGES is set on the server, which publishes that data.
check "local-only sentiment page is absent" "$BASE/sentiment"  404

# The news-failure scan may be served (COT_ANALYZER_PRIVATE_PAGES), but only to a
# browser logged in at /admin. Unregistered it 404s; registered, the page shell is
# public like every Dash page, so the check is on its DATA: the callback, asked with
# no session, must refuse (204, Dash's answer to PreventUpdate). A 200 here means the
# board went to anyone who POSTs. Nothing is logged in, written or sent.
nf_status=$(curl -s -o /dev/null --max-time 30 -w '%{http_code}' "$BASE/news-failure")
if [ "$nf_status" = "404" ]; then
    echo "pass  news-failure scan is not served (flag off)"
    PASS=$((PASS+1))
elif [ "$nf_status" = "200" ]; then
    nf_cb=$(curl -s -o /dev/null --max-time 30 -w '%{http_code}' \
        -H 'Content-Type: application/json' -X POST "$BASE/_dash-update-component" \
        --data '{"output":"..news_failure_body.children...news_failure_date.disabled...news_failure_window_wrap.style..","outputs":[{"id":"news_failure_body","property":"children"},{"id":"news_failure_date","property":"disabled"},{"id":"news_failure_window_wrap","property":"style"}],"inputs":[{"id":"news_failure_date","property":"value","value":null},{"id":"news_failure_market","property":"value","value":"NG"},{"id":"news_failure_window","property":"value","value":0},{"id":"news_failure_model","property":"value","value":null}],"changedPropIds":["news_failure_market.value"]}')
    if [ "$nf_cb" = "204" ]; then
        echo "pass  news-failure scan refuses a logged-out callback"
        PASS=$((PASS+1))
    else
        echo "FAIL  news-failure scan: logged-out callback got HTTP $nf_cb, expected 204"
        FAIL=$((FAIL+1))
    fi
else
    echo "FAIL  news-failure scan: expected HTTP 404 or 200, got $nf_status"
    FAIL=$((FAIL+1))
fi

# The subscription endpoints exist and refuse garbage; nothing here subscribes,
# confirms or sends anything.
check "confirm rejects a bad token"    "$BASE/confirm?token=verify-deploy-probe"     404 "not valid"
check "unsubscribe rejects a bad token" "$BASE/unsubscribe?token=verify-deploy-probe" 404 "not valid"

# The merged chart page's old address, and the guard that keeps scanner paths
# from being answered with a full app shell.
check "old /graphs address redirects"  "$BASE/graphs"      301
check "unknown paths still 404"        "$BASE/definitely-not-a-page-xyz" 404

echo
echo "$PASS passed, $FAIL failed."
[ "$FAIL" -eq 0 ]
