"""
viz_constants.py

App-layer visual constants: colors and Dash style dicts. Kept out of the data
layer (cotmetrics.constants) so the metrics package carries no presentation
config. Imported by the Dash pages/components as `import viz_constants as vc`.
"""

import cotmetrics.constants as const
import cotmetrics.models as models

# ── the app-wide positioning model ────────────────────────────────────────────
#
# There is one knob here, not two. A model binds a basis to a gate and each basis
# belongs to exactly one model, so "which basis do I plot" and "which rule decides a
# setup" are the same question asked from two ends. Offering them as separate controls
# would let the Home page call something a setup while the Analysis page disagreed,
# which is the inconsistency this whole line of work set out to remove.
#
# So the selector names the *model*, and the basis follows. Panel titles still say
# "Raw" or "% of OI", because there the reader wants to know which series is drawn.
MODEL_BOTH = "both"
# The real models, and the models plus the chart-only comparison view.
MODEL_CHOICES = tuple(m.key for m in models.MODELS)
MODEL_VIEW_CHOICES = MODEL_CHOICES + (MODEL_BOTH,)

# Short enough for a 130px select. The band is in the tooltip rather than the label:
# "NPF CS 80/20" does not fit and the numbers are not what you pick on.
MODEL_LABELS = {
    models.RAW_PF.key: "Raw PF",
    models.NPF.key: "NPF",
    MODEL_BOTH: "Both",
}

MODEL_TOOLTIPS = {
    models.RAW_PF.key: f"{models.RAW_PF.title} — net contracts, all three legs",
    models.NPF.key: f"{models.NPF.title} — net / open interest, Commercials and Small only",
    MODEL_BOTH: "Draws both bases on one axis. Verdicts fall back to Raw PF.",
}


def resolve_model_view(value):
    """A stored selector value -> (model, is_overlay).

    MODEL_BOTH is presentation only: it draws the two bases side by side so the drift
    the normalization removes is visible rather than remembered. get_symbols_data never
    sees it, and no gate can be derived from it, so it resolves to the model whose basis
    the overlay draws as its solid baseline series.
    """
    if value == MODEL_BOTH:
        return models.for_basis(const.BASIS_RAW), True
    return models.resolve(value), False


# ── prose that has to agree with the active gate ──────────────────────────────
#
# The positioning tooltips used to be one fixed set of sentences describing the Raw PF
# three-leg gate: "Commercials are heavily accumulated near their historical max, while
# Speculators are heavily distributed". That is false under NPF, whose CS gate does not
# read the Large Spec leg at all -- and it was already false for equity index contracts
# under either model, since those gate on Commercials alone and their speculator legs
# may sit anywhere. Generating the sentence from the model closes both gaps at once and
# stops a third opening the next time a model is added.

LEG_NAMES = {
    models.LEG_LARGE: "Large Speculators",
    models.LEG_SMALL: "Small Traders",
}


def _join(names):
    """Comma-and list. Two names get "A and B", three get "A, B and C"."""
    if len(names) < 3:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def setup_legs(model, is_equity=False):
    """The speculator legs this gate actually requires, as a list of display names.

    Empty is the meaningful case rather than an error: equities gate on the Commercial
    leg alone, so any sentence about speculator positioning would be inventing a
    condition the setup never checked.
    """
    if is_equity:
        return []
    return [LEG_NAMES[leg] for leg in model.spec_legs if leg in LEG_NAMES]


def setup_leg_phrase(model, is_equity=False):
    """The required speculator legs named in prose, or None if the gate requires none."""
    names = setup_legs(model, is_equity)
    return _join(names) if names else None


