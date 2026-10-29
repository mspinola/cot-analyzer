"""The subscriber lifecycle, and the promises the subscribe form makes.

What these pin, in the order a subscriber meets it: an address is stored once in
one spelling, nothing recurring is sent before a confirmation click, the token in
an old email keeps working forever, an unsubscribe sticks until the OWNER (a
confirmation click, not a form submission) reverses it, and the weekly fan-out
sends the operator's exact message per subscriber with that subscriber's
unsubscribe link, skipping a failed recipient rather than dying.

Everything runs against a temp SQLite file via COT_SUBSCRIBERS_DB and a stub
SMTP; no network, no real mailbox, no store.
"""
import pytest

import subscribers


@pytest.fixture()
def env(tmp_path):
    return {
        subscribers.DB_ENV: str(tmp_path / "subs.db"),
        subscribers.BASE_URL_ENV: "https://example.test",
        "EMAIL_USER": "sender@example.test",
        "RECEIVER_EMAIL_USER": "operator@example.test",
        "EMAIL_PASSWORD": "app-password",
    }


class StubSMTP:
    """Records what a send would have done. `fail_for` simulates one recipient
    the server rejects, which must not take the rest of the fan-out with it."""

    def __init__(self, fail_for=()):
        self.fail_for = set(fail_for)
        self.logins = []
        self.sent = []  # (to, message-string)

    def login(self, user, password):
        self.logins.append(user)

    def sendmail(self, sender, to, message):
        if to in self.fail_for:
            raise RuntimeError(f"mailbox unavailable: {to}")
        self.sent.append((to, message))

    def quit(self):
        pass


# ── the address itself ────────────────────────────────────────────────────────

def test_addresses_normalize_to_one_spelling():
    assert subscribers.normalize_email("  Foo@Example.COM ") == "foo@example.com"


def test_non_addresses_are_rejected():
    for raw in (None, "", "not-an-email", "a@b", "two @words.com",
                "a" * 300 + "@example.com"):
        assert subscribers.normalize_email(raw) is None, raw


# ── the lifecycle ─────────────────────────────────────────────────────────────

def test_a_new_address_is_pending_until_its_link_is_clicked(env):
    status, token = subscribers.subscribe("Reader@example.com", env)
    assert status == "pending" and token
    # Nothing recurring yet: the fan-out list is empty until the click.
    assert subscribers.confirmed_subscribers(env) == []

    assert subscribers.confirm(token, env) == "reader@example.com"
    assert subscribers.confirmed_subscribers(env) == [
        ("reader@example.com", token)]


def test_resubmitting_a_confirmed_address_sends_nothing_new(env):
    """The public form must not be usable to bombard an existing subscriber."""
    _, token = subscribers.subscribe("reader@example.com", env)
    subscribers.confirm(token, env)

    status, again = subscribers.subscribe("READER@example.com", env)
    assert status == "confirmed"
    assert again == token


def test_unsubscribe_sticks_and_the_form_cannot_undo_it(env):
    """A form submission is not proof the address's owner is behind it, so a
    re-subscribe after an unsubscribe goes back through confirmation."""
    _, token = subscribers.subscribe("reader@example.com", env)
    subscribers.confirm(token, env)
    assert subscribers.unsubscribe(token, env) == "reader@example.com"
    assert subscribers.confirmed_subscribers(env) == []

    status, same_token = subscribers.subscribe("reader@example.com", env)
    assert status == "pending"
    assert same_token == token  # the link in an old email keeps working
    assert subscribers.confirmed_subscribers(env) == []

    subscribers.confirm(token, env)
    assert subscribers.confirmed_subscribers(env) == [
        ("reader@example.com", token)]


def test_unknown_tokens_answer_none(env):
    assert subscribers.confirm("no-such-token", env) is None
    assert subscribers.unsubscribe("no-such-token", env) is None
    assert subscribers.confirm(None, env) is None


# ── the abuse valve ───────────────────────────────────────────────────────────

def test_the_rate_limit_counts_per_address_per_window():
    ip = "203.0.113.9"
    subscribers._attempts.clear()
    t = 1_000_000.0
    for i in range(subscribers.RATE_LIMIT):
        assert subscribers.allow_attempt(ip, now=t + i)
    assert not subscribers.allow_attempt(ip, now=t + 10)
    # Another address is unaffected, and the window expires.
    assert subscribers.allow_attempt("198.51.100.7", now=t + 10)
    assert subscribers.allow_attempt(ip, now=t + subscribers.RATE_WINDOW_SECONDS + 1)


# ── the emails ────────────────────────────────────────────────────────────────

def test_the_confirmation_email_carries_the_deployments_link(env):
    _, token = subscribers.subscribe("reader@example.com", env)
    smtp = StubSMTP()
    subscribers.send_confirmation("reader@example.com", token, env,
                                  smtp_factory=lambda: smtp)
    (to, message), = smtp.sent
    assert to == "reader@example.com"
    assert f"https://example.test/confirm?token={token}" in message


