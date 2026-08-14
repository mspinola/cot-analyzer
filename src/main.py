import logging
import multiprocessing
import os
import signal
import sys
import threading
import time

import cotmetrics.utils as utils

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def signal_handler(sig, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)


class NoDashComponentFilter(logging.Filter):
    def filter(self, record):
        # Returns False if the string is in the log message, which drops the log
        return "_dash-update-component" not in record.getMessage()


# Create a filter that drops any log record containing ".map"
class SuppressSourceMapErrors(logging.Filter):
    def filter(self, record):
        # Return False (drop the log) if the message contains a request for a .map file
        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            if ".map" in str(exc_value):
                return False
        return ".map" not in record.getMessage()

# If you are also using Werkzeug's default logger, filter that too
logging.getLogger('werkzeug').addFilter(SuppressSourceMapErrors())

# Apply filter to the werkzeug logger
log = logging.getLogger('werkzeug')
log.addFilter(NoDashComponentFilter())
log.addFilter(SuppressSourceMapErrors())

STORE_POLL_SECONDS = 5 * 60


def store_poll_loop():
    """Notice a new COT week even when nobody has the site open.

    A THREAD, deliberately, where daily_options_update_scheduler below is a
    multiprocessing.Process. That one only has to fetch options snapshots and write
    them out, so it does not care which process it runs in. This one mutates the
    CotIndexer singleton that serves HTTP requests, and a child process would refresh
    its own forked copy while the web process kept serving the previous week. Same
    call, wrong address space.

    The navbar callback polls the same way and is the primary trigger, but dcc.Interval
    is client-side: it only ticks while a browser tab is open. Without this loop the
    first visitor after a release pays the ~90 second rebuild. With it, an unattended
    app is current before anyone arrives.

    Every 5 minutes, always, rather than a window around the Friday release. The store
    is a replica fed by a producer push, so it can advance at times no schedule here
    predicts (revisions, a backfill, a manual run, a late release). The check itself is
    one small JSON read, so a window would buy nothing and could only be wrong.

    It is also where the weekly email fires from, for the same reason it is where the
    refresh fires from: this box does not download COT, so noticing the store moved is
    the only "new week" event that happens locally. See weekly_email_trigger, which is
    opt-in and keeps its own ledger. The send is attempted on every tick rather than
    only when refresh_if_stale returns True, because a browser tab's navbar poll can
    win that race and consume the True, and an email that depends on who happened to
    poll first is an email that goes missing on a busy Friday.
    """
    from cotmetrics.database import cotDatabase
    from cotmetrics.indexer import get_indexer

    import weekly_email_trigger

    # The pid is here because which process this lands in is the whole correctness
    # question, and it is invisible otherwise. Under --debug there are two, and only
    # the one serving requests is any use.
    utils.cot_logger.info(
        f"Store poller started in pid {os.getpid()} (every {STORE_POLL_SECONDS}s).")
    while True:
        time.sleep(STORE_POLL_SECONDS)
        try:
            if get_indexer().refresh_if_stale():
                utils.cot_logger.info("Store poller: picked up a new COT week.")

            # After the refresh, never before: refresh_if_stale blocks until the index
            # matches the store, so by here the matrix the email builds is the new
            # week's rather than a mix.
            outcome = weekly_email_trigger.maybe_send(
                cotDatabase.latest_update_timestamp())
            if outcome in ("sent", "failed"):
                utils.cot_logger.info(f"Store poller: weekly email {outcome}.")
        except Exception as e:
            # Never let a transient read kill the loop. A poller that dies silently
            # is worse than no poller, because the navbar still looks like it is
            # watching. Log and wait for the next tick.
            utils.cot_logger.error(f"Store poller failed, will retry: {e}")


def daily_options_update_scheduler():
    import datetime

    import pytz
    from cotmetrics.options_data import update_all_daily_options
    eastern = pytz.timezone('US/Eastern')

    utils.cot_logger.info("Daily options and price update scheduler started.")

    while True:
        now = datetime.datetime.now(eastern)

        # Determine if we are currently inside the overnight update window (6:00 PM - 6:00 AM)
        is_in_update_window = (now.hour >= 18 or now.hour < 6)

        if is_in_update_window:
            utils.cot_logger.info("Scheduler inside update window. Triggering options snapshot refresh...")
            try:
                # Prices now come from the cotdata store (Norgate producer via cotdata-update);
                # only the options Max Pain snapshots are refreshed here.
                update_all_daily_options()

                utils.cot_logger.info("Options snapshot refresh completed successfully.")
            except Exception as e:
                utils.cot_logger.error(f"Scheduled update failed: {e}")

            # Sleep for 3 hours before checking/polling again
            sleep_seconds = 3 * 3600
        else:
            # We are in the daytime. Calculate seconds until the next window starts (6:00 PM ET today)
            target = now.replace(hour=18, minute=0, second=0, microsecond=0)
            sleep_seconds = (target - now).total_seconds()
            utils.cot_logger.info(f"Daytime mode. Sleeping for {sleep_seconds:.0f} seconds until update window starts at 6:00 PM ET.")

        time.sleep(sleep_seconds)


