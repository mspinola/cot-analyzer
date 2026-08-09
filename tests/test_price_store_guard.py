"""The boot guard's POLICY, pinned without a store.

`check_price_store` is I/O: read the universe, ask marketdata, log. The arguable
part is what it does with the answer, and that is `price_store_verdict`, which is
pure. These tests pin the line between "say so and carry on" and "refuse to boot",
because getting that line wrong in either direction is a real cost: refuse too
eagerly and a data gap takes down the positioning half of a site that was working;
refuse too rarely and you are back to the failure this exists for, which is a
dashboard that boots happily and draws blank charts.
"""
from dataclasses import dataclass

import pytest

from main import price_store_verdict


@dataclass(frozen=True)
class FakeGap:
    """Stands in for marketdata.Gap. Only `reason` is read by the policy."""
    symbol: str
    tier: str
    reason: str
    detail: str = ""


def absent_everything(symbols):
    """What an unfilled store returns: both stored tiers missing for every symbol."""
    return [FakeGap(s, t, "absent")
            for s in symbols for t in ("backadj", "unadj")]


def test_a_store_with_no_gaps_is_ok():
    verdict, message = price_store_verdict(["ES", "GC"], [])
    assert verdict == "ok"
    assert "2 instruments" in message


def test_nothing_at_all_refuses_to_boot():
    syms = ["ES", "GC", "CL"]
    verdict, message = price_store_verdict(syms, absent_everything(syms))
    assert verdict == "refuse"
    assert "no price chart on this site can render" in message
    # The message has to name a fix, not just a diagnosis.
    assert "import_from_cotdata.py" in message


def test_the_escape_hatch_downgrades_the_refusal():
    syms = ["ES", "GC"]
    verdict, _ = price_store_verdict(syms, absent_everything(syms),
                                     allow_missing=True)
    assert verdict == "warn"


def test_a_subset_missing_warns_rather_than_taking_the_site_down():
    """Most of the site still works, and a human decides whether it matters."""
    gaps = [FakeGap("ES", "backadj", "absent"), FakeGap("ES", "unadj", "absent")]
    verdict, message = price_store_verdict(["ES", "GC", "CL"], gaps)
    assert verdict == "warn"
    assert "Positioning is unaffected" in message


def test_half_a_store_is_not_an_empty_one():
    """Only `backadj` present for every symbol. Counted against stored SERIES, not
    symbols, so this is half-filled and warns rather than reading as empty."""
    syms = ["ES", "GC"]
    gaps = [FakeGap(s, "unadj", "absent") for s in syms]
    assert price_store_verdict(syms, gaps)[0] == "warn"


@pytest.mark.parametrize("reason", ["stale", "short"])
def test_stale_and_short_never_refuse(reason):
    """However many there are. A store that is merely old still draws charts, and
    refusing on it would mean a holiday weekend could take the site down."""
    syms = ["ES", "GC"]
    gaps = [FakeGap(s, t, reason) for s in syms for t in ("backadj", "unadj")]
    assert price_store_verdict(syms, gaps)[0] == "warn"
