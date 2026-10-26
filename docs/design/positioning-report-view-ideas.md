# Ideas from an external positioning/crowding report

Evaluation of two outside presentations against what cot-analyzer already draws, written
2026-08-21. Sources reviewed:

1. `positioning_crowding_report.pdf` (9 pages). Page 1 is a cross-asset crowding strip:
   one row per market, grouped by asset class, a red/green min..max bar with a diamond at
   the latest value and a bucket label ("Max Crowded Long" ... "Max Crowded Short").
   Pages 2 to 9 are per-asset-class small multiples: the same market drawn against FOUR
   windows (1-year, 5-year, since COVID, since inception), each bar labelled with the
   window min, the window max and the current value in contracts.
2. A single chart, "Equity-index speculator positioning, aggregate $": S&P 500 price on a
   top panel and, below it, the ES/NQ/YM/RTY spec net position converted to US$ billions
   and SUMMED across the four contracts, filled blue above zero and red below.

Neither is a competitor to this app. Both are one-shot renderings of quantities the
`cotmetrics` layer already computes, with the exception of the dollar conversion. What
they are good at is *layout*, and that is where the ideas are.

## What the app already has

- The page-1 measure is our positioning index. `cotmetrics.indicators` computes
  `(current - window_min) / (window_max - window_min) * 100`, which is exactly the marker
  position on that bar. The Heatmap already renders it per market with conditional
  colour, and the setup gates already bucket it.
- Cross-asset scanning exists as the Heatmap grid, plus the home page accordion and the
  Active Setups strip.
- Basis doctrine (raw contracts vs net/OI) is richer than the report's, which has no
  basis concept at all.
- Three legs are kept separate (Commercial / Non-Commercial / Non-Reportable), and the
  Categories page splits Legacy further into Disaggregated and TFF.

Naming note, 2026-09-17: the app now labels the three Legacy legs with the CFTC's own
category names (Commercial, Non-Commercial, Non-Reportable; `viz_constants.LEG_LABELS`
is the one table). Passages below that predate this say "Large Specs" / "Small Traders"
for the second and third leg; they describe the same series and are left as written.

## What the report does that we do not

### 1. A visual cross-asset strip, not a table

Page 1 reads in about five seconds; the Heatmap needs scrolling and column-by-column
attention. Same numbers, different scan cost. A one-screen strip is the single cheapest
win here: one row per market, asset-class headers, a min..max rule, a marker at the
current index, class rows ordered by index so the crowded ends of the book collect at the
top and bottom of each group.

Do it better than the source in three ways:

- **Draw all three legs on one row**, not a single "spec" marker. The report collapses to
  one series and we would be throwing away the leg structure the whole app is built on.
- **Colour by the setup gate bands, not by arbitrary deciles.** The report's
  `<10 / 10-30 / 30-70 / 70-90 />90` split is a choice with no stated backing. We already
  have calibrated bands and models, and a strip coloured by them says something the app
  can defend.
- **Offer the basis toggle.** Raw and OI-normalized disagree most exactly where a market
  has grown, which is where a crowding read matters.

### 2. Multi-horizon comparison, which is the report's best idea

Pages 2 to 9 answer a question this app cannot currently ask: *is this market extreme
only against the last year, or against its whole history?* The report's own data shows
the two coming apart hard. ZT is at the top of its 1-year range and near the BOTTOM of
its since-inception range. ZB is "Max Crowded Short" on 1-year and mid-range since
inception. A single-window index cannot express that and can read as a strong signal when
the window is simply narrow.

Our lookbacks (`cotmetrics-config/params.yaml`) are only 26 and 52 weeks plus a per-market
`CustomLookbackWeeks`. So this is genuinely absent. Two shapes:

- a **horizon ladder** on the single-asset pages: the same index at 26w / 52w / 5y /
  full history, stacked, so a divergence between windows is visible at a glance;
- a **horizon column group** on the Heatmap, one column per window.

Cost to check before committing: cotmetrics computes rolling min/max per configured
lookback and caches per instrument, so adding 5-year and since-inception windows widens
every cached frame. Measure the cache size and the first-load time before adding them to
the default set.

### 3. Absolute anchoring next to the normalized read

Every bar in the report is labelled with the window min, the window max and the current
value in contracts. That matters because a 0-100 index hides the width of the range that
produced it. Palladium's whole 1-year range is roughly 8k contracts (-5k to 3k) and Gold's
is 116k (186k to 302k); an index of 12 means something different in each. A market whose
window range is degenerate produces a violently swinging index off noise.