#: How old the newest bar may be before the price store is called stale. Seven days
#: covers a weekend plus a holiday. There is no store-side default for this on
#: purpose: bars only move on trading days, so the number is the deployment's to
#: choose and marketdata refuses to guess it.
PRICE_STALE_AFTER_DAYS = 7


def check_price_store():
    """Refuse to boot into a dashboard that cannot draw a price.

    THE FAILURE THIS EXISTS FOR IS SILENCE, NOT AN ERROR. ADR-0007 moved bars to
    `marketdata` and step 4 repointed cotmetrics at it while the bars themselves
    were still in cotdata's store. Nothing raised. The app booted, bound its port,
    rendered every positioning page off the other store, and drew blank price
    charts, because a futures read against a store with no `bars/futures/` returns
    an empty frame rather than raising. It looked like a UI regression and went
    unnoticed for days.

    Reads the manifest only, so it costs one small JSON read and opens no parquet.

    The policy, and the two halves are deliberately different:

    * **Nothing at all** is a deployment error, not a data gap. The store was never
      filled or `MARKETDATA_STORE` points somewhere wrong, no chart on the site can
      work, and booting anyway is what hid the problem last time. So it refuses.
    * **Some series missing, short or stale** is a data gap. Most of the site still
      works and a human has to decide whether it matters, so it warns and carries
      on rather than taking the positioning half down with it.

    Set `COT_ANALYZER_ALLOW_MISSING_PRICES=1` to downgrade the refusal to a warning,
    for a deliberately COT-only deployment.
    """
    import cotmetrics.config as cm_config
    import yaml

    try:
        import marketdata
    except ImportError as e:
        utils.cot_logger.error(f"marketdata is not importable, so no price can be "
                               f"read: {e}")
        return

    # The siblings are EDITABLE installs, so the version on disk is whatever HEAD
    # that checkout is sitting at rather than anything a pin can promise. Skip
    # rather than crash on a checkout predating the guard: a missing check is a
    # worse outcome than no check, but an unbootable app is worse than both.
    if not hasattr(marketdata, "coverage_gaps"):
        utils.cot_logger.warning(
            "price-store check skipped: this marketdata checkout has no "
            "coverage_gaps(). Pull the sibling to enable the boot guard.")
        return

    # params.yaml is read directly rather than through CotIndexer.instruments,
    # because the point of this check is to run BEFORE the singleton is built: the
    # indexer is the expensive thing whose caches we do not want to rebuild against
    # a store that cannot serve them.
    try:
        with open(cm_config.params_path()) as f:
            params = yaml.safe_load(f)
        universe = [item["Symbol"]
                    for category in params.get("AssetClasses", [])
                    for _k, items in category.items()
                    for item in items]
    except Exception as e:
        utils.cot_logger.warning(f"price-store check skipped, cannot read the "
                                 f"instrument universe: {e}")
        return

    # Only the symbols marketdata carries as futures. The universe also holds a few
    # priced off ETF proxies (MME, MFS), which have no Norgate continuous series and
    # are absent from that registry on purpose, so checking them would report a gap
    # that is not one.
    known = {s.internal for s in marketdata.all_symbols()
             if marketdata.domain_for(s.internal) == "futures"}
    wanted = sorted(set(universe) & known)
    if not wanted:
        utils.cot_logger.warning("price-store check skipped: no configured "
                                 "instrument is in marketdata's futures registry.")
        return

    gaps = marketdata.coverage_gaps(wanted,
                                    stale_after_days=PRICE_STALE_AFTER_DAYS)
    verdict, message = price_store_verdict(
        wanted, gaps,
        allow_missing=bool(os.environ.get("COT_ANALYZER_ALLOW_MISSING_PRICES")))

    if verdict == "ok":
        utils.cot_logger.info(message)
        return
    for g in gaps[:10]:
        utils.cot_logger.warning(f"  price store gap: {g}")
    if len(gaps) > 10:
        utils.cot_logger.warning(f"  ...and {len(gaps) - 10} more")
    if verdict == "refuse":
        utils.cot_logger.error(message)
        sys.exit(1)
    utils.cot_logger.warning(message)