def positioning_tooltip(state, model, is_equity=False):
    """Plain-language reading of a row's setup state under the model that produced it.

    Every threshold in the text comes off the model, so the numbers can never describe
    one gate while the badge came from another.
    """
    near = const.SETUP_NEAR_WIDTH
    names = setup_legs(model, is_equity)
    legs = _join(names)
    # "both" only when there are two legs to be both of, and "at least one of" only when
    # there is more than one to choose from. A gate with a single leg reads plainly.
    every = f"{legs} are {'both ' if len(names) == 2 else ''}"
    anyone = f"{'at least one of ' if len(names) > 1 else ''}{legs}"
    # Said once here rather than in four branches. It is the correction that matters
    # most: the old copy asserted speculator crowding on rows where no speculator leg
    # was consulted.
    eq_note = (" Speculator positioning does not gate equity index setups, so it is not "
               "part of this reading.") if is_equity else ""

    if state == const.SETUP_BULL:
        spec = (f", while {every}at or below {model.low}" if names else "")
        return (f"Positioning has reached a bullish extreme. Commercials are heavily "
                f"accumulated at or above {model.high} on the 0-100 index{spec}, "
                f"signaling a strong potential floor or upcoming rally.{eq_note}")
    if state == const.SETUP_BEAR:
        spec = (f", while {every}at or above {model.high}" if names else "")
        return (f"Positioning has reached a bearish extreme. Commercials are heavily "
                f"distributed at or below {model.low} on the 0-100 index{spec}, "
                f"signaling a strong potential ceiling or upcoming drop.{eq_note}")
    if state == const.SETUP_NEAR_BULL:
        spec = (f", with {anyone} also within {near} points of its own extreme"
                if names else "")
        return (f"Positioning is approaching a bullish extreme. Commercials are within "
                f"{near} points of {model.high}{spec}, indicating a potential floor or "
                f"rally may be on the horizon.{eq_note}")
    if state == const.SETUP_NEAR_BEAR:
        spec = (f", with {anyone} also within {near} points of its own extreme"
                if names else "")
        return (f"Positioning is approaching a bearish extreme. Commercials are within "
                f"{near} points of {model.low}{spec}, indicating a potential ceiling or "
                f"drop may be on the horizon.{eq_note}")
    tail = (f" across {_join(['Commercials'] + names)}" if names
            else " in Commercial positioning")
    return (f"Positioning is within normal historical bounds. No extreme structural "
            f"alignment detected{tail}.{eq_note}")


# The basis vocabulary stays for the plot internals: which series a panel draws, and
# what its title says. Those are per-panel facts, below the level the model selects at.
BASIS_BOTH = MODEL_BOTH
BASIS_LABELS = {
    const.BASIS_RAW: "Raw",
    const.BASIS_OI_NORM: "% of OI",
    BASIS_BOTH: "Both",
}

# The OI-normalized line in an overlay, and the band between the two.
#
# The overlay draws the same series (Commercials) twice, so the second line can't take
# another palette slot — every one of the five already means something (Commercials,
# Large Specs, Small Specs, Price, Open Interest) and blue/yellow in particular would
# read as Large/Small Specs. A fixed color doesn't work either: magenta collides with
# Cyberpunk's own #FF007F. So it's derived as a lighter tint of the Commercials color,
# which stays correct for every palette.
# "dash" over "dot": the two bases track each other closely most of the time, and a
# dotted 1px line gets absorbed into the solid one wherever they nearly coincide.
# "longdash" reads better zoomed in but approaches solid at the default multi-year
# range, where its segments outrun the per-point spacing.
BASIS_OVERLAY_DASH = "dash"
BASIS_OVERLAY_TINT = 0.45  # blend toward white; 0 = unchanged, 1 = white

# Which plots the basis control applies to, and why it does not apply to the rest, now
# live on the plot itself in components.plot_registry as `basis_aware` and
# `invariant_note`. They moved for the same reason they were pulled out of the pages:
# a plot that counts as basis-aware in one place but not another is a bug waiting to
# happen, and a plot's own spec is the last place left where that can disagree.

NO_OVERLAY_NOTE = "different units, can't overlay"
NO_BASIS_PLOTS_NOTE = "no basis-dependent plots selected"

# The band spans the two Commercials lines, so it's washed in the Commercials hue
# rather than a neutral grey. Grey belongs to Open Interest, which is this plot's
# secondary series and rides its own axis, so it can cross the band anywhere.
BASIS_DIVERGENCE_ALPHA = 0.18

# Colour weights for the positioning-index ramp, faintest to strongest.
#
# The approach step is deliberately quiet: it should read as a hint that something is
# drifting toward a gate, not as a signal competing with the gate itself. It still sits
# above DIM_TEXT's 0.35 white so "approaching" never looks quieter than "neutral".
INDEX_RAMP_ALPHA_APPROACH = 0.5

# Background wash past the gate, as an 8-digit-hex alpha suffix. One value, not a
# gradient: a setup is binary, so (97, 3, 5) and (100, 0, 0) must render identically.
INDEX_WASH = "30"  # ~19%

