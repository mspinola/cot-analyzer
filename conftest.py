import os
import tempfile

# Prevent the CotIndexer boot-time options/price fetch (live network I/O) from
# running when modules are imported during test collection. See CotIndexer.__init__.
os.environ.setdefault("COT_SKIP_BOOT_FETCH", "1")
os.environ.setdefault("APP_ENV", "test")

# Point the visit/predictions database at a scratch file. Without this, cotmetrics'
# module-level cotDatabase resolves to the REAL per-user database (COTMETRICS_DB,
# else the XDG data dir), and any test that exercises visit capture would write rows
# into the deployment's own visitor log on a developer machine. CI never noticed
# because its filesystem is disposable; a laptop's is not. setdefault, so an
# explicitly exported COTMETRICS_DB still wins.
os.environ.setdefault(
    "COTMETRICS_DB",
    os.path.join(tempfile.mkdtemp(prefix="cot_analyzer_test_db_"), "test.db"),
)

# This file used to reach into cotmetrics and replace five CotIndexer methods
# (populate_instruments, calculate_weekly_data and the three exporters) with no-ops for the
# whole session. It had to: the indexer was built at import, so importing any page or
# component that touched it required a populated store, and on CI, where the store is an
# empty directory, construction raised during collection. A test that only wanted a pure
# styling function still paid for a full index.
#
# Both halves of that are gone. cotmetrics builds the indexer on the first get_indexer()
# call rather than at import, and the pages resolve their asset lists inside `layout()`
# instead of at module scope, so importing a page builds nothing at all. Monkeypatching a
# dependency's internals for an entire test session is a sharp tool, and nothing needs it
# now. If a collection-time store error comes back, the cause is a new module-scope
# indexer call, so fix that rather than restoring this. Every page resolves inside layout()
# now, home.py included, so any page is safe to import from a test.

# Dash page modules call dash.register_page() at import time, which requires an
# app to have been instantiated first. Create a minimal one (page discovery
# disabled) so those modules can be imported in tests.
import dash

dash.Dash(__name__, use_pages=True, pages_folder="")