def price_store_verdict(wanted, gaps, *, allow_missing=False):
    """The policy half of `check_price_store`, split out so it can be tested
    without a store: ``(verdict, message)`` for ``'ok' | 'warn' | 'refuse'``.

    The line between warn and refuse is whether ANY price can render. Every
    stored series missing means the store was never filled or `MARKETDATA_STORE`
    points somewhere wrong, which is a deployment error and the exact condition
    that hid last time. A subset missing, short or stale is a data gap: most of
    the site still works, so taking the positioning half down with it would be a
    worse trade than saying so loudly and carrying on.

    "Every series" is counted against the stored tiers rather than the symbols,
    because futures store two per symbol and a store holding only `backadj` is
    half-filled rather than empty.
    """
    if not gaps:
        return "ok", (f"price store OK: {len(wanted)} instruments, every stored tier "
                      f"present and no older than {PRICE_STALE_AFTER_DAYS} days.")
    absent = [g for g in gaps if g.reason in ("absent", "empty")]
    nothing_at_all = len(absent) == len(gaps) and len(absent) >= 2 * len(wanted)
    if nothing_at_all and not allow_missing:
        return "refuse", (
            f"MARKETDATA_STORE holds no bars for any of the {len(wanted)} configured "
            f"instruments, so no price chart on this site can render. This is what a "
            f"store that was never filled, or a wrong MARKETDATA_STORE, looks like. "
            f"Fill it (marketdata-update --bars --domain futures on the producer, or "
            f"marketdata's scripts/import_from_cotdata.py), or set "
            f"COT_ANALYZER_ALLOW_MISSING_PRICES=1 for a deliberately COT-only run.")
    return "warn", (
        f"price store has {len(gaps)} gap(s) across {len(wanted)} instruments. "
        f"Positioning is unaffected; the affected price charts will be blank or short.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="COT Analyzer")
    parser.add_argument("--debug", action="store_true", help="Launch in debug mode (enables Dash debug server)")
    parser.add_argument("--fast", action="store_true", help="Skip data checks and updates on boot for faster startup")
    args, unknown = parser.parse_known_args()

    dash_debug = False
    if args.debug:
        utils.cot_logger.warning("Running in DEBUG mode.")
        dash_debug = True

    # Check if we are in the Werkzeug reloader child process
    is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    # Before anything expensive, and in the parent only so it is said once. Under
    # --debug the parent supervises and the child serves, so refusing here stops
    # the run before a child is spawned at all.
    if not is_reloader:
        check_price_store()

    enable_server = True
    if not enable_server:
        utils.cot_logger.warning(
            "Server is disabled. Only running CotIndexer initialization.")
        from cotmetrics.CotIndexer import CotIndexer
        cmrIndexer = CotIndexer()
        from cotmetrics.indexer import boot_options_update
        boot_options_update()
    else:
        if not is_reloader:
            if not getattr(args, 'fast', False):
                # Guarantee daily price and options cache validation on boot to prevent UI blocking
                utils.cot_logger.info("Eagerly validating options cache on boot (prices come from the marketdata store)...")
                from cotmetrics.indexer import boot_options_update
                boot_options_update()
            else:
                utils.cot_logger.info("[FAST BOOT] Skipping eager cache validation.")

            if not getattr(args, 'fast', False):
                options_update_process = multiprocessing.Process(
                    target=daily_options_update_scheduler
                )
                options_update_process.start()
            else:
                utils.cot_logger.info("[FAST BOOT] Skipping background schedulers.")
                options_update_process = None

        # Deliberately OUTSIDE the `not is_reloader` block above, and gated on a
        # different question. That block asks "am I the process that owns startup
        # work?", which is right for the options fetch and the scheduler: they write
        # to disk, so duplicating them is waste. The poller asks something else, and
        # gets the opposite answer under --debug: it mutates the CotIndexer singleton
        # that answers HTTP, so it has to run wherever that singleton lives.
        #
        # Without the reloader there is one process and it serves. With it (--debug)
        # there are two, and the roles invert: the parent has no WERKZEUG_RUN_MAIN and
        # only supervises, while the CHILD carries the flag and does the serving. So
        # `not is_reloader` puts the poller in the parent, refreshing an index nobody
        # reads, and leaves the serving child without one. That is the same
        # wrong-address-space mistake as running it in the options subprocess.
        #
        # Started even under --fast, unlike the scheduler. --fast buys a faster BOOT,
        # and this costs nothing at boot: it sleeps first, then does one small JSON
        # read every 5 minutes. Skipping it would hand a --fast run the stale-data bug
        # this exists to close.
        serves_requests = is_reloader or not dash_debug
        if serves_requests:
            threading.Thread(
                target=store_poll_loop, name="store-poller", daemon=True
            ).start()

        from app_cot import app

        try:
            start_time = time.time()
            port = os.getenv('PORT', '5001')
            app.run(host="0.0.0.0", port=port, debug=dash_debug)
            utils.cot_logger.info(f"app.run took: {time.time() - start_time:.2f}s")
        except KeyboardInterrupt:
            utils.cot_logger.warning(
                "Keyboard interrupt received, terminating background update processes...")
        finally:
            if not is_reloader:
                if options_update_process:
                    options_update_process.terminate()
                    options_update_process.join()
