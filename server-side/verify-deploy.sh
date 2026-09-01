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
