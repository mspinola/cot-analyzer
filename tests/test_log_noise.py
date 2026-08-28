"""Scanner traffic stays out of the journal; the visitor DB stays the record.

Internet background noise (/.env probe sweeps answered 404, raw TLS and nmap
payloads answered 400, bot-flagged page loads) was most of what `journalctl -u
cot-analyzer` printed. Two changes, pinned here: werkzeug's echo of 400/404 lines is
filtered (`DropScannerNoise` in main), and the app's own "IP: ... | bot" line logs
at DEBUG, below the deployment's INFO threshold. Neither touches what is stored:
every bot still gets its visitor_logs row and the admin page's bot filter still
sees it, so suppression is a display decision, not a data one.
"""
import logging

import app_cot
import main

# ── werkzeug's echo of scanner requests ───────────────────────────────────────

def _passes(message, level=logging.INFO):
    record = logging.LogRecord('werkzeug', level, __file__, 0, message, None, None)
    return main.DropScannerNoise().filter(record)


def test_probe_404_access_lines_are_dropped():
    assert not _passes(
        '127.0.0.1 - - [28/Aug/2026 07:52:36] "GET /env/.env HTTP/1.1" 404 -')


def test_raw_payload_400_access_lines_are_dropped():
    """A TLS handshake or nmap probe sent to the plain HTTP port: werkzeug prints
    the bytes as the request line and answers 400."""
    assert not _passes(
        '47.95.209.20 - - [28/Aug/2026 08:01:27] '
        '"\\x16\\x03\\x01\\x02\\x00\\x01\\x00\\x01" 400 -')


def test_bad_request_error_lines_are_dropped():
    """The same probe logs twice; this is the ERROR half."""
    assert not _passes(
        "47.95.209.20 - - [28/Aug/2026 08:01:13] "
        "code 400, message Bad request version ('GetClassName\\x00\\x00')",
        level=logging.ERROR)


def test_php_cgi_exploit_405_lines_are_dropped():
    """CVE-2024-4577: `%AD` is a soft hyphen the Windows codepage folds into `-`, so
    the query string is `-d allow_url_include=1 -d auto_prepend_file=php://input`.
    It reaches a real route (`/`) with the wrong method, so it is a 405 rather than
    the 404 a nonexistent path would give."""
    assert not _passes(
        '127.0.0.1 - - [28/Aug/2026 12:35:49] '
        '"POST /?%ADd+allow_url_include%3d1+%ADd+auto_prepend_file%3dphp://input '
        'HTTP/1.1" 405 -')


def test_the_whole_4xx_range_is_dropped():
    """A code list would need extending for every new probe shape; the range does not."""
    for code in (401, 403, 405, 413, 429):
        assert not _passes(
            f'127.0.0.1 - - [28/Aug/2026 12:35:49] "GET / HTTP/1.1" {code} -')


def test_successful_requests_still_log():
    assert _passes(
        '127.0.0.1 - - [28/Aug/2026 08:19:12] "GET /heatmap HTTP/1.1" 200 -')


def test_server_errors_still_log():
    """Only client-error noise is dropped; a 500 is ours to see."""
    assert _passes(
        '127.0.0.1 - - [28/Aug/2026 08:19:12] '
        '"POST /_dash-update-component HTTP/1.1" 500 -')


def test_the_filter_is_installed_on_the_werkzeug_logger():
    assert any(isinstance(f, main.DropScannerNoise)
               for f in logging.getLogger('werkzeug').filters)


# ── the app's own visit line ──────────────────────────────────────────────────

class _StubLogger:
    def __init__(self):
        self.calls = []

    def info(self, msg):
        self.calls.append(('info', msg))

    def debug(self, msg):
        self.calls.append(('debug', msg))


def _visit(monkeypatch, user_agent):
    stub = _StubLogger()
    monkeypatch.setattr(app_cot.utils, 'cot_logger', stub)
    monkeypatch.setattr(app_cot, '_visit_worker_started', True)  # no thread
    with app_cot.app.server.test_request_context(
            '/', headers={'X-Forwarded-For': '8.8.8.8',
                          'User-Agent': user_agent}):
        app_cot._enqueue_visit('landing', '/')
    return stub.calls, app_cot._visit_queue.get_nowait()


def test_a_bot_visit_logs_at_debug_but_still_reaches_the_queue(monkeypatch):
    calls, row = _visit(monkeypatch, 'Mozilla/5.0 (compatible; AhrefsBot/7.0)')
    assert calls == [('debug', 'IP: 8.8.8.8 | Path: / | bot')]
    assert row['is_bot'] is True


def test_a_human_visit_still_logs_at_info(monkeypatch):
    calls, row = _visit(monkeypatch, 'Mozilla/5.0 (X11; Linux x86_64)')
    assert calls == [('info', 'IP: 8.8.8.8 | Path: /')]
    assert row['is_bot'] is False
