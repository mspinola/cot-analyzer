"""Weekly-email subscribers: the store, the tokens, and the fan-out send.

The weekly Signal Matrix email had exactly one recipient (RECEIVER_EMAIL_USER, the
operator) and no way for a site visitor to ask for it. This module is the whole
subscription feature except its two request surfaces: the About page renders the
form (components.subscribe) and app_cot serves the /confirm and /unsubscribe links.

Design decisions, each argued where it is implemented:

* **Double opt-in.** A public form that mails whatever address is typed into it is
  a harassment tool: anyone could sign up a victim. Nothing is sent weekly until
  the address's owner clicks a confirmation link that only their inbox received.
* **SQLite beside the weekly-email ledger**, not in cotmetrics' DB. Who subscribed
  to this deployment's email is deployment state, the same kind as which week was
  last sent; putting it in the shared cotmetrics DB would make a data-layer package
  the owner of a website's mailing list.
* **Tokens are capability URLs.** Confirm and unsubscribe are GET links in emails,
  so the token in the URL is the whole authentication. It is random (not derived
  from the email), never expires, and is stable across re-subscribes so the
  unsubscribe link in an old email keeps working.
* **The weekly fan-out reuses cotmetrics' build_message verbatim** and appends one
  extra HTML part carrying the per-recipient unsubscribe link. Appending a part
  rather than teaching build_message about footers keeps this feature out of a
  package three other callers share; clients render trailing inline-HTML parts of
  a multipart/mixed below the body, which is where a footer belongs anyway.
"""
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

import cotmetrics.utils as utils

#: Overrides for tests and unusual deployments. The DB defaults beside the
#: weekly-email ledger in the XDG data dir (see weekly_email_trigger.state_path for
#: why the *data* dir: an OS purge of ~/.cache must not erase a mailing list).
DB_ENV = "COT_SUBSCRIBERS_DB"

#: Where the links in emails point. The confirm and unsubscribe URLs are built by a
#: background thread with no request in sight, so the public origin cannot be read
#: off a request and must be stated.
BASE_URL_ENV = "COT_PUBLIC_BASE_URL"
DEFAULT_BASE_URL = "https://bluemagicai.com"

#: Deliberately loose: one @, no spaces, a dot somewhere after it. Real validation
#: is the confirmation email itself; a regex that rejects a deliverable address is
#: a worse failure than one that accepts a bouncing one.
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

#: The form's abuse valve: attempts per client address per window. Three is enough
#: for a typo and two corrections; the fourth is a script.
RATE_LIMIT = 3
RATE_WINDOW_SECONDS = 3600

_attempts = {}
_attempts_lock = threading.Lock()


def db_path(env=None):
    env = os.environ if env is None else env
    override = env.get(DB_ENV)
    if override:
        return Path(override)

    import cotmetrics.constants as const
    return Path(const.DB_PATH).parent / "subscribers.db"


