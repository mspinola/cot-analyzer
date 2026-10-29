"""The weekly email: the board's own rows, in colours an inbox will keep.

What these pin, in order of what would go wrong silently:

* the cell colours ARE the page's (board_traces.cell_fill against the same
  background), so the email cannot drift from the board it claims to be;
* there is no rgba() anywhere, because Outlook's renderer drops it and leaves a
  cell unfilled with nothing to say so;
* a large universe stays under Gmail's clipping line, past which a reader gets
  half a board and a "[Message clipped]" link;
* a subscriber's unsubscribe link is in the HTML, in the text part, and in the
  List-Unsubscribe header, and the operator copy carries none.

Store-free and page-free: the board is built from MarketReads with
board_traces.build_rows, the same function the page's build_board calls.
"""
import email
import email.header

import cotmetrics.constants as const

import crowd_email
from components import board_traces
from components.plot_colors import GridColors, cell_text_colour

COLORS = GridColors(bull="#2ecc71", bear="#ff4d4d",
                    bull_near="rgba(46, 204, 113, 0.5)",
                    bear_near="rgba(255, 77, 77, 0.5)")


def _read(asset, windows, asset_class="Metals", state=const.SETUP_NONE, move=12.0,
          symbol="GC"):
    return board_traces.MarketRead(
        asset=asset, asset_class=asset_class, windows=windows, symbol=symbol,
        history_weeks=1500, start="1986-01-14", move=move,
        path=tuple(float(i % 101) for i in range(52)), state=state,
        date="2026-10-20")


def _edition(reads, caption="Caption for the week."):
    rows, skipped = board_traces.build_rows(reads)
    board = board_traces.Board(rows=rows, report_date="2026-10-20", skipped=skipped,
                               awaiting=[], stale=[], reads=reads)

    class Model:
        title = "Raw 3-leg 95/5"
    return crowd_email.Edition(board=board, model=Model(), colors=COLORS,
                               caption=caption)


EDITION = _edition([
    _read("Gold", (95.0, 82.0, 82.0, 49.0), state=const.SETUP_BULL),
    _read("Silver", (4.0, 4.0, 4.0, 30.0), state=const.SETUP_NEAR_BEAR, move=-27.0,
          symbol="SI"),
    _read("Copper", (50.0, None, 61.0, 66.0), move=0.0, symbol="HG"),
    _read("Corn", (34.0, 34.0, 20.0, 15.0), asset_class="Grains", symbol="ZC"),
])
BASE = "https://example.test"


def test_every_cell_is_coloured_by_the_pages_own_rule():
    html = crowd_email.render_html(EDITION, BASE)
    for read in EDITION.board.reads:
        for value in read.windows:
            if value is None:
                continue
            fill = board_traces.cell_fill(value, COLORS,
                                          background=crowd_email.BACKGROUND)
            ink = cell_text_colour(fill)
            assert (f'bgcolor="{fill}" style="background:{fill};color:{ink};">'
                    f"{value:.0f}</td>") in html, (read.asset, value)


def test_no_colour_is_left_translucent():
    """Outlook on Windows drops rgba() and draws nothing in its place. The chips
    and the near-tier inks arrive as rgba from the page's helpers, so this is the
    test that the flattening actually ran on every one of them."""
    html = crowd_email.render_html(EDITION, BASE, unsubscribe_url=f"{BASE}/u")
    assert "rgba(" not in html


def test_the_chips_say_what_the_page_says():
    html = crowd_email.render_html(EDITION, BASE)
    assert ">SETUP</span>" in html and ">NEAR</span>" in html


def test_a_large_universe_stays_under_gmails_clipping_line():
    """Gmail clips an HTML body past ~102 KB. The first render of this email was
    98 KB for 43 markets, one universe expansion from clipping, before the
    constant styles moved to a sheet; after, 39 KB.

    The bar is TWICE today's universe (params.yaml names 47 markets) with 12 KB
    to spare. It is not open-ended: a row costs ~770 bytes, so somewhere past
    ~115 markets this fails, and that failure is the signal to split the email
    or drop a column, not to raise the budget."""
    reads = [_read(f"Market {i}", (float(i % 100), 50.0, 99.0, 1.0),
                   asset_class=f"Class {i % 9}",
                   state=const.SETUP_BULL if i % 7 == 0 else const.SETUP_NONE)
             for i in range(2 * 47)]
    html = crowd_email.render_html(_edition(reads), BASE, unsubscribe_url=f"{BASE}/u")
    assert len(html.encode("utf-8")) < crowd_email.SIZE_BUDGET_BYTES


