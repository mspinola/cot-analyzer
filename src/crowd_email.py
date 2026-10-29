"""The weekly email: the Crowdedness Board, as HTML an email client will render.

The email used to be the Signal Matrix (cotmetrics.weekly_email, the heatmap's
table). The board replaced it on 2026-10-29 when it became the landing page: the
email should be what a reader would see if they opened the site, and since then
that is the board.

It cannot BE the page. The page is a Plotly figure drawn by a browser, and an
email client runs no script, so this prints the same rows as a table. What keeps
the two from drifting apart is that nothing about WHAT is shown is decided here:

* the rows come from `pages.analytics.crowd.build_board`, the function the page's
  own callback calls, so the universe, the order, the tape-context block and the
  dropped-market list are one join;
* every cell's fill is `board_traces.cell_fill` and every ink is
  `plot_colors.cell_text_colour`, the functions the figure is coloured with, run
  against the same background;
* the line under the board is the page's own `caption`.

What IS decided here is only what an inbox forces:

* **Solid colours only.** Outlook on Windows renders with Word's engine, which
  drops rgba() and leaves a cell unfilled. Every translucent colour the page uses
  (the chips, the dimmed text) is composited onto the email's background first.
* **Inline styles and bgcolor attributes,** both, because Gmail strips some
  <style> blocks and some clients ignore one or the other.
* **Dark, like the page and like the Signal Matrix email it replaces.** A client
  in dark mode leaves an already-dark design alone; a light one would get
  inverted into colours nobody chose.
* **The 52-week path as block characters,** because no mainstream client renders
  inline SVG. Thirteen points (every fourth week) at eight heights is coarse, and
  it is labelled as a sketch, not a chart.
"""
import csv
import dataclasses
import io
import os
import urllib.parse
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils

import viz_config
import viz_constants as vc
from components import board_traces
from components.plot_colors import blend_over, cell_text_colour, grid_colors

BACKGROUND = vc.BACKGROUND_COLOR
#: The page's text colours, which are the Solarized cream pair: correct on the
#: email's background for the same reason they are on the page's.
TEXT = vc.TEXT_COLOR
BRIGHT = vc.BRIGHTER_TEXT_COLOR
#: What the page draws at 35% white, composited, because rgba is not an option.
DIM = blend_over("#ffffff", 0.35, BACKGROUND)
RULE = blend_over("#ffffff", 0.10, BACKGROUND)
CLASS_BAND = blend_over("#ffffff", board_traces.HEADER_BAND_ALPHA, BACKGROUND)

SPARK_LEVELS = "▁▂▃▄▅▆▇█"
SPARK_STEP = 4          # every fourth week of the trailing 52: 13 points

FONT = "Arial, Helvetica, sans-serif"
MONO = "Menlo, Consolas, monospace"


def _rgba_over(rgba, background=BACKGROUND):
    """'rgba(r, g, b, a)' composited onto `background`, as hex. A hex input passes
    through. The chips and near-tier inks arrive as rgba from the page's own
    helpers, and are flattened here rather than re-derived so that those helpers
    stay the one place their strengths are decided."""
    text = str(rgba).strip()
    if not text.startswith("rgba("):
        return text
    r, g, b, a = (part.strip() for part in text[5:-1].split(","))
    return blend_over("#{:02x}{:02x}{:02x}".format(int(r), int(g), int(b)),
                      float(a), background)


def sparkline(path):
    """The trailing-year index as block characters, or '' with too little of it."""
    points = [v for v in path[::-1][::SPARK_STEP][::-1] if v is not None]
    if len(points) < 2:
        return ""
    top = len(SPARK_LEVELS) - 1
    return "".join(SPARK_LEVELS[round(max(0.0, min(100.0, v)) / 100 * top)]
                   for v in points)


def _fmt(value):
    return "" if value is None else f"{value:.0f}"


def _move_text(move):
    if move is None:
        return ""
    if abs(move) <= board_traces.DELTA_FLAT:
        return f"&#9656; {move:+.0f}"            # flat: a neutral pointer
    return f"{'&#9650;' if move > 0 else '&#9660;'} {move:+.0f}"


# ── the table ────────────────────────────────────────────────────────────────

#: Gmail clips an HTML body past about 102 KB behind a "[Message clipped]" link,
#: and a clipped board is half a board. The first render, with these rules inline
#: on every cell, was 98 KB for this week's 43 markets: 73 KB of it repeated
#: style text. So everything a cell does NOT vary on is said once, here, and a
#: cell carries only its colours. The font is ALSO set on the table, because the
#: one notable client that strips <style> (the Gmail app on a non-Google account)
#: still honours inheritance, and there the board loses its rules and padding but
#: keeps every colour and every number. test_crowd_email pins the budget.
SIZE_BUDGET_BYTES = 90_000

