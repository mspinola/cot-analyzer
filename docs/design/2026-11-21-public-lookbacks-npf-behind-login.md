# Public site on 26/52, per-market lookbacks and NPF behind the login

Status: **phase 1 built 2026-11-21** (branch `claude/public-lookbacks-26-52`). Phases 2 and 3 not started.

## Why

The public site offers four lookbacks today (26, 52, Custom, CMR). Two of them are
per-market tables that should not be public:

| Control value | Source | What it is |
|---|---|---|
| `Custom` | `CustomLookbackWeeks` | the table the NPF research and livebook were validated on. FROZEN (changing it changes a pre-registered book's signals) |
| `CMR` | `CmrLookbackWeeks` | fitted 2026-11-20 to reproduce a third-party paid index (`npf/scripts/fit_cmr_lookbacks.py`, `npf/docs/npf/2026-11-20-cmr-lookback-fit.md`) |

They differ on 16 of the 47 markets (ES/NQ/YM/RTY 28 vs 26, GC 26 vs 24, BTC 84 vs 90, ...).

The goal:

1. The public site offers **26 and 52 weeks only**, and says nothing about CMR.
2. The per-market tables and everything NPF (model verdicts, setup ages, the setups
   board) move **behind the existing admin login**.
3. npf stays the historical record and keeps evolving. It moves to the recently studied
   lookbacks (mostly 26/52) through its own gate, later.

Phases 1 and 2 touch cot-analyzer only. Nothing that trades (npf, livebook, the
cotmetrics column names) changes until phase 3.

## What already exists

The login gate is built. `src/admin_session.py::is_admin()` answers from the Flask
session set at `/admin`, and `src/local_pages.py::allowed()` is the page-level check
(true on a local run, otherwise only for a logged-in browser). The News Failure page
uses it as of 2026-11-21.

The one rule that carries over: **the check must be server side, in the layout AND in
every callback.** All page data comes back through the single shared
`/_dash-update-component` endpoint, so hiding a dropdown option is not gating. A public
browser can post `lookback="CMR"` to any callback. Every callback that resolves a
lookback has to refuse a gated value for a non-admin request, not merely not offer it.

## Phase 1: the lookback control (cot-analyzer, small)

**Choke point.** `components/controls.py` owns what the control's values mean
(`LOOKBACK_CHOICES`, `lookback_select`, `_canon_lookback`, `lookback_weeks`). Make it
the one place that resolves a value against the request:

- Public values: `"26"`, `"52"`. Default `"52"`.
- Gated values (admin only): the CMR-fit set, labelled **"Custom"** in the UI, and the
  frozen set, labelled **"NPF research"**. Internally they still pass the cotmetrics
  family names (`"CMR"`, `"Custom"`) because those are the column names until phase 3.
  The UI-to-cotmetrics mapping lives in controls.py and nowhere else.
- `_canon_lookback` maps a gated value from a non-admin request, and anything unknown,
  to `"52"`.
- `lookback_select` builds its options per request (a layout function, not a module
  constant), so a public visitor never sees the gated entries.

**Call sites that hard-code `"Custom"` today** and must stop handing the frozen table to
public visitors (they pass it straight to cotmetrics, bypassing the control):

| File | Use | Phase 1 action |
|---|---|---|
| `pages/analytics/heatmap.py` | matrix (`get_matrix_data`), the 572 warm-up, the 601 default | public default `"52"` |
| `pages/analytics/crowd.py` | matrix at 211 and 404 | `"52"` |
| `pages/analytics/divergence.py` | matrix at 190 and 576, raw/norm frames at 112 | `"52"` |
| `pages/analytics/aggregation.py`, `analysis.py`, `positioning.py`, `strip.py`, `categories.py` | `if not lookback: lookback = "Custom"` | `"52"` |
| `pages/analytics/strip.py` | `_custom_weeks`, the caption at 221 | route through `controls.lookback_weeks`, drop the CMR caption |
| `pages/analytics/exposure.py` | its own `LOOKBACK_CUSTOM` option | public: 26/52 only |
| `heatmap.py` 408/480, `strip.py` 134 | exposure/offside always ask for `"Custom"` | check whether the window matters there (the comments say net contracts are read, not the index). If it does not, pass `"52"` so no frozen-table read remains on a public path |
| `weekly_reports.py:198` | weekly matrix | `"52"` (no subscribers to preserve) |
| `app_cot.py:796, 928` | `global_lookback_store` default, URL writer that omits `Custom` | default `"52"`, omit `52` from the URL |

Old `?lookback=Custom` / `?lookback=CMR` links and session-persisted dropdown values
fall back to 52. Breaking them is fine (cleared 2026-11-21, close to none in the wild).

**Other public CMR references to remove:** the `"CMR"` palette name in
`config/params.yaml` (line 42) if it shows in the theme picker. Then grep the rendered
site for "CMR".

**Tests** to rewrite: `test_controls.py` (default is no longer `"Custom"`),
`test_equity_contracts.py::test_cmr_is_a_lookback_choice_resolved_per_market`,
`test_net_range_band.py` (lookback_weeks), `test_analysis_views.py`,
`test_exposure_copy.py` (custom window). Add: a non-admin callback posting `"CMR"` or
`"Custom"` gets 52, and an admin one gets the per-market value.

**Done when** a logged-out browser sees 26/52 only, no response to a logged-out request
is computed on either per-market table, a logged-in browser sees both under the new
labels, and the rendered public pages contain no "CMR".

### As built (2026-11-21)

- `controls.resolve(value)` is the gate. Every callback that reads the lookback calls
  it first. Control values are `26`, `52`, `custom`, `npf`, deliberately not the
  cotmetrics family names, so a posted `"CMR"` or `"Custom"` is unknown and lands on 52.
  `family_label` and `column_label` turn a family back into reader-facing words (the
  positioning table's headers and CSV, the strip summary).
- The exposure page's per-market "Custom" choice was **removed**, not gated. It read the
  frozen table and only applied where every selected market shared one value. Old
  session values fall back to all history.
- The `"CMR"` palette is renamed `"Classic"` in both `config/params.yaml` and the private
  `cotmetrics-config/params.yaml`. An unknown persisted palette name already falls back
  to the default.
- **Still reading the frozen table on a public path, left for phase 2:** the scorecard's
  setup age (`scorecard.py`, `"Custom"` at 178/186 and the matrix at 565). It is the
  book's own window, so phase 2 gates the page rather than changing the window.
- Verified in a deployed-mode run (`COT_ANALYZER_LOCAL_PAGES=0`): every lookback control
  shows 26/52 only, `?lookback=npf` lands on 52, no rendered page contains "CMR". In
  local mode (the same gate as the login): four options, `custom` renders with "Comm
  Custom Idx" headers and a "Custom lookback" summary. The login itself was not
  exercised (it needs the operator's password).

## Phase 2: NPF surfaces behind the login (cot-analyzer, wide)

The NPF model layer (`models.resolve`, `global_model_store`, `setup_age_from`,
`get_board`) is read by: `pages/setups.py` (**the home page**), `scorecard.py`,
`strip.py`, `crowd.py`, `analysis.py`, `oi_alignment.py`, `components/signal_cards.py`,
`components/scorecard_rows.py`.

These views report what the books do, so behind the login they keep reading the frozen
table (`"Custom"` in cotmetrics) and keep matching livebook and `weekly_setups`. They
are not lookback choices, they are the book's own window.

Two kinds of change:

- **Whole pages** (setups board, scorecard): register them as login-gated like
  `/news-failure`, via `local_pages.allowed()` in layout and callbacks.
- **Mixed pages** (strip, crowd, analysis, oi_alignment, signal cards): the positioning
  view stays public on 26/52, and the model verdict columns, setup badges and model
  selector render only for an admin request.

The branch `claude/home-no-model-selector` (2026-11-21, home page always reads the
default model) is already a step this way. Phase 2 builds on it rather than beside it.

**Open decision: what is the public home page** once the setups board is private?
Candidates: the positioning strip, the heatmap, or a plain positioning board on 52
weeks. Needs a call before phase 2 starts.

**Done when** a logged-out browser can reach no model verdict, setup age or setups
board, including through direct callback posts, and the logged-in site is unchanged
from today.

## Phase 3: data layer and npf (separate, later)

Not cot-analyzer work. Listed so phases 1 and 2 do not pre-empt it.

- **cotmetrics rename.** `CustomLookbackWeeks` becomes something like
  `NpfLookbackWeeks`, and the `Custom` column family (`"Comm Custom Index"` ...) gets a
  new name. cotmetrics is on PyPI and the column names are its public surface, so this
  needs a deprecation path (accept both keys, emit both column names for a release),
  not a straight rename. About 60 npf scripts and research reproducers read the old
  names and stay runnable as the historical record. The derived cache
  (`COTMETRICS_CACHE`) rebuilds.
- **npf on 26/52.** New research, governed by npf/AGENTS.md: a new pre-registration and
  the gauntlet, with every variant in the `SearchSpaceLog`. The frozen spec is not
  edited. livebook keeps the frozen table until a 26/52 book is promoted.
- Once a promoted book no longer reads the frozen table, phase 2's book views follow
  the promoted book's window, and the "NPF research" lookback entry can go.

## Reproducer for the figures above

The 16-of-47 count compares `CustomLookbackWeeks` against `CmrLookbackWeeks` (missing
means equal) over every instrument in `cotmetrics-config/params.yaml`. The call-site
table is from `grep -rnE "['\"]Custom['\"]|cmr_lookback|custom_lookback" src` in
cot-analyzer on `claude/home-no-model-selector` at `6e7ad34`.