def test_a_subscriber_can_leave_from_every_part_of_the_message():
    url = f"{BASE}/unsubscribe?token=tok123"
    msg = crowd_email.build_message(EDITION, "from@x.test", "to@x.test", BASE,
                                    unsubscribe_url=url)
    assert msg["List-Unsubscribe"] == f"<{url}>"
    parsed = email.message_from_string(msg.as_string())
    bodies = {part.get_content_type(): part.get_payload(decode=True).decode()
              for part in parsed.walk()
              if part.get_content_type() in ("text/plain", "text/html")}
    assert url in bodies["text/plain"]
    assert url in bodies["text/html"]


def test_the_operator_copy_carries_no_unsubscribe_link():
    msg = crowd_email.build_message(EDITION, "from@x.test", "op@x.test", BASE)
    assert msg["List-Unsubscribe"] is None
    assert "unsubscribe" not in msg.as_string().lower()


def test_the_subject_names_the_week_and_the_board():
    msg = crowd_email.build_message(EDITION, "from@x.test", "op@x.test", BASE)
    assert msg["Subject"] == "📊 COT Crowdedness Board: 2026-10-20"


def test_the_csv_is_the_boards_rows():
    rows = crowd_email.board_csv(EDITION.board).decode().splitlines()
    assert rows[0].startswith("asset_class,symbol,market,3M,6M,12M,Full,")
    assert len(rows) == 1 + len(EDITION.board.reads)
    # An empty window is an empty field, not "None" or a zero.
    copper = next(r for r in rows if ",Copper," in r)
    assert ",50.0,,61.0,66.0," in copper


def test_every_market_links_to_its_detail_page_encoded_like_the_site():
    html = crowd_email.render_html(_edition([_read("S&P 500", (50.0,) * 4)]), BASE)
    assert 'href="https://example.test/oi_alignment?asset=S%26P%20500"' in html
    # And the name itself is escaped where it is printed.
    assert ">S&amp;P 500</a>" in html


def test_the_text_part_is_a_real_alternative():
    text = crowd_email.render_text(EDITION, BASE)
    assert "Gold" in text and "  95   82   82   49" in text
    assert "SETUP" in text and "NEAR" in text
    assert f"{BASE}/?date=2026-10-20" in text


def test_every_path_image_is_embedded_and_referenced_by_its_content_id():
    """The paths ride as CID parts of a multipart/related, which is what lets a
    client show them with no "display images" click and no fetch. Each market row
    gets one, each is referenced from the HTML by the id it carries, and each is a
    PNG."""
    msg = crowd_email.build_message(EDITION, "from@x.test", "to@x.test", BASE)
    parsed = email.message_from_string(msg.as_string())
    related = next(p for p in parsed.walk()
                   if p.get_content_type() == "multipart/related")
    html = next(p for p in related.walk() if p.get_content_type() == "text/html")
    html = html.get_payload(decode=True).decode()
    images = [p for p in related.walk() if p.get_content_type() == "image/png"]

    markets = [r for r in EDITION.board.rows if r.kind == "market"]
    assert len(images) == len(markets)
    for image in images:
        cid = image["Content-ID"].strip("<>")
        assert f'src="cid:{cid}"' in html
        assert image.get_payload(decode=True)[:8] == b"\x89PNG\r\n\x1a\n"
        assert image.get_content_disposition() == "inline"


def test_a_path_is_drawn_once_per_edition_not_once_per_reader(monkeypatch):
    """Every subscriber's message carries the same images; drawing them again
    for each recipient would be N times the work for the same bytes."""
    edition = _edition([_read("Gold", (95.0, 82.0, 82.0, 49.0))])
    calls = []
    real = crowd_email.spark_png.spark_png
    monkeypatch.setattr(crowd_email.spark_png, "spark_png",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    for to in ("a@x.test", "b@x.test", "c@x.test"):
        crowd_email.build_message(edition, "from@x.test", to, BASE)
    assert len(calls) == 1


def test_send_operator_copy_mails_the_edition_to_the_receiver():
    class SMTP:
        sent = []

        def login(self, *a):
            pass

        def sendmail(self, sender, to, message):
            self.sent.append((to, message))

        def quit(self):
            pass

    smtp = SMTP()
    env = {"EMAIL_USER": "from@x.test", "RECEIVER_EMAIL_USER": "op@x.test",
           "EMAIL_PASSWORD": "pw"}
    date = crowd_email.send_operator_copy(env=env, smtp_factory=lambda: smtp,
                                          edition=EDITION)
    assert date == "2026-10-20"
    (to, message), = smtp.sent
    assert to == "op@x.test"
    # Decoded, because the emoji makes the wire form RFC 2047 (=?utf-8?b?...?=).
    subject = str(email.header.make_header(
        email.header.decode_header(email.message_from_string(message)["Subject"])))
    assert subject == "📊 COT Crowdedness Board: 2026-10-20"
