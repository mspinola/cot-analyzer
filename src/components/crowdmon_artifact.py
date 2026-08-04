"""Reader for crowdmon's published damage panel. Pure pandas, no Dash, no cotmetrics.

## Why this is a file read and not an import

`crowdmon` computes `D = C x I x Phi`, the crowding / illiquidity / holder-fragility
composite. This app **cannot import it**, and the blocking reason is arithmetic rather than
architectural: production runs Python 3.9 (see `server-side/README.md`) and crowdmon declares
`requires-python = ">=3.10"`. Three softer reasons point the same way, chief among them that
crowdmon's ladder needs Norgate `unadj` **and** `propadj` prices plus a `contract_specs`
table, and this server cannot produce prices however it is provisioned.

So crowdmon publishes a versioned artifact and this reads it. Their
`docs/adr/ADR-0001-crowdmon-publishes-a-panel-rather-than-being-imported.md` is the decision.
It keeps this repo's own rule intact too: **cot-analyzer computes no metrics of its own**,
and rendering a column somebody else computed is not computing it. The line that decides
future cases is theirs:

> Aggregating a published value by a published group key is presentation. Deriving the value
> is a metric.

## The obligation this file exists to keep

**No crowdmon vocabulary appears in this repo's source.** Not one score-state name, not one
stratum name, not one of the four quadrant labels, not a damage band, not the caveat prose.
All of it is carried in the artifact's manifest, generated from crowdmon's live constants at
publish time, and read from there. `tests/test_damage_vocabulary.py` fails if any of those
values turns up here, **including in a comment**: an exemption for prose is how the rule
erodes, and a docstring quoting the value is one copy-paste from being the value.

That is not fastidiousness. crowdmon lost 104 lines of a duplicated spec for a day and only
found it through an unrelated diff, and shipped a test whose entire purpose is that a caveat
its README states and its brief omits is omitted **silently** while the brief still reads
complete. A copy here would be the one with nothing checking it.

## `load` never raises, and that is structural

`use_pages=True` imports every page module at startup, so an exception raised while reading
this artifact takes down the **page registry** rather than one page. A missing store, an
empty one, a manifest naming a directory that is not there, and a schema this reader does not
know all return a degraded `Artifact` carrying a message to render.

Python 3.9 compatible on purpose: `from __future__ import annotations` and `typing`
generics, no `X | Y`, no `match`. CI runs 3.10-3.12 and will not catch a violation.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

import pandas as pd

#: The manifest `schema_version` this reader understands. A newer artifact is refused with a
#: message rather than rendered from columns it half-recognises.
SUPPORTED_SCHEMA = 1

#: Where the panel lives. Defaults to a SIBLING OF THE WORKSPACE, not a sibling of this
#: repo, which is how `cotdata_store` is already deployed: `server-side/README.md` puts it at
#: `$(dirname "$REMOTE_ROOT")/cotdata_store`, one level above `trading_workspace`. Getting
#: this wrong is silent, because a missing store is a legitimate state that renders a
#: perfectly reasonable "not available" card.
#:
#: `parents`: [0] components, [1] src, [2] cot-analyzer, [3] the workspace, [4] its parent.
STORE_ENV = "CROWDMON_STORE"
DEFAULT_STORE = pathlib.Path(__file__).resolve().parents[4] / "crowdmon_store"

OK = "ok"
MISSING = "missing"
PARTIAL = "partial"
UNSUPPORTED = "unsupported"

#: Columns this app actually reads. Asserted on load so a producer-side rename fails HERE,
#: with a named message, rather than rendering an empty column that reads as "no risk".
#: Deliberately a subset of crowdmon's `PANEL_COLUMNS`: naming only what is used means a
#: column they add does not break this, and a column they remove that we use does.
REQUIRED_COLUMNS = (
    "report_date", "market_code", "market_name", "symbol", "asset_class", "report_type",
    "damage_sell_pct", "damage_buy_pct",
    "crowding_long", "crowding_short", "illiquidity_sell", "illiquidity_buy", "fragility",
    "dtl_sell", "dtl_buy", "open_interest",
    "score_state_sell", "score_state_buy", "stratum", "beta",
    "trigger_sell_sigma", "trigger_buy_sigma", "trigger_sell_pct", "trigger_buy_pct",
    "trigger_sell_pool_agrees", "trigger_buy_pool_agrees",
)

#: How many days past the report week before the panel is called stale on wall-clock alone.
#: COT is weekly, so a fortnight means at least one publish did not happen.
STALE_DAYS = 14


@dataclass(frozen=True)
class Artifact:
    """What the page got, including when what it got is nothing."""

    state: str
    message: Optional[str] = None
    report_date: Optional[str] = None
    built_at: Optional[str] = None
    manifest: Dict[str, Any] = field(default_factory=dict)
    panel: Optional[pd.DataFrame] = None
    blocks: Dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.state == OK and self.panel is not None and not self.panel.empty


def store_root(explicit=None) -> pathlib.Path:
    """The artifact root: an argument, then `CROWDMON_STORE`, then the sibling default."""
    if explicit:
        return pathlib.Path(explicit).expanduser()
    value = os.environ.get(STORE_ENV)
    return pathlib.Path(value).expanduser() if value else DEFAULT_STORE


def load(root=None) -> Artifact:
    """Read the current week's panel. Never raises; returns a degraded `Artifact` instead.

    Cached on the manifest's own mtime, so a fresh sync is picked up without a restart and a
    quiet week costs one `stat`. Every callback on the page calls this, and the panel is a
    few megabytes of parquet: re-reading it per interaction is the difference between a
    responsive page and a visibly slow one. The same two-signal idea as `CotIndexer`'s cache
    busting, with the file system supplying the counter.
    """
    base = store_root(root) / "damage"
    try:
        stamp = (base / "manifest.json").stat().st_mtime
    except OSError:
        stamp = None
    return _load_cached(str(base), stamp)


@lru_cache(maxsize=4)
def _load_cached(base_str: str, _stamp) -> Artifact:
    base = pathlib.Path(base_str)
    manifest_path = base / "manifest.json"
    if not manifest_path.exists():
        return Artifact(
            state=MISSING,
            message=(
                "No crowding panel found at {}. It is produced by crowdmon's "
                "bin/publish_damage.sh on the machine that has the Norgate price "
                "subscription, and synced here; this server cannot build it itself."
            ).format(base))

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return Artifact(state=MISSING,
                        message="The panel manifest at {} could not be read: {}".format(
                            manifest_path, exc))

    version = manifest.get("schema_version")
    if version != SUPPORTED_SCHEMA:
        return Artifact(
            state=UNSUPPORTED, manifest=manifest,
            message=("The panel declares schema version {} and this page reads version {}. "
                     "Refusing to render rather than guess at columns it does not know."
                     ).format(version, SUPPORTED_SCHEMA))

    week = manifest.get("current_report_date")
    folder = base / str(week)
    if not folder.is_dir():
        return Artifact(
            state=PARTIAL, manifest=manifest, report_date=week,
            message=("The manifest names report week {} but that directory is not here. "
                     "That is the signature of a partial sync, so this page is showing "
                     "nothing rather than silently showing an older week."
                     ).format(week))

    try:
        panel = pd.read_parquet(folder / "panel.parquet")
    except (OSError, ValueError) as exc:
        return Artifact(state=PARTIAL, manifest=manifest, report_date=week,
                        message="Report week {} is present but unreadable: {}".format(
                            week, exc))

    absent = [c for c in REQUIRED_COLUMNS if c not in panel.columns]
    if absent:
        return Artifact(
            state=UNSUPPORTED, manifest=manifest, report_date=week,
            message=("The panel is missing columns this page reads: {}. The producer's "
                     "schema changed without the version changing."
                     ).format(", ".join(absent)))

    blocks = {}
    blocks_path = folder / "blocks.json"
    if blocks_path.exists():
        try:
            blocks = json.loads(blocks_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # The per-market briefs are the drill-down, not the page. Losing them costs a
            # panel, not the page, so this degrades rather than failing the load.
            blocks = {}

    return Artifact(state=OK, manifest=manifest, report_date=week,
                    built_at=(manifest.get("provenance") or {}).get("built_at"),
                    panel=panel, blocks=blocks)


def latest_week(artifact: Artifact) -> pd.DataFrame:
    """The current report week's rows, or an empty frame."""
    if not artifact.usable:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))
    panel = artifact.panel
    return panel[panel["report_date"] == panel["report_date"].max()].copy()


