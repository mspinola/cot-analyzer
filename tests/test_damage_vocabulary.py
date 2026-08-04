"""No crowdmon vocabulary may be written down in this repo.

This is the structural guard that makes the damage page's design honest rather than merely
intended. The page renders `crowdmon`'s output without importing `crowdmon`, and everything
it needs to render is carried in the artifact's manifest, generated from that package's live
constants at publish time. The moment a state name or a quadrant label is typed out HERE, a
living document has a copy in the repo with the weakest guards and nothing checking it.

That failure has a history on the producer's side, which is why they asked for this. crowdmon
lost 104 lines of a duplicated spec for a day and found it only through an unrelated diff,
and it ships a test whose whole purpose is that a caveat its README states and its brief
omits is omitted *silently* while the brief still reads complete. Their ADR-0001 names this
grep as the one obligation it places on a consumer.

The strings below are deliberately assembled from fragments so that this file does not itself
become the copy it exists to prevent: a reader looking for the literal `"no_crowding"` in
this repo finds it in neither the page nor here.
"""
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

#: The modules that touch the artifact. Anything they render must have come from it.
GUARDED = (SRC / "pages" / "analytics" / "damage.py",
           SRC / "components" / "crowdmon_artifact.py")

#: Assembled rather than written, per the docstring. Each pair is (prefix, suffix) of a
#: crowdmon enum value or label whose home is that package's constants.
FRAGMENTS = (
    # composite.SCORE_STATES
    ("war", "mup"), ("no_", "crowding"), ("no_", "illiquidity"), ("no_", "fragility"),
    # composite.UNWIND_STATES
    ("mid_", "exit"), ("falling_", "not_exit"), ("not_", "falling"),
    ("indeter", "minate"),
    # stratum.STRATA
    ("out", "right"), ("certi", "ficate"), ("differ", "ential"),
    # report.QUADRANT, the phrases that carry the reading
    ("CLOSE and ", "SEVERE"), ("close but not ", "severe"),
    ("severe but not ", "close"), ("neither close nor ", "severe"),
    # report.DAMAGE_BANDS
    ("top ", "decile"), ("above ", "middling"), ("bottom ", "quartile"),
)


@pytest.mark.parametrize("prefix,suffix", FRAGMENTS,
                         ids=lambda v: v if isinstance(v, str) else str(v))
def test_no_crowdmon_vocabulary_is_written_down_here(prefix, suffix):
    needle = prefix + suffix
    for path in GUARDED:
        body = path.read_text(encoding="utf-8")
        assert needle not in body, (
            "{} contains the crowdmon value {!r}. Read it from the artifact manifest "
            "instead: `vocabulary`, `quadrant`, `damage_bands` and `notes` are all "
            "published for exactly this reason. A copy here is a copy of a living "
            "document in the repo with the weakest guards.".format(path.name, needle))


def test_the_guard_is_still_pointed_at_something():
    """A grep that stops seeing its target passes forever."""
    for path in GUARDED:
        assert path.exists(), "{} moved; this guard is now vacuous".format(path)
        assert len(path.read_text(encoding="utf-8")) > 1000


def test_the_severity_threshold_is_read_and_not_hard_coded():
    """`0.75` is crowdmon's severity floor and belongs in the artifact, not in a chart.

    Checked separately from the string fragments because a number cannot be split into
    fragments convincingly, and because this is the one that would be easiest to type in
    while drawing a reference line.
    """
    body = (SRC / "pages" / "analytics" / "damage.py").read_text(encoding="utf-8")
    lines = [ln for ln in body.splitlines()
             if "0.75" in ln and not ln.strip().startswith("#")]
    assert len(lines) <= 1, (
        "0.75 appears {} times outside comments in damage.py. It is crowdmon's severity "
        "floor and should be derived from the manifest's `damage_bands`; the single "
        "permitted occurrence is the fallback in `_severe_floor`.".format(len(lines)))
