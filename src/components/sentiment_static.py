"""The sentiment page as one self-contained HTML file, published at surveys.bluemagicai.com.

The app's `/sentiment` page stays local-only (`local_pages`): the published copy is this
file, rendered from the same read and the same two figures, and pushed to its own GitHub
Pages repo by dbmf-tracker's `deploy/publish_pages.py --key surveys`, the way the DBMF,
AHLT and ORR monitors are (docs/surveys-publishing.md). Publishing NAAIM's and AAII's history was cleared against
their terms by the operator on 2026-11-09; the app's gate is unchanged, because the
deployed app is not where the publication happens.

What the static page keeps from the app, and how:

- **Both lookbacks.** The 1Y/3Y toggle redrew the charts server-side. Here every
  lookback's figures, summary and notes are embedded, and the toggle swaps them with
  `Plotly.react`; the figures carry the page's `uirevision`, so a zoom survives a flip.
- **The y-axis re-fit on zoom.** The app's own `clientside.js` is inlined and its
  `autoscale_y_axes` is called on every `plotly_relayout`, exactly as the Dash
  clientside callback calls it, so the published page cannot fit its axes by a
  different rule than the app does. It finds the plot as `#<id> .js-plotly-plot`, which
  is why each chart is drawn inside a wrapper carrying the id.
- **Not the PNG export.** It leans on html2canvas and the app's theme container; a
  reader of a static page has the browser's own screenshot.

The figures are serialized by plotly.py and drawn by the plotly.js release it bundles,
loaded from Plotly's CDN rather than inlined (about 4.6 MB). The version is read from the
installed plotly.py at render time (`plotly_js_url`), never pinned here: the JSON a
plotly.py writes is the format its own bundled plotly.js reads, and the CI resolver and
the publishing venv do not install the same plotly.py.

`generated_at` is written as `"generated_at":"..."` on purpose: publish_pages masks that
exact spelling when deciding whether anything changed, so a rebuild with no new data
pushes nothing.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import plotly.offline

import viz_constants as vc
from components import aaii_votes, sentiment


def plotly_js_url():
    """The CDN build of the plotly.js the installed plotly.py bundles."""
    return f"https://cdn.plot.ly/plotly-{plotly.offline.get_plotlyjs_version()}.min.js"


CLIENTSIDE_JS = Path(__file__).resolve().parent.parent / "assets" / "clientside.js"

TITLE = "Surveys, NAAIM and AAII"
DESCRIPTION = ("NAAIM exposure and AAII bulls minus bears against SPY, weekly, "
               "as range indexes with SPY's drawdowns behind them.")
HOME = "https://bluemagicai.com/"
#: The monitor row the DBMF, AHLT and ORR pages carry, with this page marked current.
SITES = (("DBMF", "https://dbmf.bluemagicai.com/"),
         ("AHLT", "https://ahlt.bluemagicai.com/"),
         ("ORR", "https://orr.bluemagicai.com/"),
         ("Surveys", "https://surveys.bluemagicai.com/"))
CURRENT = "Surveys"
SOURCES = ("Sources: NAAIM Exposure Index (naaim.org), AAII Sentiment Survey (aaii.com), "
           "SPY total return, CFTC Commitments of Traders (S&P 500 consolidated).")

#: Zoom buttons left off below 600px, where the full ladder (3M to Max, nine buttons) runs
#: past the plot's left edge and over the panel title. Seven fit, as the page had before
#: 3M and 6M were added; 2Y and 15Y sit between neighbours a phone reader can still pick.
PHONE_HIDDEN_RANGES = ("2Y", "15Y")
PHONE_QUERY = "(max-width: 600px)"

PRICE_ID = "price"
COLUMNS_ID = "columns"
VOTES_ID = "votes"
#: The payload key for the AAII votes figure, beside the lookback keys: the card does not
#: depend on the lookback, so it is embedded once and drawn once.
VOTES_KEY = "votes"


def lookback_payload(read, colors, palette):
    """Everything one lookback draws, as JSON-ready values."""
    return {
        "price": json.loads(sentiment.price_sentiment_figure(read, colors, palette).to_json()),
        "columns": json.loads(sentiment.columns_figure(read, colors, palette).to_json()),
        "summary": sentiment.summary(read) or "",
        "caption": sentiment.caption(read, local=False),
    }


def _script_json(value):
    """JSON safe inside a <script> element: no `</` can close it early."""
    return json.dumps(value, separators=(",", ":")).replace("</", "<\\/")


def _nav():
    links = []
    for name, url in SITES:
        current = ' aria-current="page"' if name == CURRENT else ""
        links.append(f'<a href="{url}"{current}>{name}</a>')
    return ('<nav class="sites" aria-label="Monitors"><span class="sep">Monitors</span>'
            + "".join(links)
            + f'<a class="home" href="{HOME}">COT Analyzer &rarr;</a></nav>')


def render(reads, colors, palette, generated_at=None, clientside_js=None, votes=None):
    """The page for `reads`, a {lookback years: SentimentRead} with the default included,
    and `votes` (`aaii_votes.read()`), whose card is left out when it is None.

    Raises ValueError when the default lookback is missing or any read is empty, so a
    failed store read stops the publish rather than putting an empty page up.
    """
    if sentiment.DEFAULT_LOOKBACK not in reads:
        raise ValueError(f"no read for the default lookback ({sentiment.DEFAULT_LOOKBACK}y)")
    for years, read in reads.items():
        if read.frame.empty:
            raise ValueError(f"the {years}y read is empty (awaiting {', '.join(read.awaiting)})")
    payload = {str(y): lookback_payload(r, colors, palette) for y, r in sorted(reads.items())}
    if votes is not None:
        payload[VOTES_KEY] = json.loads(aaii_votes.figure(votes, colors).to_json())
    default = payload[str(sentiment.DEFAULT_LOOKBACK)]
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    js = clientside_js if clientside_js is not None else CLIENTSIDE_JS.read_text(encoding="utf-8")
    esc = html.escape

    pressed = {y: "true" if y == sentiment.DEFAULT_LOOKBACK else "false" for y in reads}
    buttons = "".join(f'<button type="button" data-years="{y}" aria-pressed="{pressed[y]}">'
                      f'{y}Y</button>' for y in sorted(reads))
    notes = "".join(f"<p>{esc(p)}</p>" for p in default["caption"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(TITLE)}</title>
<meta name="description" content="{esc(DESCRIPTION)}">
<style>
:root {{ --page: {vc.BACKGROUND_COLOR}; --ink: {vc.BRIGHTER_TEXT_COLOR}; --ink-2: {vc.TEXT_COLOR};
  --muted: #7d8794; --line: rgba(255,255,255,0.10); --surface: rgba(28,28,28,0.55);
  --wash: rgba(255,255,255,0.06); --accent: {vc.BLUE_BACKGROUND};
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
html, body {{ background: var(--page); color: var(--ink-2); margin: 0; font-family: var(--sans); }}
main {{ max-width: 1400px; margin: 0 auto; padding: 16px; }}
nav.sites {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; font-size: 12.5px; margin-bottom: 10px; }}
nav.sites a {{ color: var(--ink-2); text-decoration: none; padding: 3px 9px; border-radius: 6px; border: 1px solid transparent; }}
nav.sites a:hover {{ background: var(--wash); color: var(--ink); }}
nav.sites a[aria-current="page"] {{ color: var(--ink); font-weight: 600; border-color: var(--line); background: var(--surface); }}
nav.sites .home {{ margin-left: auto; }}
nav.sites .sep {{ color: var(--muted); }}
@media (max-width: 600px) {{ nav.sites .home {{ margin-left: 0; }} .card {{ padding: 10px 6px; }} }}
h1 {{ color: var(--ink); font-size: 1.4rem; font-weight: 500; margin: 6px 0 8px; }}
.summary {{ color: var(--ink); font-size: 0.9rem; margin: 0 0 10px; }}
.lookback {{ display: flex; align-items: center; gap: 6px; font-size: 0.8rem; margin-bottom: 14px; }}
.lookback button {{ background: var(--accent); color: var(--ink); border: 1px solid transparent; border-radius: 3px;
  font-size: 10px; padding: 2px 8px; cursor: pointer; }}
.lookback button[aria-pressed="true"] {{ border-color: var(--ink); }}
.card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
.card h2 {{ color: var(--ink); font-size: 0.95rem; font-weight: 400; margin: 0 0 3px; }}
.card .sub {{ font-size: 0.8rem; margin-bottom: 6px; }}
.notes p, footer {{ font-size: 0.8rem; line-height: 1.45; }}
footer {{ color: var(--muted); border-top: 1px solid var(--line); margin-top: 18px; padding-top: 10px; }}
</style>
<script src="{plotly_js_url()}" charset="utf-8"></script>
</head>
<body>
<main>
{_nav()}
<h1>{esc(TITLE)}</h1>
<p class="summary" id="summary">{esc(default["summary"])}</p>
<div class="lookback" role="group" aria-label="Index lookback"><span>Index lookback</span>{buttons}</div>
<section class="card"><h2>{esc(sentiment.PRICE_TITLE)}</h2>
<div class="sub">{esc(sentiment.PRICE_SUBTITLE)}</div>
<div id="{PRICE_ID}"><div class="plot"></div></div></section>
{_votes_card() if votes is not None else ""}<section class="card"><h2>{esc(sentiment.COLUMNS_TITLE)}</h2>
<div id="{COLUMNS_ID}"><div class="plot"></div></div></section>
<div class="notes" id="notes">{notes}</div>
<footer>{esc(SOURCES)} Not investment advice.</footer>
</main>
<script>window.SURVEYS_META={{"generated_at":"{esc(stamp)}"}};</script>
<script type="application/json" id="surveys-data">{_script_json(payload)}</script>
<script>window.dash_clientside = {{no_update: null}};</script>
<script>
{js}
</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById('surveys-data').textContent);
  var CONFIG = {{displayModeBar: false, responsive: true}};
  var IDS = ['{PRICE_ID}', '{COLUMNS_ID}'];
  var KEYS = {{'{PRICE_ID}': 'price', '{COLUMNS_ID}': 'columns'}};
  var refit = window.dash_clientside.clientside.autoscale_y_axes;
  var HIDDEN = window.matchMedia('{PHONE_QUERY}').matches ? {_script_json(list(PHONE_HIDDEN_RANGES))} : [];
  function plotOf(id) {{ return document.querySelector('#' + id + ' .plot'); }}
  function fitted(layout) {{
    var rs = layout.xaxis && layout.xaxis.rangeselector;
    if (!HIDDEN.length || !rs) {{ return layout; }}
    var buttons = rs.buttons.filter(function (b) {{ return HIDDEN.indexOf(b.label) < 0; }});
    var xaxis = Object.assign({{}}, layout.xaxis,
                              {{rangeselector: Object.assign({{}}, rs, {{buttons: buttons}})}});
    return Object.assign({{}}, layout, {{xaxis: xaxis}});
  }}
  function draw(years, first) {{
    var d = DATA[String(years)];
    IDS.forEach(function (id) {{
      var fig = d[KEYS[id]];
      var fn = first ? Plotly.newPlot : Plotly.react;
      fn(plotOf(id), fig.data, fitted(fig.layout), CONFIG);
    }});
    document.getElementById('summary').textContent = d.summary;
    var notes = document.getElementById('notes');
    notes.textContent = '';
    d.caption.forEach(function (t) {{
      var p = document.createElement('p'); p.textContent = t; notes.appendChild(p);
    }});
    document.querySelectorAll('.lookback button').forEach(function (b) {{
      b.setAttribute('aria-pressed', b.dataset.years === String(years) ? 'true' : 'false');
    }});
  }}
  draw({sentiment.DEFAULT_LOOKBACK}, true);
  if (DATA['{VOTES_KEY}']) {{
    Plotly.newPlot(plotOf('{VOTES_ID}'), DATA['{VOTES_KEY}'].data, DATA['{VOTES_KEY}'].layout,
                   CONFIG);
  }}
  IDS.forEach(function (id) {{
    plotOf(id).on('plotly_relayout', function (ev) {{
      try {{ refit(ev, id); }} catch (e) {{ console.error(e); }}
    }});
  }});
  document.querySelectorAll('.lookback button').forEach(function (b) {{
    b.addEventListener('click', function () {{ draw(b.dataset.years, false); }});
  }});
}})();
</script>
</body>
</html>
"""


def _votes_card():
    esc = html.escape
    return (f'<section class="card"><h2>{esc(aaii_votes.TITLE)}</h2>\n'
            f'<div class="sub">{esc(aaii_votes.SUBTITLE)}</div>\n'
            f'<div id="{VOTES_ID}"><div class="plot"></div></div></section>\n')


def write(path, reads, colors, palette, **kw):
    """Render and write with LF line ends, the bytes publish_pages compares."""
    Path(path).write_text(render(reads, colors, palette, **kw), encoding="utf-8", newline="")