_SHEET = f"""<style>
.b td,.b th{{font-family:{FONT};font-size:12px;padding:3px 6px;border-bottom:1px solid {RULE};}}
.b th{{font-size:10px;font-weight:bold;color:{TEXT};padding:4px 6px;}}
.b .y{{font-family:{MONO};font-size:11px;color:{TEXT};}}
.b .n{{color:{BRIGHT};white-space:nowrap;}}
.b .v{{font-weight:bold;min-width:30px;}}
.b .m{{white-space:nowrap;}}
.b .p{{color:{DIM};font-size:11px;letter-spacing:-1px;white-space:nowrap;}}
.b .k{{color:{TEXT};font-size:10px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;padding:6px 6px 4px;border-bottom:0;}}
.b .g{{height:8px;line-height:8px;font-size:0;border-bottom:0;}}
.b a{{color:{BRIGHT};text-decoration:none;}}
</style>"""


def _chip_cell(read, colors):
    chip = board_traces.verdict_chip(read.state, colors)
    if chip is None:
        return "<td></td>"
    label, fill, border, ink = chip
    fill, border, ink = (_rgba_over(c) for c in (fill, border, ink))
    return (f'<td class="m"><span style="display:inline-block;padding:1px 5px;'
            f'font-size:9px;font-weight:bold;background:{fill};'
            f'border:1px solid {border};color:{ink};border-radius:3px;">'
            f'{escape(label)}</span></td>')


def _value_cell(value, colors):
    fill = board_traces.cell_fill(value, colors, background=BACKGROUND)
    if fill is None:
        return f'<td align="center" style="color:{DIM};">&middot;</td>'
    ink = cell_text_colour(fill)
    return (f'<td align="center" class="v" bgcolor="{fill}" '
            f'style="background:{fill};color:{ink};">{_fmt(value)}</td>')


def _market_row(read, colors, base_url):
    tag = board_traces.since_tag(read)
    name = escape(read.asset)
    if read.linked and base_url:
        # The detail page every board click opens on the site, encoded the way
        # app_utils.clicked_market_href encodes it there.
        href = escape(f"{base_url}/oi_alignment?asset={urllib.parse.quote(read.asset)}",
                      quote=True)
        # The link colour rides inline too: some clients paint links blue over any
        # stylesheet, and blue on this background is the one illegible choice.
        name = f'<a href="{href}" style="color:{BRIGHT};">{name}</a>'
    since = (f' <span style="color:{DIM};font-size:10px;">{escape(tag)}</span>'
             if tag else "")
    move_ink = _rgba_over(board_traces.delta_colour(read.move, colors))
    cells = "".join(_value_cell(v, colors) for v in read.windows)
    return (
        "<tr>"
        f"{_chip_cell(read, colors)}"
        f'<td class="y">{escape(read.symbol or "")}</td>'
        f'<td class="n">{name}{since}</td>'
        f"{cells}"
        f'<td align="right" class="m" style="color:{move_ink};">'
        f"{_move_text(read.move)}</td>"
        f'<td class="p">{sparkline(read.path)}</td>'
        "</tr>"
    )


def _class_row(label):
    return (f'<tr><td colspan="9" class="k" bgcolor="{CLASS_BAND}" '
            f'style="background:{CLASS_BAND};">{escape(label)}</td></tr>')


def _spacer_row():
    return '<tr><td colspan="9" class="g">&nbsp;</td></tr>'


def _header_row():
    labels = "".join(f'<th align="center">{label}</th>'
                     for label in board_traces.WINDOW_LABELS)
    return (f'<tr><th></th><th></th><th align="left">Market</th>{labels}'
            f'<th align="right">{const.MOMENTUM_PERIOD}W</th>'
            f'<th align="left">52w path</th></tr>')


def pretty_date(report_date):
    try:
        return datetime.strptime(report_date, "%Y-%m-%d").strftime("%B %d, %Y")
    except (TypeError, ValueError):
        return "an unknown date"


def subject(report_date):
    return f"📊 COT Crowdedness Board: {report_date}"


@dataclasses.dataclass(frozen=True)
class Edition:
    """One week's email, everything about it that is the same for every reader.

    Built once per send and handed to every recipient, so the operator copy and
    each subscriber's are the same board by construction rather than by each
    rebuilding it and hoping the store did not move in between. It is also the
    seam the tests stub: a value, so no stub can accept a call the real code
    would refuse (test_subscribers records the 2026-09-12 fan-out failure a
    permissive stub hid).
    """
    board: board_traces.Board
    model: object      # cotmetrics.models model
    colors: object     # plot_colors.GridColors
    caption: str       # the page's own caption for this board

    @property
    def report_date(self):
        return self.board.report_date


