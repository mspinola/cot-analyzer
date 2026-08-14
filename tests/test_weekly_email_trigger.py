"""The weekly email fires once per COT week, and only where it is switched on.

Nothing here sends anything: `maybe_send` takes the sender as an argument and every
test passes a spy. The trigger's whole job is deciding WHETHER to send, so that is
what is under test.

Context for why the guards exist: the original trigger lived in a deleted ETL
scheduler and fired on download. This box does not download, so the replacement fires
off the store poller, which runs every five minutes forever. Everything that could
turn "once a week" into "every five minutes" is a test below.
"""
import json

import pytest

import weekly_email_trigger as trigger

ON = {"COT_WEEKLY_EMAIL": "1"}


@pytest.fixture
def ledger(tmp_path):
    """A state file path, isolated from the real XDG data dir."""
    return tmp_path / "weekly_email.json"


def env_with(ledger, **extra):
    return {**ON, "COT_WEEKLY_EMAIL_STATE": str(ledger), **extra}


class Spy:
    def __init__(self, fails=False):
        self.calls, self.fails = 0, fails

    def __call__(self, *a, **kw):
        self.calls += 1
        if self.fails:
            raise OSError("smtp is down")
        return "2026-08-11"


def seed(ledger, week):
    ledger.write_text(json.dumps({"last_sent_week": week}))


# ── the switch ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_the_flag_accepts_the_usual_spellings(value, ledger):
    seed(ledger, "2026-08-04")
    send = Spy()

    assert trigger.maybe_send("2026-08-11",
                              env=env_with(ledger, COT_WEEKLY_EMAIL=value),
                              send=send) == "sent"
    assert send.calls == 1


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_anything_else_is_off(value, ledger):
    """Both boxes run this code. A local run-local.sh must not mail anyone."""
    seed(ledger, "2026-08-04")
    send = Spy()

    assert trigger.maybe_send("2026-08-11",
                              env=env_with(ledger, COT_WEEKLY_EMAIL=value),
                              send=send) == "disabled"
    assert send.calls == 0


def test_an_unset_flag_is_off(ledger):
    send = Spy()
    env = {"COT_WEEKLY_EMAIL_STATE": str(ledger)}

    assert trigger.maybe_send("2026-08-11", env=env, send=send) == "disabled"
    assert send.calls == 0


# ── once per week ─────────────────────────────────────────────────────────────

def test_a_new_week_sends_and_records(ledger):
    seed(ledger, "2026-08-04")
    send = Spy()

    assert trigger.maybe_send("2026-08-11", env=env_with(ledger), send=send) == "sent"
    assert send.calls == 1
    assert json.loads(ledger.read_text())["last_sent_week"] == "2026-08-11"


def test_the_same_week_never_sends_again(ledger):
    """The poller ticks every five minutes forever. This is the test that matters."""
    seed(ledger, "2026-08-11")
    send = Spy()

    for _ in range(10):
        assert trigger.maybe_send("2026-08-11", env=env_with(ledger),
                                  send=send) == "already-sent"
    assert send.calls == 0


def test_a_restart_mid_week_does_not_resend(ledger):
    """The ledger is on disk precisely so a restart is not a new week."""
    send = Spy()
    trigger.maybe_send("2026-08-04", env=env_with(ledger), send=send)   # seeds
    trigger.maybe_send("2026-08-11", env=env_with(ledger), send=send)   # sends

    # ...process dies, comes back, polls again
    assert trigger.maybe_send("2026-08-11", env=env_with(ledger),
                              send=send) == "already-sent"
    assert send.calls == 1


# ── the states that are not a week ────────────────────────────────────────────

def test_an_unreadable_store_sends_nothing(ledger):
    """None is no answer, not a new week. Same rule the index refresh follows."""
    seed(ledger, "2026-08-04")
    send = Spy()

    assert trigger.maybe_send(None, env=env_with(ledger), send=send) == "no-week"
    assert send.calls == 0
    assert json.loads(ledger.read_text())["last_sent_week"] == "2026-08-04"


@pytest.mark.parametrize("value", ["Unknown", "", "null", "2026-08", "not a date"])
def test_anything_that_is_not_a_date_is_not_a_week(value, ledger):
    """"Unknown" is what an older cotmetrics returns from a torn status.json read.

    It compares unequal to every real week, so treating it as one would mail a report
    when the sync truncated the file and a second when the real date came back. This
    trigger must hold whichever version of that read is installed, since the fix lives
    in another repo on another branch.
    """
    seed(ledger, "2026-08-04")
    send = Spy()

    assert trigger.maybe_send(value, env=env_with(ledger), send=send) == "no-week"
    assert send.calls == 0


def test_a_first_run_seeds_without_sending(ledger):
    """Enabling the flag must not itself produce an email. See the module docstring."""
    send = Spy()

    assert trigger.maybe_send("2026-08-11", env=env_with(ledger), send=send) == "seeded"
    assert send.calls == 0
    assert json.loads(ledger.read_text())["last_sent_week"] == "2026-08-11"


def test_the_week_after_seeding_is_the_first_one_mailed(ledger):
    send = Spy()
    trigger.maybe_send("2026-08-11", env=env_with(ledger), send=send)

    assert trigger.maybe_send("2026-08-18", env=env_with(ledger), send=send) == "sent"
    assert send.calls == 1


def test_a_corrupt_ledger_reseeds_rather_than_resending(ledger):
    """Losing the record costs one email. Ignoring it costs one every five minutes."""
    ledger.write_text("{ this is not json")
    send = Spy()

    assert trigger.maybe_send("2026-08-11", env=env_with(ledger), send=send) == "seeded"
    assert send.calls == 0


# ── failure ───────────────────────────────────────────────────────────────────

def test_a_failed_send_is_not_recorded_so_it_retries(ledger):
    seed(ledger, "2026-08-04")
    failing = Spy(fails=True)

    assert trigger.maybe_send("2026-08-11", env=env_with(ledger),
                              send=failing) == "failed"
    assert json.loads(ledger.read_text())["last_sent_week"] == "2026-08-04"

    working = Spy()
    assert trigger.maybe_send("2026-08-11", env=env_with(ledger),
                              send=working) == "sent"
    assert working.calls == 1


def test_a_missing_sender_reports_as_an_email_failure(ledger, monkeypatch):
    """These two changes are separate branches. Merged out of order, cotmetrics has no
    weekly_email, and that must read as an email problem rather than as a store poller
    that breaks every five minutes with no stated cause."""
    import builtins
    real_import = builtins.__import__

    def no_weekly_email(name, *a, **kw):
        if "weekly_email" in name:
            raise ImportError("No module named 'cotmetrics.weekly_email'")
        return real_import(name, *a, **kw)

    seed(ledger, "2026-08-04")
    monkeypatch.setattr(builtins, "__import__", no_weekly_email)

    assert trigger.maybe_send("2026-08-11", env=env_with(ledger)) == "failed"
    assert json.loads(ledger.read_text())["last_sent_week"] == "2026-08-04"


def test_a_failed_send_does_not_escape(ledger):
    """It runs inside the store poller. An exception here stops the app noticing new
    data at all, which is a much worse failure than a missed email."""
    seed(ledger, "2026-08-04")

    assert trigger.maybe_send("2026-08-11", env=env_with(ledger),
                              send=Spy(fails=True)) == "failed"
