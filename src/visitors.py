"""Who a request is from, without keeping anything that identifies them.

The arguable half of visitor tracking, split out of `app_cot` the way `routing` holds
the url-membership test: pure functions over strings, importable without a Dash app,
pinned by tests. The I/O half (the request hook, the geolocation worker, the database
row) stays in `app_cot`.
"""
import hashlib
from datetime import datetime, timezone

#: Substrings that mark a user agent as automated. Matched case-insensitively. The
#: list is deliberately short and generic: 'bot' alone catches Googlebot, bingbot,
#: AhrefsBot, DotBot and most of the rest, and the tail entries catch the script
#: clients and uptime monitors that do not self-describe as bots. A miss in either
#: direction only mislabels one row's `is_bot` flag, so this is tuned for obviousness
#: rather than completeness.
BOT_MARKERS = (
    'bot', 'crawler', 'spider', 'crawling', 'curl', 'wget', 'python-requests',
    'python-urllib', 'go-http-client', 'httpclient', 'headless', 'scrapy',
    'monitor', 'uptime', 'probe', 'scan',
)


def client_ip(forwarded_for, remote_addr):
    """The client's address: the FIRST X-Forwarded-For entry, else the socket peer.

    Behind the deployment's reverse proxy `remote_addr` is always 127.0.0.1 and the
    real client arrives in X-Forwarded-For, which is a comma-separated CHAIN once any
    second proxy is involved ("client, proxy1, proxy2"). The old code stored the whole
    header; the visitor hash needs one stable address, and the client is the first
    entry by definition.
    """
    if forwarded_for:
        first = forwarded_for.split(',')[0].strip()
        if first:
            return first
    return remote_addr or ''


def is_bot(user_agent):
    """Does this user agent describe an automated client?

    An EMPTY user agent is a bot: every browser sends one, and the traffic that
    arrives without one here is scanners and hand-rolled scripts.
    """
    if not user_agent:
        return True
    ua = user_agent.lower()
    return any(marker in ua for marker in BOT_MARKERS)


def visitor_id(ip, user_agent, day=None):
    """A daily-rotating pseudonymous id: sha256 of day, ip and user agent, 16 hex chars.

    The construction is the one the privacy-first analytics tools settled on
    (Plausible, GoatCounter): stable enough within a day to count uniques, sessions
    and pages-per-visit, and rotating at midnight UTC so it cannot accumulate into a
    cross-day profile. No cookie, so nothing to consent-banner.

    `day` defaults to today in UTC and is injectable for tests. The digest is
    truncated to 16 hex characters (64 bits), plenty against collision at this
    traffic scale and short enough to read in the admin table.
    """
    if day is None:
        day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    raw = f"{day}|{ip}|{user_agent or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