# Index momentum labels.
#
# The metric is `index - index.shift(MOMENTUM_PERIOD)`: a *point* change on the 0-100
# positioning index over that many weekly reports. It was previously labelled "WoW ROC"
# everywhere, which was wrong twice: the horizon is MOMENTUM_PERIOD weeks, not one, and
# a point difference is not a rate of change. On Gold at 2026-07-14 the column read -8
# (the 6-week change) while the actual week-over-week move was +7, so the label sent the
# direction the wrong way.
#
# Built from the constant so the two cannot drift apart again: change MOMENTUM_PERIOD
# and every label follows.
MOMENTUM_LABEL = f"{const.MOMENTUM_PERIOD}W Index Change"
MOMENTUM_UNIT_PHRASE = (
    f"change in the 0-100 positioning index over the last {const.MOMENTUM_PERIOD} "
    f"weekly reports, in index points"
)

# Figure chrome, in pixels. The top margin holds the title, legend and rangeselector
# (positioned above the plot area); the bottom holds the x-axis labels. This is fixed
# per figure and does NOT scale with row count.
PLOT_MARGIN_TOP = 200
PLOT_MARGIN_BOTTOM = 50
PLOT_ROW_GAP = 80  # target gap between subplot rows

TEXT_COLOR = "#ABB8C9"
BRIGHTER_TEXT_COLOR = "#E2E8F0"
HOVER_TEXT_COLOR = "#FFFFFF"
BACKGROUND_COLOR = "#1a1a1a"
BLUE_BACKGROUND = "#375a7f"
GRID_COLOR = "rgba(55, 100, 100, 0.2)"
EMPTY_COLOR = 'rgba(0, 0, 0, 0)'

SOLARIZED_DARK_BASE03 = '#002b36'
SOLARIZED_DARK_BASE02 = '#073642'
SOLARIZED_DARK_BASE01 = '#586e75'
SOLARIZED_DARK_BASE00 = '#657b83'
SOLARIZED_DARK_BASE0 = '#839496'
SOLARIZED_DARK_BASE1 = '#93a1a1'
SOLARIZED_DARK_BASE2 = '#eee8d5'
SOLARIZED_DARK_BASE3 = '#fdf6e3'
SOLARIZED_DARK_YELLOW = "#b58900"
SOLARIZED_DARK_ORANGE = "#cb4b16"
SOLARIZED_DARK_RED = "#dc322f"
SOLARIZED_DARK_MAGENTA = "#d33682"
SOLARIZED_DARK_VIOLET = "#6c71c4"
SOLARIZED_DARK_BLUE = "#268bd2"
SOLARIZED_DARK_CYAN = "#2aa198"
SOLARIZED_DARK_GREEN = "#859900"
SOLARIZED_DARK_BACKGROUND_COLOR = SOLARIZED_DARK_BASE03
SOLARIZED_DARK_TEXT = SOLARIZED_DARK_BASE2
SOLARIZED_DARK_BRIGHTER_TEXT = SOLARIZED_DARK_BASE3
TEXT_COLOR = SOLARIZED_DARK_TEXT
BRIGHTER_TEXT_COLOR = SOLARIZED_DARK_BRIGHTER_TEXT
BLUE_BACKGROUND = SOLARIZED_DARK_BACKGROUND_COLOR
GRID_COLOR = SOLARIZED_DARK_BASE03

label_style = {
    'color': TEXT_COLOR,
    'fontSize': '0.85rem',
    'marginRight': '5px',
    'marginBottom': 0,
}

hr_style = {
    'display': 'flex',
    'alignItems': 'center',
    'fontSize': '0.8rem',
    'color': BRIGHTER_TEXT_COLOR,
    'backgroundColor': TEXT_COLOR,
    'height': '1px',
    'border': 'none',
    'opacity': '0.5',
    'marginTop': '10px',
    'marginBottom': '30px',
    'width': '95%',
    'marginLeft': 'auto',
    'marginRight': 'auto',
}

button_style = {
    'height': '38px',
    'display': 'flex',
    'alignItems': 'center',
    'backgroundColor': BACKGROUND_COLOR,
    'color': BRIGHTER_TEXT_COLOR,
    'borderColor': BRIGHTER_TEXT_COLOR,
    'border': '1.5px solid TEXT_COLOR',
    'fontSize': '0.8rem',
    'textAlign': 'center',
    'width': '100%',
    'maxWidth': '200px',
}