def _edition():
    """A one-market crowd_email.Edition, built the way the page builds a board
    (board_traces.build_rows over MarketReads) so no store or page is needed."""
    import cotmetrics.constants as const

    import crowd_email
    from components import board_traces
    from components.plot_colors import GridColors

    read = board_traces.MarketRead(asset="Gold", asset_class="Metals",
                                   windows=(90.0, 80.0, 70.0, 60.0), symbol="GC",
                                   move=5.0, state=const.SETUP_NONE,
                                   date="2026-08-25")
    rows, skipped = board_traces.build_rows([read])

    class Model:
        title = "Raw 3-leg 95/5"
    return crowd_email.Edition(
        board=board_traces.Board(rows=rows, report_date="2026-08-25",
                                 skipped=skipped, awaiting=[], stale=[],
                                 reads=[read]),
        model=Model(),
        colors=GridColors("#2ecc71", "#ff4d4d", "#2ecc71", "#ff4d4d"),
        caption="Caption.")


def test_the_fanout_sends_each_subscriber_their_own_unsubscribe_link(
        env, monkeypatch):
    import crowd_email

    def current_edition(model=None):
        # The real signature, never `lambda **kw`. A permissive stub once accepted
        # a call the real function refused: the fan-out called get_matrix_data
        # without its positional-required asset_classes, so every real weekly
        # fan-out failed (2026-09-12, after the operator copy had already gone
        # out) while this file stayed green.
        return _edition()
    monkeypatch.setattr(crowd_email, "current_edition", current_edition)

    tokens = {}
    for addr in ("a@example.com", "b@example.com"):
        _, token = subscribers.subscribe(addr, env)
        subscribers.confirm(token, env)
        tokens[addr] = token

    smtp = StubSMTP()
    sent = subscribers.send_weekly_to_subscribers(env, smtp_factory=lambda: smtp)
    assert sent == 2
    for to, message in smtp.sent:
        assert f"/unsubscribe?token={tokens[to]}" in message
        # The other subscriber's token must never ride along.
        other = next(t for a, t in tokens.items() if a != to)
        assert other not in message


def test_one_failed_recipient_does_not_stop_the_fanout(env):
    for addr in ("a@example.com", "b@example.com", "c@example.com"):
        _, token = subscribers.subscribe(addr, env)
        subscribers.confirm(token, env)

    smtp = StubSMTP(fail_for={"b@example.com"})
    sent = subscribers.send_weekly_to_subscribers(
        env, smtp_factory=lambda: smtp, edition=_edition())
    assert sent == 2
    assert {to for to, _ in smtp.sent} == {"a@example.com", "c@example.com"}


def test_an_empty_list_touches_no_smtp(env):
    def explode():
        raise AssertionError("no subscribers, no connection")
    assert subscribers.send_weekly_to_subscribers(
        env, smtp_factory=explode) == 0


def test_the_poller_send_survives_a_fanout_failure(env, monkeypatch):
    """Only the operator half may fail the ledger: a raised fan-out would re-send
    next tick to every subscriber who already got theirs."""
    import crowd_email
    edition = _edition()
    monkeypatch.setattr(crowd_email, "current_edition", lambda model=None: edition)
    operator_sent = []

    def send_operator_copy(env=None, smtp_factory=None, edition=None):
        operator_sent.append(edition)
    monkeypatch.setattr(crowd_email, "send_operator_copy", send_operator_copy)

    fanout_got = []

    def boom(env=None, smtp_factory=None, edition=None):
        fanout_got.append(edition)
        raise RuntimeError("smtp fell over mid-fanout")
    monkeypatch.setattr(subscribers, "send_weekly_to_subscribers", boom)

    subscribers.send_weekly_everywhere(env)  # must not raise
    # One edition, built once, and the SAME one went to both halves.
    assert operator_sent == [edition] and fanout_got == [edition]

    # The operator half failing is a different story: it must propagate, so the
    # trigger's ledger records nothing and retries.
    def operator_boom(env=None, smtp_factory=None, edition=None):
        raise RuntimeError("not configured")
    monkeypatch.setattr(crowd_email, "send_operator_copy", operator_boom)
    with pytest.raises(RuntimeError):
        subscribers.send_weekly_everywhere(env)


def test_an_empty_board_fails_the_operator_half_so_the_ledger_retries(
        env, monkeypatch):
    """Building the edition is the operator half's first step. A week whose board
    has no markets raises there, before anyone is mailed an empty table."""
    import crowd_email

    def empty(model=None):
        raise crowd_email.EmptyBoard("the board has no markets this week")
    monkeypatch.setattr(crowd_email, "current_edition", empty)
    monkeypatch.setattr(crowd_email, "send_operator_copy",
                        lambda **kw: pytest.fail("mailed an empty board"))
    with pytest.raises(crowd_email.EmptyBoard):
        subscribers.send_weekly_everywhere(env)