def render_html(edition, base_url, unsubscribe_url=None):
    """The whole email body for one reader. Only the unsubscribe link differs."""
    board, model, colors = edition.board, edition.model, edition.colors
    body = []
    for row in board.rows:
        if row.kind == "class":
            body.append(_class_row(row.label))
        elif row.kind == "spacer":
            body.append(_spacer_row())
        else:
            body.append(_market_row(row.read, colors, base_url))

    live = f"{base_url}/?date={board.report_date}" if base_url else None
    link = (f'<a href="{escape(live, quote=True)}" style="color:{BRIGHT};">'
            f"Open this week's board on the site</a>" if live else "")
    p = f"font-family:{FONT};font-size:12px;line-height:1.5;color:{TEXT};margin:0 0 10px;"
    legend = (
        f"Each cell is the range index of Commercial positioning within its own "
        f"window: 0 at the window's low, 100 at its high, over 13, 26 and 52 weekly "
        f"reports and the market's full history. A short window says where this "
        f"week sits in the RECENT range, not whether the market is net long. "
        f"SETUP and NEAR are {escape(model.title)}'s verdict. "
        f"The {const.MOMENTUM_PERIOD}W column is the change in the 12M index; the "
        f"path is a sketch of that index over the trailing year, one mark per four "
        f"weeks. The tape-context rows at the bottom are ETF ratios, not positioning."
    )
    # Inside the body, on the board's own background, rather than the separate
    # trailing MIME part the Signal Matrix carried it in: some clients show a
    # trailing html part as a "noname.html" attachment, and a text-only reader
    # never saw it at all.
    footer = ""
    if unsubscribe_url:
        footer = (f'<p style="{p}color:{DIM};font-size:11px;">You are receiving this '
                  f"because you subscribed at {escape(base_url or '')}. "
                  f'<a href="{escape(unsubscribe_url, quote=True)}" '
                  f'style="color:{DIM};">Unsubscribe</a>.</p>')
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
{_SHEET}
</head>
<body bgcolor="{BACKGROUND}" style="margin:0;padding:0;background:{BACKGROUND};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BACKGROUND}" style="background:{BACKGROUND};">
<tr><td align="center" style="padding:16px 8px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="max-width:760px;width:100%;">
<tr><td style="padding:0 6px 4px;">
<div style="font-family:{FONT};font-size:20px;font-weight:bold;color:{BRIGHT};">COT Crowdedness Board</div>
<div style="font-family:{FONT};font-size:12px;color:{TEXT};padding-top:2px;">Tuesday {pretty_date(board.report_date)} &middot; {escape(model.title)}</div>
</td></tr>
<tr><td style="padding:10px 0 0;">
<table class="b" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;font-family:{FONT};font-size:12px;color:{TEXT};">
{_header_row()}
{''.join(body)}
</table>
</td></tr>
<tr><td style="padding:14px 6px 0;">
<p style="{p}">{escape(edition.caption)}</p>
<p style="{p}">{legend}</p>
<p style="{p}">{link}</p>
{footer}
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def render_text(edition, base_url, unsubscribe_url=None):
    """The plain-text alternative. A real one rather than "enable HTML": it is what
    a screen reader or a text-only client gets, and spam filters weigh its absence."""
    board, model = edition.board, edition.model
    lines = [f"COT Crowdedness Board, Tuesday {pretty_date(board.report_date)}",
             f"{model.title}", ""]
    labels = " ".join(f"{label:>4}" for label in board_traces.WINDOW_LABELS)
    for row in board.rows:
        if row.kind == "class":
            lines += ["", row.label.upper(),
                      f"{'':6} {'':24} {labels}  {const.MOMENTUM_PERIOD}W"]
        elif row.kind == "market":
            r = row.read
            cells = " ".join(f"{_fmt(v) or '-':>4}" for v in r.windows)
            move = "" if r.move is None else f"{r.move:+.0f}"
            chip = board_traces.STATE_LABELS.get(r.state, "")
            lines.append(f"{(r.symbol or '')[:6]:6} {r.asset[:24]:24} {cells}  "
                         f"{move:>4}  {chip}".rstrip())
    lines += ["", edition.caption]
    if base_url:
        lines += ["", f"Open this week's board: {base_url}/?date={board.report_date}"]
    if unsubscribe_url:
        lines += ["", f"Unsubscribe: {unsubscribe_url}"]
    return "\n".join(lines) + "\n"


