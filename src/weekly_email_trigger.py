"""Mail the weekly Signal Matrix once, when the store takes a new COT week.

This puts back a trigger that existed until 2026-07-24. `cotmetrics` used to carry a
`CotJobScheduler` that polled the CFTC, ran an ETL, and emailed the matrix on new data,
started by `main.py` as a subprocess. ADR-0006 made cotdata the sole COT producer and
deleted the pipeline, the trigger with it (cotmetrics 606d15c, cot-analyzer ec61a25).
Its documented replacement was a crontab line the operator adds by hand, which was
never added anywhere, so no weekly email has been sent since.

IT CANNOT GO BACK WHERE IT WAS, because the event it hung off no longer happens here.
The deployed box does not download COT: the store arrives as an rsync push from the
Windows producer. The only local event meaning "a new week exists" is the store poller
noticing status.json moved, so that is what this hangs off.

Two guards, and both are load-bearing:

* **Opt-in.** `COT_WEEKLY_EMAIL` is unset by default and set only on the deployment.
  Both boxes run this code, and a developer running run-local.sh must not start mailing
  the world every Friday.
* **Once per week, recorded on disk.** A ledger file, not an in-memory flag. A restart
  during the Friday window, a second worker, or a browser tab that happens to win the
  refresh race would each otherwise produce another copy of the same email.

The ledger is SEEDED WITHOUT SENDING the first time it is missing. Enabling a trigger
whose state has never been written is how a flag fires on its first tick and reports it
as news, which is the same trap npf's `--edge-decay` documents: turn it on after there
is state, or it fires on nothing. Here the cost is only a duplicate email, but the
first thing an operator does after enabling a feature is judge it by what it does, and
"it emailed immediately" is indistinguishable from "it thinks this week is new".
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

import cotmetrics.utils as utils

#: A COT week is a date. Anything else is not a week, however confidently it is
#: reported. This is a SHAPE check rather than a None check on purpose: the store read
#: has historically answered a failure with the string "Unknown", which compares
#: unequal to every real week and would therefore mail one report when the sync
#: truncated status.json and a second when the real date came back. Whether that read
#: is fixed to return None is a separate concern in a separate repo, and this trigger
#: must not depend on which version of it is installed.
_WEEK = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Set to 1/true/yes on the deployment to enable sending. Anything else is off.
ENABLE_ENV = "COT_WEEKLY_EMAIL"

#: Where the last-sent week is recorded. Durable state, not a cache: it defaults
#: beside the visitor-log SQLite DB in the XDG *data* dir, never under COTMETRICS_CACHE,
#: because an OS purge of ~/.cache would silently re-arm the send.
STATE_ENV = "COT_WEEKLY_EMAIL_STATE"

_TRUE = {"1", "true", "yes", "on"}


def enabled(env=None):
    env = os.environ if env is None else env
    return str(env.get(ENABLE_ENV, "")).strip().lower() in _TRUE


def state_path(env=None):
    env = os.environ if env is None else env
    override = env.get(STATE_ENV)
    if override:
        return Path(override)

    import cotmetrics.constants as const
    return Path(const.DB_PATH).parent / "weekly_email.json"


def read_last_sent(path):
    """The week the last email covered, or None if the ledger is absent/unreadable.

    An unreadable ledger reads as absent, which re-seeds rather than re-sends. That is
    the safe direction: the cost of losing the record is one email nobody gets, and the
    cost of ignoring it is an email every five minutes.
    """
    try:
        with open(path) as f:
            return json.load(f).get("last_sent_week")
    except Exception:
        return None


def write_last_sent(path, week):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump({"last_sent_week": week,
                   "recorded_at": datetime.now().isoformat(timespec="seconds")}, f)
    # Replace rather than truncate-and-write: this file is read by the next tick, and
    # a half-written ledger reads as absent, which re-arms the send.
    os.replace(tmp, path)


def maybe_send(week, env=None, send=None):
    """Send the weekly email if `week` is new. Returns what it did, for the log.

    One of: 'disabled', 'no-week', 'seeded', 'already-sent', 'sent', 'failed'.

    `week` is the store's current COT week. Anything that is not a date (None, or the
    "Unknown" sentinel an older store read returns) means no answer rather than no
    data, so it is not a reason to do anything. Same rule the index refresh follows.
    """
    if not enabled(env):
        return "disabled"
    if not week or not _WEEK.match(str(week)):
        return "no-week"

    path = state_path(env)
    last_sent = read_last_sent(path)

    if last_sent is None:
        write_last_sent(path, week)
        utils.cot_logger.info(
            f"weekly email: seeded the ledger at {week} without sending. The next "
            f"COT week will be the first one mailed.")
        return "seeded"

    if last_sent == week:
        return "already-sent"

    try:
        # Imported here, inside the guard, so a cotmetrics without weekly_email
        # (these two changes are separate branches and can merge in either order)
        # reports itself as an email failure rather than as a store poller that
        # breaks every five minutes for no stated reason.
        if send is None:
            from cotmetrics.weekly_email import send_weekly_matrix_email as send

        send()
    except Exception as e:
        # Never let this kill the poller. A missed email is a bad Friday; a dead
        # poller is a site that stops noticing new data at all, which is the far
        # more expensive failure and the one this whole area exists to prevent.
        utils.cot_logger.error(f"weekly email: send failed for {week}, will retry on "
                               f"the next poll: {e}")
        return "failed"

    # Recorded only after a send that returned. A ledger written first would turn one
    # failed send into a week with no email and no retry.
    write_last_sent(path, week)
    return "sent"
