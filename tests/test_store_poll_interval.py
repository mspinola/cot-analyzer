"""The store poller tightens to 30s while the Friday release is landing.

The always-on 5-minute baseline is the safety net (the replica can move at any
time); the Friday window only shortens the wait for the one event whose timing is
known. Pinned here: the window's edges, that other weekdays keep the baseline, that
a sleep begun just before the window cannot carry past its start, and that the
window is Eastern whatever zone `now` arrives in.
"""
import datetime
import zoneinfo

import pytest

import main

ET = main.EASTERN
FRI = datetime.date(2026, 9, 25)   # a Friday
THU = datetime.date(2026, 9, 24)


def _at(day, hh, mm, ss=0, tz=ET):
    return datetime.datetime.combine(day, datetime.time(hh, mm, ss), tz)


@pytest.mark.parametrize("hh,mm", [(15, 25), (15, 30), (16, 0), (16, 29)])
def test_inside_the_friday_window_polls_fast(hh, mm):
    assert main.seconds_until_next_poll(_at(FRI, hh, mm)) == main.RELEASE_POLL_SECONDS


@pytest.mark.parametrize("hh,mm", [(16, 30), (18, 0), (9, 0)])
def test_outside_the_friday_window_keeps_the_baseline(hh, mm):
    assert main.seconds_until_next_poll(_at(FRI, hh, mm)) == main.STORE_POLL_SECONDS


@pytest.mark.parametrize("day", [THU, FRI + datetime.timedelta(days=1)])
def test_other_days_keep_the_baseline_even_at_release_time(day):
    assert main.seconds_until_next_poll(_at(day, 15, 30)) == main.STORE_POLL_SECONDS


def test_a_sleep_begun_before_the_window_ends_at_its_start():
    # 15:24:00 -> 60s, not 300s: the first fast tick is 15:25, not 15:29.
    assert main.seconds_until_next_poll(_at(FRI, 15, 24)) == 60
    assert main.seconds_until_next_poll(_at(FRI, 15, 24, 59)) == 1
    # Far enough out, the baseline is the shorter of the two.
    assert main.seconds_until_next_poll(_at(FRI, 15, 0)) == main.STORE_POLL_SECONDS


def test_the_window_is_eastern_whatever_zone_now_is_in():
    # 19:30 UTC in September is 15:30 EDT: inside. The server runs on New York time
    # today, but the window must not depend on that.
    utc = datetime.datetime(2026, 9, 25, 19, 30, tzinfo=zoneinfo.ZoneInfo("UTC"))
    assert main.seconds_until_next_poll(utc) == main.RELEASE_POLL_SECONDS
    # And in winter (EST, UTC-5) 20:30 UTC is 15:30 ET.
    winter = datetime.datetime(2026, 12, 4, 20, 30, tzinfo=zoneinfo.ZoneInfo("UTC"))
    assert main.seconds_until_next_poll(winter) == main.RELEASE_POLL_SECONDS
