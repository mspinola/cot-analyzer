"""How a signal card reads one row.

`_safe_getter` decides what happens when a value is not there, and the two cases are
not the same. A NaN is a data condition: the metric exists and has nothing to say this
week, so the neutral default is the right answer and the card should say nothing about
it. A missing column is a bug: `get_symbols_data` stopped emitting something, or the
name is misspelled, and the neutral default then renders as an ordinary reading for a
metric nobody computed.

Added in cot-analyzer#61. These are its first tests.
"""

import cotmetrics.constants as const
import numpy as np
import pandas as pd
import pytest

from components.signal_cards import _safe_getter


class _RecordingLogger:
    """Stand-in for utils.cot_logger, so the assertion does not depend on how the
    real logger is configured or whether it propagates to caplog."""

    def __init__(self):
        self.errors = []

    def error(self, msg, *args):
        self.errors.append(msg % args if args else msg)


@pytest.fixture
def log(monkeypatch):
    import cotmetrics.utils as utils
    recorder = _RecordingLogger()
    monkeypatch.setattr(utils, "cot_logger", recorder)
    return recorder


@pytest.fixture
def row():
    return pd.Series({
        const.COMMS_IDX: 88.0,
        const.LRG_ZSCORE: np.nan,
        const.WILLCO_ALIAS: 0.0,
    })


def test_a_present_value_passes_through(row, log):
    assert _safe_getter(row, "probe")(const.COMMS_IDX, 50) == 88.0
    assert log.errors == []


def test_a_falsy_value_is_not_mistaken_for_missing(row, log):
    """0 is a real WillCo reading, and the most bearish one there is. Returning the
    neutral 50 here would invert the card."""
    assert _safe_getter(row, "probe")(const.WILLCO_ALIAS, 50) == 0.0
    assert log.errors == []


def test_a_nan_returns_the_default_quietly(row, log):
    """A data condition, not a bug. Nothing to report."""
    assert _safe_getter(row, "probe")(const.LRG_ZSCORE, 0) == 0
    assert log.errors == []


def test_a_missing_column_returns_the_default_and_says_so(row, log):
    """The case the neutral defaults would otherwise hide."""
    assert _safe_getter(row, "build_signal_panel(GC)")("coms_idx", 50) == 50
    assert len(log.errors) == 1
    message = log.errors[0]
    assert "coms_idx" in message
    assert "build_signal_panel(GC)" in message, "context must identify the caller"
    assert "50" in message, "the substituted value must be visible"


def test_the_two_absences_are_distinguishable(row, log):
    """The distinction is the whole point: same return value, different report."""
    get = _safe_getter(row, "probe")
    assert get(const.LRG_ZSCORE, 0) == get("not_a_column", 0) == 0
    assert len(log.errors) == 1
    assert "not_a_column" in log.errors[0]


def test_every_alias_the_cards_read_is_reported_when_absent(log):
    """An empty row means every read is a miss, so each one must announce itself
    rather than silently producing a full panel of neutral readings."""
    get = _safe_getter(pd.Series(dtype=float), "probe")
    aliases = [const.COMMS_IDX, const.LRG_IDX, const.SML_IDX,
               const.COMMS_ZSCORE, const.LRG_ZSCORE, const.SML_ZSCORE,
               const.WILLCO_ALIAS, const.OI_ZSCORE, const.COMM_MOMENTUM]
    for alias in aliases:
        assert get(alias, 50) == 50
    assert len(log.errors) == len(aliases)
