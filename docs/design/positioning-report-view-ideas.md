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
- Three legs are kept separate (Commercial / Large Spec / Small Trader), and the
  Categories page splits Legacy further into Disaggregated and TFF.

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