def board_csv(board):
    """The board's own rows as CSV, replacing the Signal Matrix's. A reader who
    loads the attachment into a sheet gets the numbers the table printed."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["asset_class", "symbol", "market", *board_traces.WINDOW_LABELS,
                     f"change_{const.MOMENTUM_PERIOD}w", "setup", "date"])
    for row in board.rows:
        if row.kind != "market":
            continue
        r = row.read
        writer.writerow([row.asset_class, r.symbol, r.asset,
                         *("" if v is None else round(v, 1) for v in r.windows),
                         "" if r.move is None else round(r.move, 1),
                         "" if r.state == const.SETUP_NONE else r.state, r.date])
    return out.getvalue().encode("utf-8")


# ── assembling and sending ───────────────────────────────────────────────────

class EmptyBoard(RuntimeError):
    """The matrix had nothing for this week, so there is no board to send."""


def current_edition(model=None):
    """This week's edition: every asset class, in the page's default order, with
    the model and colours the page opens on. Raises EmptyBoard rather than
    returning a board with no markets on it.

    The page module is imported here, not at the top: it registers itself with
    Dash on import, which needs the app to exist, and every caller of this runs in
    the app's process after it does (the store poller, the admin button).
    """
    from cotmetrics.indexer import get_indexer

    from pages.analytics.crowd import build_board
    from pages.analytics.crowd import caption as page_caption

    model = model or models.DEFAULT_MODEL
    board = build_board(get_indexer().get_asset_classes(), model,
                        board_traces.ORDER_CLASS)
    if board is None or not board.reads:
        raise EmptyBoard("the board has no markets this week")
    return Edition(
        board=board, model=model,
        colors=grid_colors(viz_config.get_palette(None)),
        caption=page_caption(board.report_date, model, board.skipped,
                             awaiting=board.awaiting, stale=board.stale),
    )


def build_message(edition, sender, receiver, base_url, unsubscribe_url=None):
    """The multipart message for one recipient: text and HTML alternatives, then
    the CSV. `unsubscribe_url` is a subscriber's own link; the operator copy has
    none."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject(edition.report_date)
    msg["From"] = sender
    msg["To"] = receiver
    if unsubscribe_url:
        # Mail clients put their own Unsubscribe button on a message carrying
        # this, and Gmail and Yahoo weigh its absence against a sender. Without
        # List-Unsubscribe-Post: that one-click form needs /unsubscribe to accept
        # a POST, and today it answers a GET.
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(render_text(edition, base_url, unsubscribe_url),
                        "plain", "utf-8"))
    alt.attach(MIMEText(render_html(edition, base_url, unsubscribe_url),
                        "html", "utf-8"))
    msg.attach(alt)
    name = f"cot_crowd_board_{edition.report_date}.csv"
    part = MIMEApplication(board_csv(edition.board), Name=name)
    part["Content-Disposition"] = f'attachment; filename="{name}"'
    msg.attach(part)
    return msg


def send_operator_copy(env=None, smtp_factory=None, edition=None):
    """Mail this week's board to RECEIVER_EMAIL_USER. Returns the report date.

    Raises on failure, and that is the contract the weekly ledger depends on: an
    exception means "not sent, retry next poll". An empty board raises too
    (EmptyBoard, from current_edition) rather than mailing an empty table, which
    differs from the Signal Matrix sender (it mailed the empty table as a visible
    symptom). Here the ledger retries, so the symptom is a log line every poll
    until the data arrives, and nobody is mailed a board with no markets on it.
    """
    from cotmetrics.weekly_email import email_config

    import subscribers

    sender, receiver, password = email_config(env)
    edition = edition or current_edition()
    msg = build_message(edition, sender, receiver, subscribers.base_url(env))
    server = subscribers._smtp(env, smtp_factory)
    try:
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())
    finally:
        server.quit()
    utils.cot_logger.info(
        f"weekly email: sent the {edition.report_date} Crowdedness Board "
        f"({len(edition.board.reads)} markets) to {receiver}.")
    return edition.report_date


def preview_html(path=None):
    """Write this week's email body to a file, for looking at it without a send.

    From src/, in an environment with the stores set, after importing app_cot
    (which builds the Dash app the page module needs). Returns the path.
    """
    import subscribers

    edition = current_edition()
    path = path or os.path.join(os.getcwd(),
                                f"crowd_email_{edition.report_date}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(edition, subscribers.base_url(),
                            unsubscribe_url=f"{subscribers.base_url()}/unsubscribe?token=PREVIEW"))
    return path