def base_url(env=None):
    env = os.environ if env is None else env
    return (env.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip('/')


def _connect(env=None):
    path = db_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            email TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            subscribed_at TEXT NOT NULL,
            confirmed_at TEXT,
            unsubscribed_at TEXT
        )
    """)
    return conn


def _now():
    return datetime.now().isoformat(timespec="seconds")


def normalize_email(raw):
    """The stored spelling, or None for anything that is not an address.

    Lowercased whole, not just the domain: the local part is case-sensitive by RFC
    and case-insensitive at every provider anyone subscribes from, and a table
    where Foo@ and foo@ are two rows double-mails that person.
    """
    email = (raw or "").strip().lower()
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        return None
    return email


def allow_attempt(ip, now=None):
    """One form submission's rate check. True means proceed.

    In-memory on purpose: the limit exists to blunt a scripted loop, not to
    survive a restart, and a table of request timestamps would be the only thing
    in the subscribers DB that is not about a subscriber.
    """
    now = time.time() if now is None else now
    with _attempts_lock:
        stamps = [t for t in _attempts.get(ip, []) if now - t < RATE_WINDOW_SECONDS]
        if len(stamps) >= RATE_LIMIT:
            _attempts[ip] = stamps
            return False
        stamps.append(now)
        _attempts[ip] = stamps
        return True


def subscribe(raw_email, env=None):
    """Record intent to subscribe. Returns ('invalid'|'confirmed'|'pending', token).

    'confirmed' sends nothing: the form must not be usable to bombard an address
    that already gets the email. 'pending' covers a new address, a re-submitted
    unconfirmed one, and a previously unsubscribed one (which must re-confirm:
    an unsubscribe followed months later by a form submission is not proof the
    same person is behind both). The token is stable across all of it.
    """
    email = normalize_email(raw_email)
    if email is None:
        return "invalid", None

    conn = _connect(env)
    try:
        row = conn.execute(
            "SELECT token, confirmed_at, unsubscribed_at FROM subscribers "
            "WHERE email = ?", (email,)).fetchone()
        if row is None:
            token = secrets.token_urlsafe(24)
            conn.execute(
                "INSERT INTO subscribers (email, token, subscribed_at) "
                "VALUES (?, ?, ?)", (email, token, _now()))
            conn.commit()
            return "pending", token

        token, confirmed_at, unsubscribed_at = row
        if confirmed_at and not unsubscribed_at:
            return "confirmed", token
        conn.execute(
            "UPDATE subscribers SET subscribed_at = ?, confirmed_at = NULL, "
            "unsubscribed_at = NULL WHERE email = ?", (_now(), email))
        conn.commit()
        return "pending", token
    finally:
        conn.close()


def confirm(token, env=None):
    """Mark the token's address confirmed. Returns the email, or None.

    Idempotent, and it clears any unsubscribe: the link only exists in mail the
    address received, so a click is the owner speaking, whatever the row said.
    """
    if not token:
        return None
    conn = _connect(env)
    try:
        row = conn.execute("SELECT email FROM subscribers WHERE token = ?",
                           (token,)).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE subscribers SET confirmed_at = COALESCE(confirmed_at, ?), "
            "unsubscribed_at = NULL WHERE token = ?", (_now(), token))
        conn.commit()
        return row[0]
    finally:
        conn.close()


def unsubscribe(token, env=None):
    """Mark the token's address unsubscribed. Returns the email, or None.

    The row is kept, not deleted: the token must keep answering (so a second
    click of the same link says "already done" rather than "unknown link"), and
    a later re-subscribe goes back through confirmation because confirmed_at is
    what the fan-out reads, not the row's existence.
    """
    if not token:
        return None
    conn = _connect(env)
    try:
        row = conn.execute("SELECT email FROM subscribers WHERE token = ?",
                           (token,)).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE subscribers SET unsubscribed_at = COALESCE(unsubscribed_at, ?) "
            "WHERE token = ?", (_now(), token))
        conn.commit()
        return row[0]
    finally:
        conn.close()


def confirmed_subscribers(env=None):
    """[(email, token)] the weekly fan-out sends to, oldest subscription first."""
    conn = _connect(env)
    try:
        return conn.execute(
            "SELECT email, token FROM subscribers "
            "WHERE confirmed_at IS NOT NULL AND unsubscribed_at IS NULL "
            "ORDER BY subscribed_at").fetchall()
    finally:
        conn.close()


def _smtp(env=None, smtp_factory=None):
    from cotmetrics.weekly_email import SMTP_HOST, SMTP_PORT
    factory = smtp_factory or (lambda: smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT))
    return factory()


def send_confirmation(email, token, env=None, smtp_factory=None):
    """Mail the double-opt-in link. Raises WeeklyEmailNotConfigured when the
    EMAIL_* variables are absent, so the form can say so instead of pretending."""
    from cotmetrics.weekly_email import email_config
    sender, _receiver, password = email_config(env)
    link = f"{base_url(env)}/confirm?token={token}"

    msg = MIMEText(
        f"<p>Someone (hopefully you) asked to receive the weekly COT Signal "
        f"Matrix from COT Analyzer at this address.</p>"
        f"<p><a href=\"{link}\">Confirm your subscription</a> to start getting "
        f"it each week when the new CFTC report lands.</p>"
        f"<p style=\"color:#888;font-size:12px\">If this wasn't you, ignore this "
        f"email and nothing more will be sent.</p>", "html")
    msg["Subject"] = "Confirm your COT Analyzer weekly email"
    msg["From"] = sender
    msg["To"] = email

    server = _smtp(env, smtp_factory)
    try:
        server.login(sender, password)
        server.sendmail(sender, email, msg.as_string())
    finally:
        server.quit()
    utils.cot_logger.info(f"subscribers: confirmation link sent to {email}.")


def _footer(token, env=None):
    return MIMEText(
        f"<p style=\"color:#888;font-size:12px;margin-top:16px\">You are "
        f"receiving this because you subscribed at {base_url(env)}. "
        f"<a href=\"{base_url(env)}/unsubscribe?token={token}\">Unsubscribe</a>."
        f"</p>", "html")


def send_weekly_to_subscribers(env=None, smtp_factory=None):
    """The fan-out: the operator's exact email, per subscriber, plus a footer.

    The matrix is built once and the message rebuilt per recipient (cheap: the
    frame dominates, and get_matrix_data is cached). One failed recipient is
    logged and skipped, never fatal: this runs after the ledger's send has
    succeeded, so raising here could not trigger a retry that helps anyone.
    Returns how many were sent.
    """
    subs = confirmed_subscribers(env)
    if not subs:
        return 0

    from cotmetrics.reports import get_matrix_data
    from cotmetrics.weekly_email import build_message, email_config, report_date_for
    sender, _receiver, password = email_config(env)
    df = get_matrix_data(lookback="Custom")
    report_date = report_date_for(df)

    sent = 0
    server = _smtp(env, smtp_factory)
    try:
        server.login(sender, password)
        for email, token in subs:
            try:
                msg = build_message(df, report_date, sender, email)
                msg.attach(_footer(token, env))
                server.sendmail(sender, email, msg.as_string())
                sent += 1
            except Exception as e:
                utils.cot_logger.error(
                    f"subscribers: weekly send to {email} failed, skipping: {e}")
    finally:
        server.quit()
    utils.cot_logger.info(
        f"subscribers: weekly matrix sent to {sent}/{len(subs)} subscribers.")
    return sent


def send_weekly_everywhere(env=None):
    """What the store poller hands to weekly_email_trigger.maybe_send.

    The operator copy first, and only its failure propagates: maybe_send records
    the week as sent when this returns, so an exception from the fan-out would
    re-send next tick to every subscriber who already got theirs. Fan-out
    problems are per-recipient log lines instead.
    """
    from cotmetrics.weekly_email import send_weekly_matrix_email
    send_weekly_matrix_email(env=env)
    try:
        send_weekly_to_subscribers(env=env)
    except Exception as e:
        utils.cot_logger.error(
            f"subscribers: weekly fan-out failed after the operator send: {e}")