Cheapest version: put window min / max / current in the Heatmap index cell tooltip. Better
version: a range-width qualifier (window range as a fraction of open interest, or of the
market's own long-run range) so a "Max Crowded" call on a squashed window can be
discounted rather than trusted equally.

### 4. Time-in-state, which neither presentation has

Page 1 is a snapshot with no history. It cannot distinguish a market that hit its extreme
this week from one pinned there for four months, and those are not the same trade. We have
the weekly series, so a sparkline column, or a simple "weeks in this bucket" count, is a
strictly additive view neither source offers.

This matters more here than it would elsewhere, because the positioning series is near
unit-root and exceedances arrive in **episodes** (`cotmetrics/docs/positioning-series-properties.md`:
median lag-1 autocorrelation 0.956, effective sample roughly a fifth of nominal). Any
readout that counts "how many markets are extreme right now" is counting correlated
observations, and a strip that shows 12 markets at "Max Crowded" invites the reader to
treat that as 12 independent facts. Showing time-in-state is the honest correction.

## The dollar-notional chart

The aggregate-$ chart is the more interesting of the two artifacts, because it does
something the app currently cannot: it makes positions **commensurable across markets**,
which is what licenses the sum. Our Aggregation page sums net positions in contracts
across selected assets. The report itself disclaims that ("contracts not summed across
markets") and it is right to. Contracts of ES and contracts of YM are different units.

Converting with `Point Value x price` fixes that, and the inputs exist:
`marketdata.store.read_metadata()` carries `Point Value` for 49 symbols, and
`marketdata.get_bars` carries the price. So an "aggregate spec exposure, US$" panel for a
complex (equity index, energy, metals, the whole book) is buildable today.

Four traps, all of which will silently produce a wrong chart rather than an error:

- **Use unadjusted prices, not back-adjusted.** A notional level is `contracts x
  multiplier x PRICE`, and Norgate's `_CCB` back-adjusted series is not a price level: it
  restates history on every roll and for crude it can go negative. marketdata stores both
  `backadj` and `unadj` precisely so this is a choice rather than an accident. A notional
  history built on `backadj` is fiction that looks plausible.
- **Multipliers are not constant over the full history** for several contracts, and the
  specs table is a snapshot of today. Either accept the distortion and say so in the
  caption, or bound the chart to a window where the multiplier held.
- **Sign convention.** The chart's "long equities +" is spec net. In our terms that is
  Large Spec net plus Small Trader net, which is the negative of Commercial net. It is not
  the Large Spec leg alone.
- **Where the code lives.** This is a joiner: COT x prices x contract specs. cot-analyzer
  computes no metrics of its own, so a notional column belongs in `cotmetrics` (which
  already reads `marketdata` for prices and proxies) and this repo draws it. This is the
  same normalization crowdmon was built for, and crowdmon is deprecated. Only the
  arithmetic is being reused, not the composite damage thesis; do not reopen that.

Paired with the price panel above it, as the source does, this is a strong single view:
"the crowd's dollar exposure to equities, against the thing they are exposed to."

## What NOT to copy

- **"Net SPEC (mirror of commercials)."** In the Legacy report the three legs sum to zero,
  so the mirror of Commercial net is Non-Commercial net PLUS Non-Reportable net. Calling
  that "spec" quietly folds small traders into the speculator leg. The app keeps them
  apart, and the gates treat the Small leg as its own piece of evidence. Do not adopt the
  shorthand.
- **"Buckets by 1yr percentile"** in the page-1 footer, when the geometry drawn above it
  is range position. They are different statistics: range position is set by two extreme
  observations, a percentile rank uses the whole window. Whichever we draw, label it as
  what it is. Offering both is cheap and the difference is informative: a market at range
  position 95 but percentile 78 has one outlier week holding the top of its range.
- **Uniform-window assumption.** The report uses one 1-year window for every market, which
  is at least consistent. Our Heatmap defaults to `Custom`, and `CustomLookbackWeeks` is
  tuned per market for deploy instruments, so a cross-asset scan there is already comparing
  markets measured over different windows. That is defensible for a per-market signal and
  is a hazard for a cross-asset ranking. If a strip page ships, it should either force one
  window or state the per-market window on the row.

## Suggested order

1. Cross-asset strip page, three legs, gate-band colouring, basis toggle. Data all
   present, no new metrics.
2. Window min / max / current in the Heatmap tooltip. One change, removes the worst
   ambiguity in the existing index columns.
3. Time-in-state (sparkline or weeks-in-bucket) on the strip and the Heatmap.
4. Horizon ladder, after measuring the cache cost of the longer windows.
5. Dollar-notional aggregate, as a `cotmetrics` column plus an Aggregation basis, on
   unadjusted prices, with the multiplier caveat in the caption.

## Bottom line

Neither document contains a metric we do not already compute. What they contain is better
packaging, and two of those packaging choices are worth taking seriously: a scannable
cross-asset strip instead of a grid, and the multi-window comparison, which asks a
question our single-lookback index genuinely cannot answer. The dollar-notional chart is
the one real capability gap, it is buildable from stores we already read, and it would
make the Aggregation page's cross-market sum defensible rather than merely available. The
report's own labelling is loose in two places (spec-as-mirror-of-commercials, and
percentile-vs-range-position) and those are the parts to leave behind.

## Layout critique: where these designs are weak

The section above takes the ideas. This one takes the execution, because several of the
layout choices actively work against the point the chart is making, and copying the shape
without fixing them would import the problem.

### The four-panel range pages: every window is drawn at the same width

This is the serious one. Pages 2 to 9 draw four windows per market as four separately
scaled bars, each rendered at full panel width. The windows are nested by construction
(a 1-year range is a subset of the since-inception range), so the interesting fact is
*how much narrower* the recent window is, and equal-width drawing destroys exactly that.

Measured across the 43 markets in the report, using the endpoint labels the report itself
prints:

- the since-inception span is a **median 2.5x** the 1-year span;
- **16 of 43** markets have a full-history span more than 3x their 1-year span;
- the worst are OJ at 8.2x, ZAR at 6.8x, PL at 6.3x, PA at 5.6x, NQ at 5.4x.

An 8x difference in the underlying quantity is drawn as zero difference in ink. The reader
has to do the arithmetic from four pairs of small endpoint labels, which is the work the
chart existed to save.

**Fix: one shared x scale per market, windows nested on a single row.** Draw the
since-inception span as the full-width rule, the since-COVID span inset within it, then
5-year, then 1-year, then one marker for the current value. A market at the top of its
1-year range but mid-range historically then looks like what it is, and the whole
comparison collapses from four panels to one row. That also removes the need to repeat the
market label four times.

### The same pages repeat themselves

Because the windows are nested and several contracts have short or quiet histories, many
panels are duplicates. Again from the report's own numbers: **28 of 172 window-rows (16%)
have exactly the same min and max as another window of the same market**, 19 of the 43
markets have at least two identical windows, and Lean Hogs has all four identical, so a
quarter of that page is the same bar drawn four times.

Nesting the windows on one row (above) makes this self-documenting: a window that adds no
range simply has no visible inset, which is itself informative. If separate panels are
kept, suppress a window whose range matches a longer one and say why.

### Label collisions at exactly the moment that matters

The current-value label collides with the window-max label whenever the current value is
near the top of the range, which is precisely the case a crowding report exists to
highlight. It is visible on ZT and ZF (1-year), ES, HG, SB and CT, where the black
current label overprints the orange max label.

Fixes, in order of preference: put the current value in a fixed column at the right of the
row rather than floating above the marker; or suppress the endpoint label when the marker
is within a few percent of it, since the marker position already says the value; or use a
short leader line.

While there: the endpoint labels mix suffixed and bare numbers in one column
(`-1.7m`, `-973k`, `897`, `-273`). Those bare values are correct, not bugs, but in a column
of k-suffixed numbers `-273` reads as `-273k` at a glance. Format one way, with the unit,
and give the row a consistent significant-figure count.

### Three encodings of one variable, and no scale for any of them

Page 1 encodes the crowding bucket three times: marker position along the rule, marker
colour, and a text label ("Max Crowded Long"). One variable, three channels, and none of
them carries a number. There is no axis, no tick, no 0/50/100 gridline, and no value
printed anywhere on the page, so a marker at roughly 60% of the rule cannot be read as
anything more precise than "somewhat long".

Spend one of those channels on new information instead. Replace the text label with the
index value, or with the 1-week change, or with weeks-in-bucket. Keep colour for the
bucket and position for the value, and add faint rules at the band boundaries so position
becomes readable rather than merely relative.

### Page 1 has no as-of date

The title says "1-year lookback" and the footer says "Source: CFTC COT, weekly." Nowhere on
the page does it say which Tuesday the snapshot is. For a document whose entire content is
one week's positions, that is the most important missing element, and our Heatmap already
gets this right with its snapshot caption. Any strip page we build must carry the report
date in the header, not the footer.

### Layout economy

The page-1 bar occupies roughly a third of the page width, with a wide empty gutter between
the market name and the start of the rule and a second column of repeated text at the
right. Roughly half the markets sit in the Neutral bucket and are drawn at full visual
weight, so most of the ink is spent on the rows with the least to say. Widening the rule,
de-emphasizing Neutral rows, and sorting within each asset class by index would put the
crowded ends of each group at the top and bottom where the eye lands first. The report
keeps a fixed within-class order, so finding the extremes means reading every row.

Conversely the four-panel pages waste vertical space: the grid is fixed at four panels
regardless of the class, so Livestock (3 markets) and Rates (4 markets) leave half the page
blank while FX (11 markets) is tight. Size the panel to the class.

### The aggregate-$ chart

Better designed than the PDF, and the two-panel price-over-positioning stack with a shared
x axis and a zero-line diverging fill is the right shape. Four things to improve when we
build our version:

- **Scope mismatch between the panels.** The top panel is the S&P 500 alone; the bottom
  aggregates ES, NQ, YM and RTY. The price reference is not the thing the exposure is
  against. Either weight a composite of the four underlyings to match the aggregate, or
  label the top panel as a reference index rather than as the counterpart.
- **The publication lag is invisible.** Positioning is as-of Tuesday and published Friday,
  and the chart plots it at the Tuesday date against a daily price line. Read literally it
  suggests the positioning was knowable when the price printed. An as-of / as-published
  toggle, or a fixed shift to the release date, makes the chart honest about what a reader
  could have acted on. This matters more for us than for a static PDF, because our charts
  sit next to setup gates.
- **A weekly series drawn as a continuous line** against daily bars implies intra-week
  detail that does not exist. Step interpolation, or visible weekly markers, says what the
  data is.
- **Small collisions and duplications.** The source note overlaps the x-axis year labels.
  The y-axis title repeats the units already given in the subtitle. There are four stacked
  text elements above the top panel (title, subtitle, in-plot panel title) at three
  different weights and two different left edges. And "Aggregate net (all contracts)" is
  ambiguous between "all four markets" and "futures and options combined", which is a
  distinction our store takes seriously.
- **Nothing marks the extremes** on a chart whose subject is crowding. Shading the top and
  bottom deciles of the aggregate's own history, or a second trace of its percentile,
  would let the reader see whether today's +47bn is unusual without eyeballing the whole
  series.

### Carry-over rules for our version

1. Nested ranges on a shared scale, never equal-width panels per window.
2. Report date in the header of any snapshot view.
3. One channel per variable; if a bucket is coloured, the label should carry a number.
4. Current value in a fixed column, not floating where it can collide with an endpoint.
5. Sort within group by the quantity being shown, and de-emphasize the neutral majority.
6. Say what the lag is, and mark weekly data as weekly.

## Bottom line on the layouts

The ideas are better than their execution. The four-panel range pages defeat their own
purpose by drawing windows that differ by up to eight times at identical width, and they
repeat themselves on 16% of rows; both problems disappear if the nested windows share one
scale on a single row. Page 1 spends three visual channels on one variable, prints no
number and no as-of date, and gives half its ink to the markets with nothing to say. The
dollar chart is the soundest of the three and still mismatches its price reference to its
aggregate and hides the publication lag. None of this argues against the ideas; it argues
for taking the shape and rebuilding the layout rather than reproducing it.

## Would box-and-whisker present better?

Not for the cross-asset strip, and not as a drop-in for the four-window pages. It would
earn its place in one view neither source has.

### What a box would genuinely add

A min..max rule is set by two observations and says nothing about where the mass sits.
That is the range-position-versus-percentile problem from the section above, drawn rather
than argued: a market at range position 95 might be at the 78th percentile of its window
if one outlier week holds the top, and the rule cannot show the difference. A box exposes
it immediately, which is a real gain.

### Why it is the wrong instrument for this series

The grammar of a box plot asserts that the marks are draws from a distribution: quartiles
estimate population quantiles, the 1.5 IQR fence flags outliers. Positioning does not
behave that way. `cotmetrics/docs/positioning-series-properties.md` measures a median
lag-1 autocorrelation of **0.956** and finds exceedances arriving in episodes, with an
effective sample roughly a fifth of nominal. A 52-week box is therefore built on about ten
effective observations, and its quartiles are not stable estimates of anything.

That is worse than merely imprecise: it is confidently imprecise. The min..max rule makes
no distributional claim, so the reader supplies the appropriate scepticism. A box looks
like statistics and invites the reader to trust the quartiles as a reference distribution.

The failure is sharpest under a trend, which is the normal state of a positioning series.
If positioning drifted from one extreme to the other across the window, the median sits
mid-path and the IQR is the middle half of the journey. It describes the path, not a
population, while looking exactly like a population summary. The 1.5 IQR fence then flags
a run of consecutive weeks as "outliers" on a skewed, persistent series, which is clutter
that means nothing.

Two practical objections on top of the statistical one. A box needs vertical room to stay
legible, and the strip has 43 rows; boxes read well at ten to fifteen rows, not forty. And
a box discards time exactly as the rule does, so it does not fix the real gap identified
earlier, which is that a market pinned at an extreme for four months and one that arrived
this week still look identical.

### A whisker already means something else in this stack

`crucible/src/crucible/report/tearsheet.py` uses whiskers for **confidence intervals on an
estimator**, and its block-bootstrap panel is built precisely on the point at issue here:
the block whisker is wider than the i.i.d. whisker exactly when the series is positively
autocorrelated, which is what makes the i.i.d. band the optimistic one. Whiskers on a
tearsheet mean uncertainty in an estimate. Reusing the same mark in cot-analyzer to mean
range of observed values puts two meanings on one visual idiom in front of the same
reader. If we do use boxes anywhere here, they should look distinct from those whiskers.

### What to use instead on the strip

The right idiom for "current value against qualitative bands within a range", at forty-odd
rows, is a bullet chart: a background banded by the gate thresholds, a thin rule for the
window range, one marker for the current value. It carries everything the report's row
carries, plus the bands, in less vertical space than a box, and it makes no claim about
the distribution.

If the distribution question is worth answering on the strip, answer it with a second
tick rather than a whole box: draw the current value's percentile rank as a faint tick
beside the range-position marker. When the two separate, the range is outlier-driven, and
that is the entire piece of information a box would have been added to supply.

For the nested multi-window row, quartile ticks on the longest window only would work,
since the full history is the one window with enough effective observations to be worth
quartering. Keep the shorter windows as plain nested rules.

### Where a box plot does earn its place

Across markets rather than across time. A box per asset class of today's positioning index,
with each market drawn as a point on it, answers a question neither source asks and this
app cannot currently answer: **is this whole complex crowded, or one contract?** That is a
cross-section, one week and many markets, so the autocorrelation objection largely goes
away, the row count drops to nine or so classes, and the points carry the market identity
that a box normally hides. Gold at range position 45 inside a metals class whose whole box
sits high is a different fact from the same 45 in a class straddling neutral.

One thing to keep out of the app: boxes of forward returns conditioned on positioning
buckets. That is a distribution chart that reads as an edge claim, and an edge claim
belongs behind the gauntlet with its search denominator, not on a dashboard panel.

### Bottom line on whiskers

A box plot would fix the one thing the min..max rule genuinely hides, and would break two
larger things in exchange. On a series with 0.956 lag-1 autocorrelation, quartiles drawn
from about ten effective observations look more rigorous than the rule they replaced while
being less honest, and under a trend the box summarises a path as if it were a population.
Use a bullet chart with a percentile tick on the cross-asset strip, keep the nested rules
for the multi-window view, and save the box for a cross-section across markets, where the
statistics behind it actually hold.


## What shipped: the cross-asset strip (2026-08-21)

Item 1 of the suggested order above, at `/strip`
([`src/pages/analytics/strip.py`](../../src/pages/analytics/strip.py), figure logic in
[`src/components/strip_traces.py`](../../src/components/strip_traces.py)).

It reads the same `get_matrix_data` frame the Heatmap does and computes nothing, so the
only thing it changes is scan cost. The carry-over rules from the layout critique are
each answered by something concrete:

| rule | how the strip meets it |
|---|---|
| never equal-width ranges | there is no range bar. In index space it would always be the full axis, so the bar diverges from the neutral midpoint instead: length is distance from neutral, direction is the sign |
| report date in the header | the caption states the Tuesday, the model, and the window, and it names any market dropped for having no index that week |
| a number, not a third copy of the bucket | the value is printed; the redundant "Max Crowded Long" label is replaced by the model's gate verdict, which depends on the other legs and so is not a restatement of the bar |
| current value in a fixed column | value and verdict are drawn at fixed x, past the end of the scale, where nothing can collide with them |
| sort within group, de-emphasize neutral | markets sort by index inside their asset class, and a neutral market draws almost no ink because its bar is short by construction |
| say what the window is | the caption distinguishes a uniform 26/52-week window from the per-market `CustomLookbackWeeks`, which is the trap in ranking markets against each other |

Two things it does that the source reports do not. Every leg the chosen model gates on is
drawn as a tick on the same row, rather than one collapsed speculator series, and a tick
brightens only when that leg is through its own gate opposed to Commercials, in the
direction the row points. And the bar's colour is the ROW's setup verdict rather than its
own level, so a long dim bar names a market at an extreme that some other leg is blocking.
On the 2026-08-18 board that is immediately visible: all three Live Stock markets sit at
100 with no setup.

### Colour, after the first review

Three changes came out of looking at it, and each is a channel being spent on the wrong
thing.

The ticks now take the app's own leg colours by palette slot, Large Specs from slot 1 and
Small Specs from slot 2, the same slots every stacked panel in `plot_traces` draws from.
Before this they were one grey for both, which made the strip the only surface in the app
where leg identity was not a colour, and left the two legs indistinguishable from each
other. Whether a tick is gating moved onto opacity, so colour says which leg and opacity
says whether it counts. A glyph per leg was the alternative and lost on row height: at
21px a tick's whole job is to say where on the axis the leg sits, and a diamond or a star
is several axis units wide at that scale, so the shape carrying identity would blur the
position carrying the measurement.

The bar fills are knocked back to `BAR_FILL_ALPHA`. `grid_colors` picks its colours for
AG Grid cell TEXT, 11px glyphs on near-black, and deliberately swaps several palette reds
for a hotter one so they stay legible at that size. A filled bar is orders of magnitude
more pixels of the same colour, so the value that reads as legible in a table reads as
glare here. The small text beside each bar keeps the full-strength colour, which is the
same trade sized for the mark it is actually on.

The figure is capped at 1180px rather than stretched. The axis is 130 units wide whatever
the window is, so on a wide monitor every bar becomes a slab. The first thing that made
the page read better was narrowing the browser, which is the same observation from the
other end.

### Layout, after the second review

Four changes, and the first one retracts something this document argued for.

**The two text columns are gone.** The strip carried the index value and the gate verdict
in fixed columns, on the reasoning in the layout critique above: the printed reports
collide those labels against a bar end exactly on the rows worth reading, so a fixed
column cannot collide. That argument still holds for a printed page and does not hold
here. The bar's position against a banded, ticked axis already says the level, its colour
already says the verdict, and the exact figures for every leg are one hover away, which
is a channel a PDF does not have. Two columns of text for 42 rows was a second copy of
what the picture had. The axis now stops at 104 instead of 128, and the width cap came
down in step so the bars did not simply get longer.

**Filters, on two axes that cannot contradict each other.** SHOW takes the model's
verdict (all / setups / setups and near); SIDE takes which half of its own range the
market sits in (both / bullish / bearish). They are separate controls because they answer
separate questions, and they are safe to combine because a bull setup is above neutral by
construction. A class emptied by a filter loses its header rather than standing as a
heading over nothing, and the caption counts what the filters hid, for the same reason it
counts markets with no index: a filtered board that looks like a full one is the one
failure mode worth a sentence.

**A blank row between asset classes**, with the separator rule through the middle of it.
The rule alone left the groups touching, so the break read as a line drawn through one
continuous list rather than as space between two lists. This also fixed a quiet geometry
bug: the module carried two row heights, a taller one for class headers, but the y axis
is linear over the row count and spreads every row evenly, so the taller constant only
ever made the figure taller than the rows it held. One height now, and the air comes from
a real empty row, which the axis does honour.

**Two columns on a wide screen**, breaking only between classes. A laptop is far wider
than the strip needs and far shorter than 50 rows, so one column wastes the axis it has
and scrolls for the rows it does not. The split balances on row count rather than class
count, because the classes are wildly uneven: Currencies has nine markets and Crypto has
two, so dealing classes evenly would leave one column half the length of the other. A
class is never broken across the boundary, since half of Metals at the bottom left and
half at the top right is worse than the scrolling this removes. The legend is drawn once,
on the first column. On the live board that is 23 markets against 19, and the whole
universe fits one screen.

### Two defects and the group headers, after the third review

**The legend hid the scale when few asset classes were selected.** It was positioned at
paper `y=1.03`, which is three percent of the PLOT height above the plot, and the plot
height is the row count. On a full board that clears the top axis comfortably; with one
or two classes switched on it is a few pixels and the legend lands on the tick row. Same
layout, and whether the scale was legible depended on how many markets the reader had
switched on. It is now pinned with `yref="container"`, so the gap is measured against the
figure rather than against the rows, and the top margin is sized from the legend's
measured height (87px) rather than guessed: the first guess was 84 and put it three pixels
into the axis it had just been moved to clear.

**Two classes never split into two columns.** The guard that stops the splitter starting
a column it cannot fill counted the column being closed as one still needing blocks, so it
demanded two remaining classes to make a second column out of one. Off by one, and
invisible on the full board.

**The class headers now carry a band, a bolder name and a tally.** Left-aligned rather
than centred over the bars: headings on one left edge are scanned by running the eye down
a single line, while centred ones move with the length of each word and would sit among
the marks they label. The band is what makes the header span the bars, which is what
centring was reaching for. The tally ("2 setups · 1 near") is there instead of an icon,
on the same reasoning that removed the redundant text columns: an icon is a second thing
to maintain per class that says nothing the class name does not, while the count is the
reason to look at that group at all.

**Market names are lit when their row has a verdict.** This does draw one variable twice,
which the rest of this document argues against. The exception is distance: the name column
is where the eye starts and the bar carrying the verdict is at the far end of a wide row,
so a reader scanning names alone had no way to find the setups without tracking across
every one.

### Bar or mark

Both, selectable, defaulting to the diamond. The bar encodes the value twice, as the
position of its right end and as its length from the neutral midpoint, and that second
reading costs a row of saturated colour, which is why the fills had to be knocked back at
all. A mark encodes position once, which is the whole of what a bounded 0-100 index has to
say. The decision this page supports is "which side of the band", a position question
rather than a magnitude one, and the verdict no longer needs area to be scannable now that
the market name carries it too. What the bar genuinely buys is a pre-attentive ranking by
length, and the rows are already sorted by that same value, so the ordering carries it.

**Where it stood six weeks ago, which was briefly and wrongly called blocked.** The basis
hazard is real: `get_matrix_data` calls `get_symbols_data` without a basis, so it defaults
to `BASIS_RAW`, and its exported `Comm Move` column is therefore a RAW point change
sitting beside a `Comm Index Norm` that is normalized. Subtracting one from the other
under NPF mixes bases, which is precisely the defect `movers.py` shipped and
`models.leg_columns` exists to prevent.

What does NOT follow, and was asserted here for one turn, is that the data is missing.
`get_symbols_data` returns `df.copy()` and lands BOTH families on every frame whatever
basis it was asked for, so `Comm Custom Move Norm` was already sitting on the frame
`get_matrix_data` holds, unread. Verified against the live store before changing anything.
The fix is one additive line in `cotmetrics.reports`, exactly mirroring the `norm_idx_col`
two lines above it, and the strip then reads whichever momentum column belongs to the
selected model's basis. The lesson is the ordinary one: a column absent from an export is
not a column absent from the data, and the difference is one grep of the producer.

Worth noting in passing: the Heatmap shows one `Index Momentum` block beside both model
blocks, so it displays raw momentum next to normalized indices today. Not introduced here
and not fixed here, but the same column is the reason, and the new one is now available to
it.

### The marks, after the fourth review

**Shape carries the verdict, colour carries whose leg it is.** A row the model has
something to say about gets a diamond in the verdict colour. A quiet row gets a tick, the
same mark the speculator legs use, in the app's COMMERCIAL colour rather than a neutral
grey. Grey said only "nothing here" while leaving the one series on the row unnamed by
colour, which is the thing every other panel in the app names by colour. A quiet row now
reads as three marks of one family rather than as a special case.

**And where it stood six weeks ago, as a hollow mark on the same row.** No connector back
to the current position: the reference charts that do this well draw the two positions and
let the row pair them, and 42 connectors is a lot of line for a move that is usually a few
points wide. The prior value is clamped to the axis, because the index is bounded while
the change is a point difference, so a market that ran from 2 to 98 would otherwise place
its prior mark off the scale.

**The top margin is derived now, not declared.** It has to hold the legend and the top
axis, and a hardcoded value was wrong three times: 84 against an 87px legend, then 104
when adding two keys took the legend to 125. The legend grows whenever a mark or a leg is
added to it and nothing connected a constant to that, and the failure is quiet, since a
legend that outgrows its margin does not look broken, it just covers the scale. It is now
computed from the keys actually drawn.

### Row banding, after the fifth review

A row carries four marks now (Commercials, where Commercials stood six weeks ago, and a
tick per speculator leg) on nineteen pixels of height, and nothing tied them to each other
or separated them from the row above. The printed reference solves this by drawing each
asset inside its own rectangle. Copying that literally does not work here: the rectangle
would span the whole axis on every row, because the index is 0-100 by construction, so it
would be identical everywhere and carry no information beyond the grouping. Banding every
other row is the same grouping for half the ink, and it is what the app's own tables
already do (`tr:nth-child(even)` at `rgba(255,255,255,0.025)` on the Heatmap grid). The
phase resets at each class header, so the first market under a heading always looks the
same rather than depending on how many markets the class above happened to have.

Found while checking this at several window widths: the figure carries an explicit pixel
height, and without `responsive` it kept whatever width it was first drawn at. Resizing
the browser left the chart at its old width until a reload, which is worth fixing rather
than noting, because narrowing the window is the first thing a reader does to this page.

### An unset colour is the theme's colour

The six-weeks-ago circles drew teal green against a red key that said the same thing.
Cause: an OPEN Plotly symbol takes its outline from `marker.color`, while `marker.line` is
a second stroke around that, and only the line colour had been set. `marker.color` was
therefore `None`, which is not an error, it is the template colourway, whose third entry
is `#00cc96`. The legend proxy set `marker.color` and so was correct, which is the only
reason the disagreement was visible at all.

The general test written for it immediately found a second instance: the speculator leg
ticks set only `marker.line.color` too. Those render correctly, because a `line-*` symbol
happens to draw from `marker.line`, so that one was one symbol change away from silently
becoming a template colour. Every drawn trace now names its colour, and a test asserts it
for both marks rather than pinning the one case that was noticed.

### Class breaks and row isolation, after the sixth review (2026-08-22)

Four changes that turned out to depend on each other, plus the two earlier passages they
supersede. **The header paragraph in "Two defects and the group headers" and the whole of
"Row banding, after the fifth review" describe what the page did before this, and both are
now wrong about the shipped code.** They are left in place because they record what was
tried, which is the argument for what replaced them.

**The gate zones stop at the block edges.** They were one rectangle each over the whole
figure, so the red and green washed straight through the blank row between two asset
classes and the separator was doing its work against a continuous colour. They are drawn
per run of market rows now, so the whole break, the gap and the heading in it, is clean
background. Empty space between two painted blocks is the one thing on this figure that
separates them at no cost in ink.

**The class heading is centred on a quiet bar of its own.** Both halves of this reverse an
earlier decision. The band was tried once and rejected as noise, correctly, back when it
sat on top of the continuous wash and read as a third stripe among many; with the zones
cut back it is the only thing painted on that row and reads as a divider carrying a name.
And the left-alignment argument, that headings on one left edge are scanned by running the
eye down a single line, missed that the left margin is ALREADY a column of names: the
heading sat in the same left-aligned stack as the market labels, differing only in weight,
so the element separating two classes competed with the element naming a market. Centred
on the plot it is nowhere near that column and lands on a row that carries no marks. The
tally that paragraph describes is not in the shipped page; the counts said what the lit
market names already say.

**The hairline rule through the spacer row is gone.** With the heading bar and the blank
row both in place it was the third divider in a stack of three.

**Row banding became a row RULE**, a hairline on the boundary between adjacent market rows,
inside a block only. The band was calibrated twice (0.035 invisible, 0.06 read as white
stripes with data in the gaps, 0.045 between them) and the thing no alpha could fix is that
a filled band is a rhythm: every other row lit gives an eleven-row class, and Currencies is
exactly that, a ladder the eye resolves before it resolves the data. A rule treats every row
alike, gives it a floor rather than a fill, and is enough less ink that it can sit at 0.10
and still read quieter than the band did at 0.045.

Three alternatives were drawn on the same board before that was picked, and the losing two
are the useful part of the record. **Nothing at all** is calmer still and fails on one case,
a row whose only right-hand mark is a lone leg tick, where the eye crosses 700px with no
guide; the failure is concentrated in the long classes. **A hairline through each row**, as
a leader from the name to the marks, is collinear with the stem, so it reads as the stem
continuing past its head and fights the one quantity the stem measures. **A half-strength
band** keeps the rhythm and loses most of the association it was buying.

**The margin the headings vacated was reclaimed, 140px to 124px**, sized by measuring every
name in `cotmetrics-config` at the tick font rather than by eye. It fits "MSCI Emerging
Mkts" (105px), not the widest name currently plotted, "Australian Dollar" (83px), because
the two longest are both `heldout` today and a margin fitted to what is on screen would clip
the day either is promoted, and clip quietly, as a shortened name rather than an error.
Reclaiming the slack also exposed that Plotly leaves about a pixel between a tick label and
the plot when `ticks=""`, invisible while the margin carried 35px of spare, so the standoff
is explicit now. The real reclaim is 16px per column, not the ~35 the old constant looked
like it was wasting.

Still not built, in the order the list above gives them: the window min/max/current
tooltip, time-in-state, the horizon ladder, and the dollar-notional aggregate. The
percentile tick argued for in the whiskers section needs a percentile rank that
`cotmetrics` does not currently expose, so it is a change there before it is a change
here.


## After the seventh review: the dollar aggregate is built

Idea 5 in the suggested order above ("Dollar-notional aggregate, as a `cotmetrics` column
plus an Aggregation basis") shipped as its own page, `/exposure`, rather than as a basis
on the existing Aggregation view. The reason for the change of shape is the reason the
idea was worth building at all: Aggregation is a per-market stack of panels, and the
whole point of converting units is that the TOTAL means something, so a total needed a
view whose subject is the set.

**What the earlier sections got right and what they missed.**

The four traps listed under "The dollar-notional chart" all held and are all handled:
`unadj` for levels (and the guard turned out to matter more than expected, because
`marketdata.get_bars` DEFAULTS to `backadj` and the `Closing Price` column already on
every CotIndexer frame is that default, so the wrong series is the one nearest to hand);
multipliers as a present-day snapshot; the sign convention, where the spec leg is
computed as Large PLUS Small rather than as the negation of Commercials; and the code
living in `cotmetrics` with this repo drawing it.

Two things those sections did NOT anticipate, both found by building it:

- **Dollar notional is not a normalizer.** This document treated the dollar conversion as
  making positions "commensurable across markets", which is true of ADDING them and false
  of COMPARING them. Notional makes ES dwarf orange juice permanently because the ES
  market is larger, so ranking markets by it produces a market-size ranking wearing a
  positioning label. The rung that is both summable and comparable is notional x daily
  volatility, and it MULTIPLIES: a vol-targeting book sizes at `target / sigma`, so the
  product is what stays constant while it sits at target. Both units ship, labelled for
  what each can and cannot support.
- **No unit here is stationary through time.** Dollar risk carries the price level just
  as notional does (`price x percent vol` is dollar vol), so a twenty-year history of
  either is substantially a history of the index level and its most recent swings will
  always look the largest. This is why the expanding percentile is not optional
  decoration: it is the only thing on the page that answers "is this a lot". The section
  above recommended shading the extremes as an improvement over the source; it is closer
  to a requirement.

**The layout critique's four fixes all shipped**: the reference panel is
`composite_price_index` over the same set the bottom panel sums, so reference and subject
cannot come apart the way the source's S&P-over-four-markets does; the extremes are
marked with an expanding 10th/90th envelope; both weekly series step; and the publication
lag is stated in the caption in words.

**One problem the source never had to solve**, because it fixed its own four markets: a
strict "sum only weeks every member can price" rule is correct and expensive. The live
equity complex includes NKD, whose COT history ends 2026-03-03, so a six-market total
ends there while the other five run to the current week, and nothing about the resulting
chart would say so. `AggregateExposure` reports dropped members by name and reason,
per-member coverage, which member bounds each end, and how many weeks the rule cost; the
page turns that into a line above the figure and a per-market control for removing the
constraining member. Week-snapping was tried first and rejected on measurement: aligning
to Mon-Fri weeks recovers 1,373 shared observations against 1,375 by exact date, so the
missing weeks are genuine coverage gaps rather than misalignment.

## After the eighth review: what a total hides

Two questions came up about showing more than one series at once, and they have opposite
answers. Both were settled by measurement rather than by argument, and the measurements
are the durable part.

**Commercials beside Speculators: no, it is an accounting identity.** Across all 45
priceable markets and every week in the store, `max |Comm_net + Spec_net| = 0.000000`
contracts. The Legacy legs sum to zero by construction, so drawing both gives one series
and its reflection. That is worse than merely redundant: two lines converging and
diverging across a zero axis look like a relationship, so a reader would spend real
attention decoding an identity. The leg selector already covers it and produces the same
picture flipped.

**Large beside Small: yes, and it was the page's biggest omission.** They sit on OPPOSITE
sides **59%** of weeks (61% over the last five years, level correlation **-0.26**), and
the sign of their total disagrees with Large **30%** of the time and with Small **29%**.
So about a third of the time the aggregate points somewhere neither of its two halves
does. On the week this was written the page said CROWDED LONG on a speculator total of
+$509m made of Small Traders +$665m against Large Speculators -$156m.

**Composition by market: yes, and the concentration is large.** Speculator risk that same
week: S&P 500 $371m (59.5% of gross), Nasdaq $116m, Russell **-$57m** (the other way),
DOW $51m, MidCap $28m. So "equity speculators are crowded long" was substantially "the
S&P is". `agreement = |sum| / sum|.|` scores this in one number and moves independently
of the level: **1.00** for Small Traders, who were unanimous, against **0.63** for Large
Speculators, who were split, on the same markets on the same day.

What shipped: the two halves drawn as thin unfilled lines under the total when the leg is
Speculators; a horizontal contributors bar for the latest week, with bars that point
against the total faded rather than recoloured; and a composition sentence under the
headline naming the disagreement, the dominant market and the agreement score. A
market-by-market history panel was considered and rejected: five lines over 24 years is
unreadable, and the question is about the week the reader is looking at.


## After the ninth review: one market is a reading, not a degenerate set

The page called itself a set view, in the module docstring ("deliberately a SET view
rather than a market view"), in the sentence above the chart ("a whole group of
markets"), and in every line that said "this set's own history". The argument behind it
was that a single market's dollar exposure is the positioning index wearing bigger
numbers, so converting units only earns its keep on a total.

**That argument is false, and the size of the error is the point.** Take the same
52-week range index this app already uses, and run it on net contracts and on dollar
risk for the same market and leg (Large Speculators, 44 markets, all history in the
store):

| | median | worst |
|---|---|---|
| correlation, index on contracts vs on dollar risk | **0.920** | 0.713 (Gasoline), 0.750 (Gold), 0.754 (Crude) |
| 95th-percentile gap between the two readings | **28 index points** | 52 (Natural Gas) |
| weeks where they disagree on top-or-bottom quintile | **17%** | 33% (Gasoline) |

So on about one week in six the two disagree about whether the market is at an extreme
at all, and on the markets a reader is most likely to care about (Gold, Crude, Natural
Gas, Gasoline, the metals) they disagree more than that.

**Almost all of the gap is volatility, not price.** The same comparison against NOTIONAL
alone correlates **0.984** at the median. Notional is contracts times a slowly-moving
price, so it is close to a monotone transform of the contract count over a 52-week
window; risk multiplies by sigma, which moves on its own schedule and is the term the
positioning index cannot carry. That is a fact about a single market, and it is exactly
what a page in risk units can say that no normalized index can.

There is a second single-market reading the range index deliberately discards: absolute
scale through time. A rolling range index is renormalized every week, so it cannot say
that this is the largest dollar bet the crowd has ever held here. The expanding
percentile on this page can, and does.

What changed, all copy and no arithmetic: the lede offers a market or a set; the
headline, the caption, the contributors label and the figure title say "market" and name
it when one market is selected; the membership line reads "Gold on its own" rather than
"1 of 1 markets summed"; the composition sentence drops the concentration clauses, which
for one market can only report 100% of itself and 1 of 1 markets agreeing, while keeping
the Large-against-Small split, which is a real disagreement inside one market's number;
and the explanation gained an entry carrying the measurement above.

The noun comes from `len(agg.coverage)`, not from the length of the Markets selection: a
two-name selection where one market dropped for want of a contract multiplier IS a
single market, and the sentences should say so.


## After the tenth review: contracts against dollars, on one market

The obvious follow-on to the ninth review. If a single market's dollars and its contract
count are different series, show them together.

**The gap is its own fact, not a volatility chart wearing a positioning label.** That was
the thing worth checking, because `risk = contracts x point value x price x sigma`, so
the wedge could be nothing but "vol is high". Measured against each market's own dollar
volatility, as a 52-week range index like everything else here: correlation **0.30 at the
median** and it **flips sign across markets**, +0.74 on Gasoline against -0.52 on Russell.
The flip is the mechanism rather than noise: volatility acts on a position that has a
side, so the same vol spike widens the wedge upward on a long and downward on a short.

**It is a state, not a jitter.** Lag-1 autocorrelation of the gap is **0.925**; gaps of
25+ percentile points occur on **6.6%** of weeks; the median episode is 2 weeks and the
p90 is 10. Long enough to read, short enough to be an event rather than a regime.

**The live case it was built from.** Large Specs in Silver, week of 2026-08-18: **45th
percentile on contracts, 98th on dollar risk**. Gasoline 53 against 98, Heating Oil 68
against 98. Twelve of the 43 priceable markets disagreed that week about whether the leg
was at a 90/10 extreme at all, and pooled on the page's own expanding percentile the two
lenses disagree on the decile call **15% of weeks**.

Three constraints fell out of the arithmetic rather than out of taste:

- **Single market only.** Contracts do not add across markets, which is the entire reason
  this module converts to dollars. The line is read off the MEMBER frame, not the
  aggregate's `net_contracts`, which sums ES contracts and corn contracts.
- **Percentile scale only.** Contracts and dollars share no axis. On the level scale this
  would be a second y-axis inviting a reader to measure the space between incommensurable
  units, which is the classic dual-axis lie.
- **Numeraire-free.** The gold divisor applies to the value columns only, so the contracts
  line does not move when the Gold switch does. Worth knowing, because a line that stayed
  put while everything around it moved would otherwise look like a bug.

**Two lines was the wrong drawing and the fix was the wedge.** Both series are weekly over
twenty to forty years in a panel about 110px tall, so drawn as two lines of the same shape
they are a thicket the eye cannot separate, and it made no difference whether the second
was dotted, dimmed or a contrasting neutral. Shading the area between them makes the GAP
the visual object, which is the question being asked. At full range the panel then shows
the envelope of divergence rather than any single episode, and the reader drags to open
one up; the help text says so, because a chart that is only readable after an interaction
has to mention the interaction.

The sentence under the headline carries the same fact for the selected week and appears
only when the two lenses disagree about the extreme, or part by 20 percentile points.
Pooled median gap is 5.4 points, so a sentence printed every week is one nobody reads on
the week it matters.

**What this is not.** It is description. Whether the wedge predicts anything is a signal
question for the ladder in npf, judged by someone other than whoever proposed it. The
prior is not neutral: `crowdmon` tested a close cousin, damage = crowding x illiquidity x
fragility, across four pre-registered tests and got no positive result.


## After the eleventh review: contracts against dollars, on the whole board

The tenth review put the contracts-against-dollars wedge on `/exposure`, for one market at a
time. This puts the same comparison on the strip, where it is forty-odd markets at once, and the
measurements behind it are in
[`docs/analysis/2026-08-24-contracts-against-dollars.md`](../analysis/2026-08-24-contracts-against-dollars.md)
with a reproducer script beside it.

The prompt was another printed report, this time gold and silver drawn twice each: net position
in contracts, then the same position in US dollar notional, each with a percentile against its
entire history. Its own numbers are the argument for looking. Silver's speculators were at the
52nd percentile in contracts and the 97th in dollars in the same week.

**What the strip draws is the risk rung, not the notional one, and that is measured rather than
preferred.** Holding the market, the leg, the window and the statistic constant and changing only
the unit: dollar risk correlates 0.917 with the contract reading at the median, parts from it by
30 index points at the 95th percentile, and lands in a different one of the model's three bands
on 11.7% of weeks. Dollar notional scores 0.979, 14.5 points and 5.4% on the same test. Over a
rolling window notional is contracts times a slowly-moving price, so it is close to a monotone
transform of the count, and a second mark for it would sit on top of the first on most rows. It
is carried in the hover instead, one line, because it is the reading the printed reports plot and
a reader comparing the two boards should be able to see both numbers.

Worth being explicit that this is not a rebuttal of the source. The report ranks against the
ENTIRE history, where notional carries the price level and therefore says a great deal; the strip
ranks against a rolling window, which renormalizes exactly that away. The all-history version of
the question already has a home on `/exposure`, and its expanding percentile is what answers it.

**A range index, not a percentile, and the difference is the whole reason the two marks
can share an axis.** The dollar mark is `calculate_range_index` on the dollar series: position
between the window's min and max, which is exactly what the lollipop beside it measures on
contracts. A percentile rank over the same window is a different statistic, set by the whole
distribution rather than by two observations, and drawing one against the other would vary the
STATISTIC and the UNIT at once, leaving a reader unable to say which difference they were looking
at. This document already warns about that confusion in the other direction ("Whichever we draw,
label it as what it is") and the page had to learn it again the hard way: the first reader of the
new mark asked whether the diamond was a percentile, so the word "index" now appears on the hover,
in the legend key and in the caption rather than only here. The percentile version of this question
is the `/exposure` page's, where the rank is expanding or windowed and the units are dollars
throughout.

**One reference mark per row, chosen by a control, rather than a fifth mark.** A row already
carries the head, its stem and a tick per gated leg. The two comparisons worth putting beside them
are the same shape of question, "this leg measured differently", and they compete for the same few
pixels: where the index stood six weeks ago (differently in TIME) and where it sits in dollars at
risk (differently in UNIT). Drawing both was tried first. At ROW_PX a hollow ring and a hollow
diamond a few points apart are one smudge, and on a quiet row they are the same colour as well, so
the row stops saying which is which. The COMPARE control picks one, and a third setting turns both
off, which the page could not do before.

**The dollar mark takes the row's colour and a different shape, because the palette has no free
slot.** Every slot is spoken for twice over: `grid_colors` builds the bull verdict from slot 3,
which is also Price, and the bear verdict from slot 0, which is also Commercials. So a
"this is the dollar reading" colour would collide with a verdict on the one figure whose whole
colour vocabulary is verdicts. Shape carries which comparison it is; colour goes on saying what it
says everywhere else on the row.

**The connector stays, which is the opposite call from the prior mark.** That mark deliberately has
no line back to the head, on the argument that 42 connectors are a lot of ink for a move of a few
points. Here the GAP is the subject rather than a by-product, and the ink is self-limiting in a way
the momentum version's would not be: a market where money and contracts agree draws its diamond
around its own head and a line of zero length, so the rows that spend ink are exactly the rows
worth reading. Where the dollar reading falls between neutral and the head the connector lies along
the stem and is invisible, which is the same information (the diamond is ON the stem, and the
distance to the head is the gap) at no cost.

**Disagreement is counted on the bands, and on three of them.** The caption says how many drawn
markets the two lenses put in different bands, not how many differ by some number of points:
contracts at 98 against dollars at 90 is a wide gap the model answers the same way twice, while 96
against 94 under NPF straddles the line. Three bands rather than a boolean "through a gate",
because Silver on 2026-08-18 sat at 0 on contracts and 96 on dollars, which is both ends of the
axis at once, and a boolean scores the sharpest disagreement on the board as agreement.

**Two counts, for the reason the caption already counts hidden and index-less markets.** A row with
no diamond and a row whose two marks coincide look identical, and only one of them is a
measurement. MSCI EAFE and MSCI Emerging Mkts have no contract multiplier, so they can never carry
one; they are `heldout` today and therefore off the live board, which is why the sentence usually
does not appear.

**Off by default.** It is the only thing this page draws that needs the price store, so it is the
only thing on it that can fail for reasons that have nothing to do with COT. The join costs about
four seconds cold for the whole universe and about a third of a second warm, since `exposure`
caches the daily price and volatility series per symbol and the strip caches the per-market
readings keyed by the store's newest date, exactly as the Heatmap's two joined columns do.

**Where the arithmetic lives.** Both halves are cotmetrics functions (`exposure.market_exposure`
for the dollar series, `indicators.calculate_range_index` for the index) and this repo only
composes them, the same shape as the Heatmap's `_spec_risk`, which pairs `market_exposure` with
`expanding_pct_rank`. The composition is a range index of a dollar series and nothing else in the
app wants one yet. The moment a second surface does, it moves to `cotmetrics.exposure` beside
`windowed_pct_rank` rather than being copied.

**One thing that fell out of the arithmetic and constrains what can ever be drawn here.** A
position's share of open interest is the same number in contracts and in dollars, to 2.2e-16
across the universe, because the point value, the price and the volatility cancel between the
position and the market it sits in. The same identity was frozen independently as P5 of the
pre-registration behind `cotmetrics` 0.8.0, where it is asserted from the numeraire side (a share
must not move when the Gold switch does), which is the side that can actually break and did once.
So there is no dollar version of the NPF basis: the dollar lens is inherently a LEVEL lens, and
under NPF the two marks differ in normalizer as well as in unit. That is the one place this comparison is not a controlled one, it is stated in the caption
rather than hidden, and it is also why the NPF disagreement rate (20.7% of weeks) is the largest
of the three measured.

Still not built, from the list this document opened with: the window min/max/current tooltip, time
in state, and the horizon ladder. The percentile tick from the whiskers section is now cheap,
since `cotmetrics.exposure` grew `windowed_pct_rank` and `expanding_pct_rank` for the exposure
page, but it is a second statistic on one axis and would need the same care about labelling that
this comparison needed about units.


## A third report, and what was left of it (2026-08-24)

A gold-and-silver positioning report, four charts: each market's speculative net position in
contracts and again in US dollar notional, each with a percentile-against-entire-history panel
underneath. Evaluated the same way as the two above, and it is the first one that turned out to be
almost entirely already drawn.

**Its four charts are one state of `/exposure`.** Markets = Gold, Leg = Speculators, Unit =
Notional, Lookback = All history renders the report's gold pages: the dollar level over its own
history, the expanding percentile under it, the contract percentile shaded against it. Ours
carries three things theirs does not: the volatility panel that is the second factor of the
number, the Large-against-Small split under the total, and the publication lag stated in words.

**The numbers agree, which is worth recording once.** Their figures against ours on the same week:

| | the report | this app |
|---|---|---|
| Gold, notional | 113 US$bn, 99th percentile | $114.2bn, 100th |
| Gold, contracts | 258,418, 88th percentile | 258,418, **88th** |
| Silver, contracts | 44,792, 52nd percentile | 44,792, **52nd** |
| Silver, notional | 14 US$bn, 97th percentile | $14.3bn, 98th |

The contract counts and their percentiles match exactly, which is a real cross-check of the store
against an outside source. The dollar figures differ by about a percent because the price behind
them does: they use Stooq/FMP/Yahoo, this stack prices futures off Norgate's unadjusted series.

**One thing was genuinely missing, and it is the thing the report is built on.** The report shows
two markets. This page sums them, and the contract percentile lived only in the single-market
sentence under the headline, because it is read off the member frame. So the moment a reader
selected Gold AND Silver, the comparison the whole report exists to make disappeared from the
page. The fix is a column: `Contracts %ile` beside the dollar percentile in the contributions
table, joined per member. On the live week that puts the report's four numbers in two rows, and it
says out loud what the report leaves to the reader: gold's extreme is 100 in dollars against 88 in
contracts, silver's is 98 against 52, so silver's is almost entirely price and volatility.

Three details of that column, each of which could have gone the other way:

- **It is ranked against all history, not against the Lookback control**, because
  `contribution_table` ranks the dollar columns that way and two percentiles on one row measured
  over different stretches of time is precisely the confusion the column exists to remove. That
  the table does not follow the control while the headline does is a pre-existing inconsistency,
  noted here and not fixed here.
- **It reads the member frame, never the aggregate.** cotmetrics #21 removed the aggregate's
  summed `net_contracts` because it added ES contracts to corn contracts, and this column would
  have been the first thing to bring that back.
- **The count rides along for the hover**, because a percentile has no side and this column's
  whole subject is a position that has one.
- **"Its own history" means the weeks the SET covers.** `aggregate_exposure` restricts every
  member frame to the weeks the total can price, so adding a short-lived market shortens every
  other member's history and moves its percentile: gold reads 88 on its own and **81** inside an
  equities-and-metals set that starts in 2002 because Russell does. The dollar columns have
  always behaved this way and this one follows them, which is the point. It is called out because
  this is the column a reader is most likely to check against a published figure, and a published
  figure will have used the market's whole history. The table's own label still says "each market
  against its own history", which is a shade imprecise for both column families; the fix belongs
  with whoever next edits that label rather than in a second pass here.

What was NOT taken, beyond what the two earlier evaluations already rejected: their "spec = mirror
of commercials" labelling, which folds Small Traders into the speculator leg, and their choice to
give each market its own page, which the contributions table answers in one row per market without
five lines of history in one panel.


## The Lookback control reaches the table (2026-08-24)

The section above records a pre-registered defect and declines to fix it: the contract
percentile follows `contribution_table`'s expanding rank, `contribution_table` ranks
against all history whatever the Lookback control says, and the headline three lines
above it follows the control. So on "52 weeks" the page said "higher than 97% of the last
52 weeks" directly over a column headed "%ile" measured against twenty years, both on
screen at once, with nothing on either saying they were answering different questions.

**Two options, and only one of them is a fix.** Either thread the window through to the
per-member ranks, or keep the table expanding on purpose and say so in the label and the
tooltips. The second was tempting because the expanding percentile has a real claim on
this page: the seventh review calls it "the only thing on the page that answers 'is this
a lot'", since no unit here is stationary through time. But that is an argument for
keeping "All history" as the DEFAULT, which it is, and not for ignoring a control after
the reader has moved it. Copy can describe two bases; it cannot make them comparable, and
the reader's question is "which market is driving the number in the headline", which is
only answerable when the two were ranked over the same weeks.

So the window is threaded through, and the copy is fixed as well rather than instead.

**What had to move together.** Three columns, not one. `contribution_table` gained a
`window` parameter in cotmetrics (the page computes no metrics of its own, and hand
rolling the per-member ranking here would have been the first exception). The
`Contracts %ile` column from the section above follows it in the same change: it was
written to match whatever the dollar columns did, so moving one without the other would
have put the row back to mixing histories by the other route. What changed there is the
basis, not the invariant.

**Three sentences of copy went false the moment it landed**, and they are the reason this
is one change rather than two:

- the dollar column's header tooltip, "Against all of it, whatever the Lookback control
  says", which was written a commit earlier and was true when written
- the table's label, "Percentiles are each market against its own history"
- the standing explanation, which told a reader who moved the control that the band
  moved with it and said nothing about the table

The label also absorbed the OTHER imprecision the section above left for whoever next
edited it. A percentile in this table is bounded twice over, and a reader checking one
against a published figure is off by both: `aggregate_exposure` restricts every member to
the weeks the TOTAL can price, so gold reads 88 alone and 81 in a set that starts in 2002
because Russell does. The label now names both restrictions, and the set clause is dropped
on a single market, where it has nothing to qualify.

**The floor.** `cotmetrics>=0.9.0`, and it is a correctness floor of the loudest kind:
against 0.8.0 the keyword does not exist, so the call raises `TypeError` on every render
of the page and no setting of the control avoids it.

## A fourth report: the FX currency scorecard (2026-10-26)

A one-screen FX scorecard, reviewed from a screenshot. Columns are eight currencies.
Rows are grouped into two blocks, "Positioning and Sentiment" (CFTC level as % of OI,
CFTC 4-week change, a daily sentiment index, 1-month and 6-month risk reversals, a
proprietary positioning measure) and "Momentum" (RSI, deviation from the 20-day,
deviation from the 100-day). Every cell is an integer roughly in -10..+10 with a
diverging red/blue background, and a summary block on top carries one "Positioning" and
one "Momentum" score per currency, which reproduces as the unweighted mean of the rows
beneath it on seven of eight columns.

The format is the idea. Nine rows by eight columns is a whole asset class, levels and
change and tape, in less vertical space than one of our plots, and it is readable
because every cell is the same kind of number. Nothing here computes anything
`cotmetrics` does not already compute.

### What translates, and what does not

**The column axis is an asset class, not the universe.** Eight currencies fit; 47
markets do not. `Currencies` is the natural first card at nine markets (6A 6B 6C 6E 6J
6M 6N 6S DX), and the existing `class_filter` already supplies the control.

**One window across every column.** The per-market `CustomLookbackWeeks` in
`cotmetrics-config/params.yaml` are tuned individually (6B at 30 weeks, 6E at 90), so a
card built on them would put nine differently-defined numbers in one row and invite
exactly the comparison they do not support. The card uses the uniform 52-week lookback.
This is a real cost: the tuned window is the one the book trades, so the card and the
book can disagree about the same market, and the caption has to say so.

**The number is the level, the colour is the verdict.** On the FX scorecard a spec
level of -9 means specs are short, printed as a bearish number for that currency. Under
positioning fade the same fact is the bullish side, so the two presentations disagree
about the sign of the same reading.

The first draft resolved this by flipping the speculator rows so that sign and colour
always agreed, tagging the label "flipped". That was wrong, and wrong in a way this repo
had already settled twice: `strip_traces` states the rule outright, that the lollipop's
POSITION is the level and its COLOUR is the verdict and the two disagreeing is the
interesting case rather than a defect, and the Heatmap's index cells follow it. Flipping
makes the printed number stop being the reading anyone can check against the CFTC file
or against an outside table, in order to save the reader an inference the colour was
already making for them.

So nothing on the card is sign-flipped. A Non-Reportable index of -9 is small specs
washed out, prints as -9, and draws green. What the row label carries is not a "flipped"
tag but which end is bearish, which is a fact about the leg rather than a warning about
the rendering.

Note this is the opposite of `/crowd`'s convention, where colour IS value, and that
departure is documented in `board_traces`. A third surface has to pick one and say which
in its caption; this one picks the strip's, because the card's whole job is a fast scan
for agreement across rows and colour is the faster channel for that.

**A hue requires a verdict, which costs the tape rows theirs.** Once colour means the
verdict rather than the level, every coloured row needs a direction the model actually
establishes. `PositioningModel.setup_state` takes `(comm_idx, lrg_idx, sml_idx)` and no
price term, so the gates say nothing about whether a high price-in-range is the bullish
side. The first draft had quietly assigned those rows "positive is bullish", which is a
trend reading smuggled onto a fade book's surface. They draw no verdict now, like the
open interest row. The alternative is asserting a direction nobody has tested.

**A fill means a verdict; rows without one keep the hue as ink.** Drawing the
directionless rows as saturated neutral blocks was the next mistake, caught on review
(2026-10-26): a filled cell at magnitude 10 pulls the same weight whatever its hue, so
three blocks carrying no verdict competed with the three that did and inverted the
card's hierarchy. The fix keeps the hue and drops the block. Those rows print their
number in the neutral colour, weighted by magnitude, so they read as reference. Fill
is now a categorical signal in its own right: a block means the model has an opinion
about this row, and half the card has none.

**Correlations moved to the label tooltip in the same pass.** Carrying rho on the face
of every row cost more scan time than it bought, and the card is meant to be read in
one glance. Only a note that changes how the NUMBER is read stays visible, which today
is one phrase on one row ("high is bearish" on Non-Reportable). Provenance belongs on
hover; the rho table above is the durable record of it.

**No averaged summary score.** The source's top block is an unweighted mean of
heterogeneous rows, which is a composite nobody has tested, and this stack has already
paid for one of those: crowdmon closed with no positive result after four pre-registered
tests against exactly that shape. The card's top row is the model gate instead
(`pos_idx_setup_*`), which is the only row on the surface that has been through the
ladder. Everything under it is description. That inverts the source's logic in the
direction this repo can defend: there the summary is invented and the detail is real,
here the summary is the only tested thing.

### The measurement that cut the card in half

The source gets six positioning rows out of six genuinely different sources (CFTC, an
options skew at two tenors, a survey, a proprietary book). We have one report read
through legs that are algebraically tied, so the same layout would print one fact
several times and look like several opinions.

Measured before drawing: within-market Spearman against the Commercial Index, median
over 42 markets with at least ten years of weekly reports each, OI-normalized basis, on
the alias columns the card actually draws. Every figure below is on the NATIVE series,
matching the card's own no-flip rule. Only the magnitude answers "how much does this row
add"; the sign says which way the row runs against the anchor, and a negative one on a
speculator leg is the mirror relationship, not a contradiction.

| candidate row | rho vs Commercial Index | on the card |
|---|---|---|
| Open interest z-score | -0.07 | yes, as non-directional context |
| Commercial 6wk move | +0.15 | yes |
| Non-Reportable Index | -0.34 | yes |
| 13wk price change | -0.37 | yes |
| Price in 52wk range | -0.54 | yes |
| Spec long concentration | -0.73 | no |
| Commercial z-score, range-indexed | +0.76 | no |
| Non-Commercial Index | -0.98 | no |
| `willco` | +1.00 | no |

That table was first written on the oriented series, so the two speculator legs appeared
at +0.34 and +0.98. The numbers were right about magnitude and wrong about sign, and
they stayed wrong for exactly as long as the card was flipping those rows. Printing a
correlation measured on a flipped series beside an unflipped row is the same error as
the flip itself, one level up.

Two of these are worth stating on their own.

**`willco` is the Commercial Index.** Median within-market rho 1.0000, and after the
card's -10..+10 mapping the two print the same cell in 99.7% of market-weeks. It is
also identical on both bases for all 42 markets, because
`CotIndexer` builds it from `COMM_PCT_OI`, which is already normalized, so the basis
selector does not move it. Any surface offering both rows and a basis control is making
two promises it does not keep.

**The Non-Commercial Index is the most misleading row available**, and it was most
misleading in the flipped presentation. Net positions across the three legs sum to zero
and Non-Reportable is small, so Commercial and Non-Commercial are near mirrors by
construction, at rho -0.98. Flipped, it printed a different cell from the Commercial
Index in 58% of weeks: cell by cell it read as an independent second opinion while being
the same series. Drawn natively it is the Commercial row's near-exact negative, which at
least looks like what it is. Either way it is off the card. Non-Reportable is the only
other leg carrying its own information (-0.34), which is why it is the one that stayed.

So the honest card is six rows, not nine. Getting back to nine needs sources that are
actually separate, and three exist in this stack already: the four scored ratios in
`components/tape_context.py`, the options surface behind `cotmetrics.options_data`, and
the Supplemental report's Index Trader share, which per cotdata's
`cross-report-comparability.md` is carved out of all three Legacy legs rather than
nested inside one, making it the only genuinely different partition we hold.

### Status

Shipped as `/scorecard` on 2026-10-26: `pages/analytics/scorecard.py` is the data
join, the controls and the caption, `components/scorecard_rows.py` owns the row set,
the colour rule and the drawing, and `tests/test_scorecard_rows.py` pins the four
invariants that break into something which still renders. The measurement script and
the mock generator were session artifacts and are not committed; the rho table above
is the durable record, reproducible from `get_symbols_data(asset, '52',
basis='oi_norm')` plus `calculate_range_index` at window 53.

What the build added beyond the sketch:

- **One card per asset class, not one per selection.** The column axis is a complex,
  so selecting all nine renders nine cards rather than a 42-column table.
- **A scroll wrapper with a sticky label column.** Nine markets inside a phone's
  375px is about twenty pixels a column, which runs the symbols together and wraps
  the gate chip onto two lines. Below a 44px floor the card scrolls instead of
  compressing, and the row labels stay pinned so they do not scroll away with the
  markets. The overflow is on the card's own wrapper and never on the body, which is
  both the mobile-work rule in this repo and a requirement of `position: sticky`.
- Two defects caught in the browser rather than by the suite, both now pinned by
  test: a raw `#` in the sparkline's data URI opened a URI fragment and truncated
  every path to a broken image with nothing raised anywhere; and under
  `table-layout: fixed` the column widths come from the HEADER row, so a label width
  set only on the body let the labels run under the first market's column.

Verified live at the 2026-10-20 report: nine cards, 84 sparklines, no broken images,
`overflow-x: visible` on the body, and the warmer reporting 42 markets.

### The numbers were unreadable, for two separate reasons (2026-10-26)

Reported as "the numbers in the brighter green boxes are not readable", on 6A's
Commercial Index. Measuring it on the live DOM gave **1.01:1**, which is invisible
rather than dim, and the investigation turned up two independent causes. The first
guess, that the ink rule was mischoosing, was right but was not what the reader was
looking at.

**1. The ink pivot was miscalibrated, in shared code.** `cell_text_colour` picked
between `#E2E8F0` and `#101418` at a hardcoded fill luminance of 0.35. For that pair
of inks the two are equally legible at luminance 0.185 (the geometric mean of their
offset luminances), and that crossover is also the worst case. Every fill between
0.185 and 0.35 was therefore printed in the dimmer of the two available inks, worst
on the palettes with a bright bull slot. The pivot is now derived from the ink
constants rather than written down, so it follows them.

This was a pre-existing defect in `board_traces`, which the Scorecard inherited when
the helper moved to `plot_colors` to avoid a second copy. The Crowdedness Board gets
the fix too, and visibly: its Vibrant/Cyberpunk/CMR bull cells go from 2.67:1 to
6.43:1, Muted from 3.50 to 4.90.

Measured bull-slot luminance per palette, which is why no single hardcoded threshold
was ever going to work: Solarized 0.28, Muted 0.50, Vibrant/Cyberpunk/CMR 0.72. The
design mock had been drawn in Solarized, the one palette where the old rule happened
to choose correctly.

**2. A theme rule was overriding the ink entirely, which is what the reader saw.**
`custom.css` sets `color: var(--text-muted) !important` on every `tbody td` under
both themes. Every other table in the app is fine with that, because no other table
colours cells individually. The Scorecard's cells carried the correct ink inline and
had it replaced with a mid-grey, which is the 1.01:1. React cannot emit `!important`
in an inline style, so each cell now carries its ink twice: `color`, and a
`--scorecard-ink` custom property that one scoped rule applies. The rule is written
`table.scorecard-card tbody td` rather than `.scorecard-card tbody td` because the
latter ties with the theme rule on specificity and would win only by sitting later in
the file.

**Worth knowing for the next per-cell-coloured table**: an inline colour on a `td` in
this app does not survive, and nothing warns you. The failure is silent, it looks like
a colour-choice problem rather than a cascade problem, and it sent the first round of
this fix after the wrong cause.

### Per-cell ink inverted the card's attention ordering (2026-10-26)

Reported straight after the contrast fix above: "the mix of white and black text seems
to reverse the eye catching desire, the black +10 is overshadowed by the white +1."
Correct, and it is a different failure from the one before it. Every cell now passed a
contrast check and the card still read backwards.

**Contrast is symmetric; salience is not.** On a dark page a luminous glyph advances
and a dark glyph recedes, so choosing ink per cell by contrast means the brightest
fills get dark text and the faintest get bright text. The fill ramp says "+10 matters
most" while the ink ramp says the opposite, and the ink wins on a small glyph. No
contrast sweep can catch this, because contrast scores a cell in isolation and this is
a property of the ordering ACROSS cells.

**The fix is to cap the fill rather than switch the ink.** `fill_alpha_cap` finds the
strongest blend of a hue that still takes the bright ink, by bisection against
`INK_PIVOT`, and the ramp runs from a bare tint up to that cap. One ink for the whole
card, so magnitude is carried by the fill alone and every number is drawn identically.
Font weight rises with magnitude too (500 to 700), reinforcing rather than competing.

The cost is vividness: a full-strength cell is now `#298664` on Muted rather than
`#2fb282`, because that is as bright as green can get while the cream ink still holds
4:1 on it. It is still the brightest cell on the card, which is all the ordering needs.
Measured across every palette and pole, the capped maximum lands at luminance 0.183 to
0.187 and contrast 4.11 to 4.18.

One quantisation trap: the cap has to be floored onto the alpha grid, not rounded.
`round(cap, 3)` can round UP across the boundary, and `blend_over` then rounds each
channel to an integer besides, so a cap that is under the pivot as a float lands a
hair over it once drawn (0.1855 against a pivot of 0.1851). `_floor_alpha` plus a
step-down loop against the colour actually produced is what holds it.

Pinned by four invariants a contrast test cannot express: the ink is identical at every
magnitude, no fill crosses the pivot, the gate chip shares the card's ink, and fill
strength and font weight both rise monotonically with the number. Live re-check: one
distinct ink across the card, ramp luminance 0.027 at |1| to 0.184 at |10|, worst
contrast 4.15.

Pinned by a palette sweep over every shipped palette, both poles and every step of the
ramp. The floor is 4.0:1 for a filled cell, which is what the app's ink pair allows:
the pivot caps at 4.14, and reaching WCAG's 4.5 would need pure black and white ink,
a change to a constant the Crowdedness Board shares. The unfilled rows do clear 4.5,
after the neutral violet was lightened from `#6c71c4` (3.98:1 at full strength, so a
transparent ramp built on it bottomed out at 2.1) to `#aeb1df`, which stays at least
130 RGB units from every palette's bull and bear slot. Live re-check: 135 cells, none
below 4.0, worst 4.20.

Two things to settle before this becomes a page: whether the uniform-window cost is
acceptable given the book trades the tuned windows, and whether the gate row should show
the model's verdict or stay off a surface whose other rows are untested description.

A third, raised by the colour convention: only three rows carry a fill, and two of them
are the Commercial Index and its own six-week move. If that reads as too thin a coloured
surface, the fix is more independent SOURCES rather than more views of this one, and the
three candidates are named above. It is not more hues.

### Sparklines on the directionless rows (2026-10-26)

Asked whether the tape rows could be sparklines or whiskers instead of numbers. The
whisker half is already settled above, under "Would box-and-whisker present better?",
and nothing about this card changes it: quartiles over about ten effective observations
are confidently imprecise, and `crucible`'s tearsheets already spend the whisker idiom
on confidence intervals.

But that section also names the gap a box fails to close, and it is the one that
matters here: a box discards time, so a market pinned at an extreme for four months and
one that arrived this week still look identical. A sparkline is the only instrument in
the list that closes it, and the property that disqualifies the box helps it. Lag-1
autocorrelation of 0.956 makes quartiles unstable and makes a path SMOOTH, so the
series that reads worst as a distribution reads best as a line.

It also fits the card's epistemic split exactly. These rows have no tested direction,
which is why they carry no hue; a sparkline is the natural partner to that, because it
describes without claiming. So the card ended up with two registers rather than one
scale: coloured blocks where the model has an opinion, paths where it does not.

**Two rows became one, with more in it.** "Price in 52wk range" and "13wk price change"
were both summaries of a single price path, correlated 0.35 with each other. One
sparkline of the 52 weekly closes carries both and a third thing besides: where the dot
ends against the faint midpoint rule is the range reading (verified against the numbers
it replaced, all nine currency columns agree, 6A 72% against the old +4 and DX 93%
against +9), the slope of the last quarter is the 13-week change, and the shape is the
duration neither number could show. The open interest row became a sparkline on the
same argument. Net effect is seven rows to five, with more information on the card.

Figures moved to hover, consistent with the rho decision: the sparkline's own tooltip
gives its percentile, the row label's gives the correlation.

Not extended to the positioning rows, deliberately. They carry verdicts, the fill is
what encodes that, and a path under a coloured block is muddy. Sparklines everywhere
would turn the card back into a grid of charts, which is the compactness this format was
adopted for. The "pinned or just arrived" question is sharper for positioning than for
price, so if it is worth answering there, it wants its own treatment rather than a
sparkline bolted onto a verdict cell.

### Two columns, and the legs become one row of marks (2026-10-26)

Two changes to the Scorecard, the second of which fixed a defect the first had
nothing to do with.

**Two columns.** Nine stacked cards is a lot of scrolling for a surface whose point
is a fast sweep, and most asset classes are three to five markets wide, so a single
column wasted most of a desktop's width. `.scorecard-grid` goes two across at 992px,
Bootstrap's lg and the breakpoint `.setup-grid` already uses, and one below. A card
wider than a half column takes the whole row instead of being squeezed: that is
Currencies alone today at nine markets (576px against a ~476px column), every other
class fitting. `grid-auto-flow: dense` lets a later narrow card fill the gap beside a
full-width one. Nine rows become five, and no table scrolls sideways at 1400px.

**The legs became one row of marks, and the card had been drawing the wrong set.**
Asked how the Strip's single-line leg view or the home card's lane view would look
here. Reading both to answer turned up that neither draws "the three legs": they ask
the MODEL which legs it gates on. `strip_traces.LEG_COLUMNS` and
`signal_cards.strip_legs` agree on the rule, and `strip_legs` states it:

> an NPF card has no Non-Commercial lane because NPF's CS gate never reads that leg,
> and an equity index card has none at all because those gate on Commercials alone

The Scorecard had two fixed rows, Commercials and Non-Reportables. That matches NPF
and is wrong under both CLS gates, **including Raw PF, the model the page opens on**,
which reads all three. So the card was hiding a gate input: a market with extreme
Commercials and no chip had no visible explanation.

The rho measurement that dropped the Non-Commercial row is still right and was the
wrong test to apply. It says the leg adds little INFORMATION (-0.98 against
Commercials, a near-mirror by construction). The strip's rule exists for a different
reason, which is that a gate input has to be visible to explain a verdict. Low
information content is not grounds for hiding a condition the gate checked.

Drawn as the home card's lanes rather than the Strip's single line, because a row
here is a metric and a column is a market, so the Strip's row-of-marks maps onto a
CELL of marks: one lane per gated leg, Commercials on top and larger, each dot at its
leg's range index against a faint midpoint rule. **Identity is the lane, never the
colour**, which keeps the card's one colour rule intact and sidesteps the trap
`signal_cards` hit, that palette slot 0 (the Commercial leg's own colour) IS the bear
red, so a bullish Commercial reading drew a red dot. Colour stays the verdict, so a
Commercial dot high in its range and a speculator dot low in its range both draw
bullish, and a mark whose dots disagree is a market whose legs disagree.

Net effect is one fewer row (two number rows become one mark row) while showing MORE
legs. Resolution is the cost: the mark is 44px for a 0-100 axis, 0.44px per index
point, with dots 4.8px and 3.6px across, so the figures live on hover like every
other provenance on this card.

Pinned in `tests/test_scorecard_legs.py`: the leg set per model, Commercials always
first, every speculator leg reading low as bullish, an equity index contract on
Commercials alone under every model, and a leg the frame cannot supply keeping its
lane so the card cannot silently claim a two-leg gate where there is a three-leg one.

### The leg mark needed the gate band, not just more pixels (2026-10-26)

First cut of the mark was two dots on a bare lane, and it did not convey anything.
Asked whether the row should be double height and show the full strip. Nearly: the
height helps, but it was the second-order fix.

**What was actually missing was the zone.** The home card's gate strip is readable at
~150px of axis not because of the width but because each end carries a tinted band at
the gate threshold. That turns the question from "what is this value" into "is this
leg through the gate", and the second survives any resolution. A sweep surface only
ever asks the second. Leaving it out was the defect; the dimensions were a symptom.

**Height did buy width, which is the part that was not obvious.** The mark is an
`<img>` with the aspect ratio preserved, so a 44x14 drawing in a 67px cell was
HEIGHT-limited and still drew a 44px axis: 0.44px per index point, which is why two
dots a few points apart were one smudge. Going to `height: auto` with a max width
lets the cell drive both dimensions together, so the mark now draws 72x22 at 0.68px
per point, with bigger dots, and the row height roughly doubles as a by-product
rather than as the goal.

**Each lane's bands are oriented by that leg's own direction**, which is the one
place this departs from the home card. There the bear band is always left and the
bull band always right. Here Commercials reach the bull side at the HIGH end and
speculators at the LOW end, so tinting both lanes the same way round would draw a
bull setup as half red. Per-lane orientation makes "every dot in a green band" mean
"bull setup" whichever end each dot sits at, which is exactly the sweep the card is
for, and it keeps the surface's one colour rule.

Two numbers borrowed and one re-derived: `model.band` supplies the thresholds, so a
95/5 gate draws a thin band and an 80/20 gate a wide one; the midline is
`rgba(255,255,255,0.22)` because `signal_cards` found a near-black rule invisible on
a card, which "left every dot measured from nothing", and a table cell is the same
background. The zone alpha is 0.12 rather than their 0.11: the zone here is one lane
instead of the full strip height, but NPF's 80/20 gate still puts 40% of every lane
inside a band, so it is calibrated against the wide gate where the dots have to stay
what the eye lands on.