def history(artifact: Artifact, market_code: str) -> pd.DataFrame:
    """One market's full `damage_*_pct` history, for the drill-down chart."""
    if not artifact.usable:
        return pd.DataFrame()
    panel = artifact.panel
    return panel[panel["market_code"] == str(market_code)].sort_values("report_date")


def staleness(artifact: Artifact, site_latest_date: Optional[str] = None) -> List[str]:
    """Every reason the panel might be out of date, as sentences. Empty when it is current.

    Two independent checks, because they fail for different reasons. The panel can lag the
    COT release the rest of this site is already showing (the publisher did not run, or the
    sync did not), and it can be old in wall-clock terms even when no newer COT week exists.
    """
    if artifact.report_date is None:
        return []
    out = []
    if site_latest_date and str(site_latest_date) > str(artifact.report_date):
        out.append(
            "This page is showing report week {}, but the rest of the site already has {}. "
            "The crowding panel has not been rebuilt for the newer week.".format(
                artifact.report_date, site_latest_date))
    try:
        age = (pd.Timestamp.today().normalize()
               - pd.Timestamp(artifact.report_date)).days
    except (ValueError, TypeError):
        return out
    if age > STALE_DAYS:
        out.append(
            "The panel's report week is {} days old. COT is weekly, so at least one "
            "scheduled publish has not happened.".format(age))
    return out
