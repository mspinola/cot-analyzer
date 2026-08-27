"""The pure half of visitor tracking: ip parsing, bot classification, visitor ids."""
from visitors import client_ip, is_bot, visitor_id

# ── client_ip ─────────────────────────────────────────────────────────────────

def test_the_first_forwarded_entry_is_the_client():
    """X-Forwarded-For is a chain once any second proxy is involved; the client is
    the first entry, and storing the whole header split identity by route."""
    assert client_ip('34.95.46.6, 10.0.0.1, 10.0.0.2', '127.0.0.1') == '34.95.46.6'


def test_a_single_forwarded_entry_is_stripped():
    assert client_ip('  34.95.46.6  ', '127.0.0.1') == '34.95.46.6'


def test_no_forwarding_falls_back_to_the_socket_peer():
    assert client_ip(None, '192.168.1.9') == '192.168.1.9'
    assert client_ip('', '192.168.1.9') == '192.168.1.9'


def test_nothing_at_all_is_empty_not_none():
    """'' keys the Internal/Local branch downstream; None would format as 'None'."""
    assert client_ip(None, None) == ''


# ── is_bot ────────────────────────────────────────────────────────────────────

def test_browsers_are_human():
    assert not is_bot('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def test_the_usual_automation_is_flagged():
    for ua in ['Googlebot/2.1 (+http://www.google.com/bot.html)',
               'curl/8.4.0',
               'python-requests/2.32.0',
               'Go-http-client/1.1',
               'Mozilla/5.0 (compatible; AhrefsBot/7.0)',
               'HeadlessChrome/126.0']:
        assert is_bot(ua), ua


def test_an_empty_user_agent_is_a_bot():
    """Every browser sends one; the traffic without one is scripts and scanners."""
    assert is_bot('')
    assert is_bot(None)


# ── visitor_id ────────────────────────────────────────────────────────────────

def test_same_visitor_same_day_is_one_id():
    a = visitor_id('1.2.3.4', 'Mozilla/5.0', day='2026-08-27')
    b = visitor_id('1.2.3.4', 'Mozilla/5.0', day='2026-08-27')
    assert a == b


def test_the_id_rotates_daily():
    """The rotation is the privacy property: within a day it counts uniques, across
    days it cannot accumulate into a profile."""
    a = visitor_id('1.2.3.4', 'Mozilla/5.0', day='2026-08-27')
    b = visitor_id('1.2.3.4', 'Mozilla/5.0', day='2026-08-28')
    assert a != b


def test_different_visitors_get_different_ids():
    base = visitor_id('1.2.3.4', 'Mozilla/5.0', day='2026-08-27')
    assert visitor_id('1.2.3.5', 'Mozilla/5.0', day='2026-08-27') != base
    assert visitor_id('1.2.3.4', 'Safari/605.1', day='2026-08-27') != base


def test_the_id_is_short_hex():
    vid = visitor_id('1.2.3.4', 'Mozilla/5.0', day='2026-08-27')
    assert len(vid) == 16
    assert int(vid, 16) >= 0


def test_today_is_the_default_day():
    assert visitor_id('1.2.3.4', 'ua') == visitor_id('1.2.3.4', 'ua')
